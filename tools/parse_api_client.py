#!/usr/bin/env python3
"""
Parse API Client for Kurultai

Provides Kurultai agents with access to Parse's truth detection and
manipulation detection API.

Usage:
    from tools.parse_api_client import ParseClient, ParseAPIError

    client = ParseClient(api_key=os.getenv("PARSE_API_KEY"))

    # Quick truth score
    result = await client.quick_score("https://example.com/article")
    print(f"Truth Score: {result['score']}")

    # Full analysis
    analysis = await client.full_analysis("https://example.com/article")
    print(f"Credibility: {analysis['credibilityScore']}")

    # Rewrite article
    rewrite = await client.rewrite("https://example.com/article")
    print(f"Rewritten: {rewrite['rewrittenTitle']}")
"""

from __future__ import annotations

import asyncio
import os
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Dict, List
import httpx
from neo4j import AsyncGraphDatabase


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_PARSE_BASE_URL = os.getenv(
    "PARSE_BASE_URL",
    "https://kind-playfulness-production.up.railway.app"
)

# Credit costs per Parse API endpoint
CREDIT_COSTS = {
    "full_analysis": 3,   # /api/v1/article/analyze
    "rewrite": 1,         # /api/v1/article/rewrite
    "takeaways": 1,       # /api/extension/rewrite
    "claim_test": 1,      # /api/v1/claim/test
}

# Rate limits (requests per minute)
RATE_LIMITS = {
    "analyze": 5,
    "rewrite": 5,
    "takeaways": 5,
    "claim_test": 5,
    "extract": 10,
}


class QueueStatus(Enum):
    """Analysis job status from Parse queue."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CredibilityLevel(Enum):
    """Credibility levels based on truth score."""
    VERY_HIGH = "very_high"      # 85-100
    HIGH = "high"                # 70-84
    MODERATE = "moderate"        # 55-69
    LOW = "low"                  # 40-54
    VERY_LOW = "very_low"        # 0-39


@dataclass
class ParseUsageStats:
    """Track Parse API usage for governance."""
    total_credits_used: int = 0
    daily_credits_used: int = 0
    daily_limit: int = 100  # Can be overridden via env
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requests_by_endpoint: Dict[str, int] = field(default_factory=dict)
    costs_by_agent: Dict[str, int] = field(default_factory=dict)

    def reset_if_new_day(self) -> None:
        """Reset daily counters if it's a new day."""
        now = datetime.now(timezone.utc)
        if now.date() != self.last_reset.date():
            self.daily_credits_used = 0
            self.last_reset = now

    def can_afford(self, credits: int) -> bool:
        """Check if we have enough daily credit budget."""
        self.reset_if_new_day()
        return (self.daily_credits_used + credits) <= self.daily_limit

    def record_usage(self, endpoint: str, credits: int, agent: str) -> None:
        """Record API usage for tracking."""
        self.total_credits_used += credits
        self.daily_credits_used += credits
        self.requests_by_endpoint[endpoint] = self.requests_by_endpoint.get(endpoint, 0) + 1
        self.costs_by_agent[agent] = self.costs_by_agent.get(agent, 0) + credits


# Global usage tracker
_usage_stats = ParseUsageStats(
    daily_limit=int(os.getenv("PARSE_DAILY_CREDIT_LIMIT", "100"))
)


# ============================================================================
# Exceptions
# ============================================================================

class ParseAPIError(Exception):
    """Base exception for Parse API errors."""

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN",
        status_code: int = 0,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class InsufficientCreditsError(ParseAPIError):
    """Raised when credit budget is exceeded."""

    def __init__(
        self,
        required: int,
        available: int,
        daily_limit: int
    ):
        super().__init__(
            f"Insufficient credits: required {required}, available {available}, daily limit {daily_limit}",
            code="INSUFFICIENT_CREDITS"
        )
        self.required = required
        self.available = available
        self.daily_limit = daily_limit


class RateLimitError(ParseAPIError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        endpoint: str,
        limit: int,
        retry_after: Optional[int] = None
    ):
        super().__init__(
            f"Rate limit exceeded for {endpoint}: {limit} requests/min",
            code="RATE_LIMIT_EXCEEDED"
        )
        self.endpoint = endpoint
        self.limit = limit
        self.retry_after = retry_after


# ============================================================================
# Rate Limiting
# ============================================================================

class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""

    def __init__(self, rate: int, per: float = 60.0):
        """
        Args:
            rate: Number of requests allowed
            per: Time period in seconds (default 60)
        """
        self.rate = rate
        self.per = per
        self.allowance = rate
        self.last_check = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request is allowed."""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_check
            self.allowance += elapsed * (self.rate / self.per)
            self.last_check = now

            if self.allowance > self.rate:
                self.allowance = self.rate

            if self.allowance < 1:
                # Calculate wait time
                wait_time = (1 - self.allowance) * (self.per / self.rate)
                await asyncio.sleep(wait_time)
                self.allowance = 0
            else:
                self.allowance -= 1


# Rate limiters for each endpoint
_rate_limiters: Dict[str, RateLimiter] = {}


def get_rate_limiter(endpoint: str) -> RateLimiter:
    """Get or create a rate limiter for an endpoint."""
    if endpoint not in _rate_limiters:
        limit = RATE_LIMITS.get(endpoint, 5)
        _rate_limiters[endpoint] = RateLimiter(limit)
    return _rate_limiters[endpoint]


# ============================================================================
# Request Cache
# ============================================================================

class RequestCache:
    """Simple in-memory cache for Parse API responses."""

    def __init__(self, ttl: int = 300):
        """
        Args:
            ttl: Time to live in seconds (default 5 minutes)
        """
        self.cache: Dict[str, tuple[Any, float]] = {}
        self.ttl = ttl

    def _make_key(self, endpoint: str, **kwargs) -> str:
        """Create a cache key from endpoint and parameters."""
        key_parts = [endpoint]
        for k in sorted(kwargs.keys()):
            v = str(kwargs[k])
            key_parts.append(f"{k}={v}")
        key = "|".join(key_parts)
        return hashlib.sha256(key.encode()).hexdigest()

    def get(self, endpoint: str, **kwargs) -> Optional[Any]:
        """Get cached response if available and not expired."""
        key = self._make_key(endpoint, **kwargs)
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            else:
                del self.cache[key]
        return None

    def set(self, endpoint: str, value: Any, **kwargs) -> None:
        """Cache a response."""
        key = self._make_key(endpoint, **kwargs)
        expiry = time.time() + self.ttl
        self.cache[key] = (value, expiry)

    def clear(self) -> None:
        """Clear all cached entries."""
        self.cache.clear()


_request_cache = RequestCache(ttl=300)


# ============================================================================
# Main Client
# ============================================================================

class ParseClient:
    """
    Client for Parse API.

    Provides methods for:
    - Quick truth scoring
    - Full article analysis
    - Article rewriting
    - Claim verification
    - Credit balance checking
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_agent: str = "Kurultai/1.0"
    ):
        """
        Args:
            api_key: Parse API key (format: parse_pk_prod_...)
            base_url: Parse API base URL
            user_agent: User agent string for requests
        """
        self.api_key = api_key or os.getenv("PARSE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "PARSE_API_KEY environment variable must be set or api_key parameter provided"
            )

        self.base_url = base_url or DEFAULT_PARSE_BASE_URL
        self.user_agent = user_agent

        # HTTP client with connection pooling
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
            },
            timeout=120.0,  # 2 minute timeout for long analyses
        )

        # Neo4j for audit logging (optional)
        self._neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self._neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        self._neo4j_driver: Optional[AsyncGraphDatabase.driver] = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client and Neo4j connection."""
        await self._client.aclose()
        if self._neo4j_driver:
            await self._neo4j_driver.close()

    def _get_neo4j_driver(self) -> AsyncGraphDatabase.driver:
        """Get or create Neo4j driver for audit logging."""
        if self._neo4j_driver is None:
            self._neo4j_driver = AsyncGraphDatabase.driver(
                self._neo4j_uri,
                auth=(self._neo4j_user, self._neo4j_password)
            )
        return self._neo4j_driver

    async def _log_usage(
        self,
        endpoint: str,
        credits: int,
        agent: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log Parse API usage to Neo4j for audit."""
        try:
            driver = self._get_neo4j_driver()
            async with driver.session() as session:
                await session.run(
                    """
                    MERGE (u:ParseAPIUsage {date: date($date_str)})
                    ON CREATE SET u.totalCredits = 0, u.totalRequests = 0
                    ON MATCH SET u.totalCredits = u.totalCredits + $credits
                    SET u.totalRequests = u.totalRequests + 1,
                        u.lastUpdated = datetime()

                    MERGE (a:Agent {name: $agent})
                    MERGE (u)-[r:USED_API]->(a)
                    ON CREATE SET r.credits = 0, r.requests = 0
                    ON MATCH SET r.credits = r.credits + $credits,
                        r.requests = r.requests + 1
                    """,
                    date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    credits=credits,
                    agent=agent
                )
        except Exception as e:
            # Don't fail the API call if logging fails
            print(f"Warning: Failed to log usage to Neo4j: {e}")

    async def _request(
        self,
        method: str,
        endpoint: str,
        agent: str,
        credits: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to Parse API.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., "/api/v1/article/analyze")
            agent: Name of the Kurultai agent making the request
            credits: Credit cost of this request
            **kwargs: Additional arguments for httpx request

        Returns:
            Parsed JSON response

        Raises:
            ParseAPIError: On API errors
            InsufficientCreditsError: If daily budget exceeded
            RateLimitError: If rate limit exceeded
        """
        # Check credit budget
        if not _usage_stats.can_afford(credits):
            raise InsufficientCreditsError(
                required=credits,
                available=_usage_stats.daily_limit - _usage_stats.daily_credits_used,
                daily_limit=_usage_stats.daily_limit
            )

        # Check rate limit
        endpoint_key = endpoint.split("/")[-1]
        rate_limiter = get_rate_limiter(endpoint_key)
        await rate_limiter.acquire()

        # Check cache for GET requests
        if method == "GET":
            cached = _request_cache.get(endpoint, **kwargs.get("params", {}))
            if cached:
                return cached

        try:
            response = await self._client.request(method, endpoint, **kwargs)

            # Handle error responses
            if response.status_code >= 400:
                error_data = response.json().get("error", {})
                code = error_data.get("code", "UNKNOWN")
                message = error_data.get("message", f"HTTP {response.status_code}")

                if response.status_code == 402:
                    # Insufficient credits on Parse account
                    raise InsufficientCreditsError(
                        required=error_data.get("required", credits),
                        available=error_data.get("available", 0),
                        daily_limit=_usage_stats.daily_limit
                    )
                elif response.status_code == 429:
                    # Rate limit
                    raise RateLimitError(
                        endpoint=endpoint,
                        limit=RATE_LIMITS.get(endpoint_key, 5),
                        retry_after=int(response.headers.get("Retry-After", "60"))
                    )
                else:
                    raise ParseAPIError(
                        message=message,
                        code=code,
                        status_code=response.status_code
                    )

            result = response.json()

            # Track usage
            _usage_stats.record_usage(endpoint, credits, agent)
            await self._log_usage(endpoint, credits, agent, success=True)

            # Cache successful GET requests
            if method == "GET":
                _request_cache.set(endpoint, result, **kwargs.get("params", {}))

            return result

        except httpx.HTTPError as e:
            await self._log_usage(endpoint, credits, agent, success=False, details={"error": str(e)})
            raise ParseAPIError(f"HTTP error: {e}")

    # ========================================================================
    # Quick Score (Fastest)
    # ========================================================================

    async def quick_score(
        self,
        url: str,
        agent: str = "kublai"
    ) -> Dict[str, Any]:
        """
        Get a quick truth score for an article.

        This is the fastest option - returns just the 0-100 score.

        Cost: 0 credits (uses cached/public endpoint if available)
        """
        # For now, use the extract endpoint which returns basic info
        response = await self._request(
            "POST",
            "/api/article/extract",
            agent=agent,
            credits=0,
            json={"url": url}
        )
        return {
            "url": url,
            "title": response.get("title", ""),
            "score": response.get("credibilityScore", 50),
            "source": response.get("source", ""),
        }

    # ========================================================================
    # Full Analysis (Complete)
    # ========================================================================

    async def submit_analysis(
        self,
        url: str,
        agent: str = "kublai",
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit an article for full analysis (async/queued).

        Returns immediately with a job ID. Poll get_analysis_status()
        to retrieve results.

        Cost: 3 credits

        Args:
            url: Article URL to analyze
            agent: Name of Kurultai agent
            options: Optional analysis options

        Returns:
            Dict with jobId, statusUrl, position, estimatedWaitSeconds
        """
        body = {"url": url}
        if options:
            body["options"] = options

        return await self._request(
            "POST",
            "/api/v1/article/analyze",
            agent=agent,
            credits=CREDIT_COSTS["full_analysis"],
            json=body
        )

    async def get_analysis_status(
        self,
        job_id: str,
        agent: str = "kublai"
    ) -> Dict[str, Any]:
        """
        Get the status of an analysis job.

        Cost: 0 credits

        Returns:
            Dict with status, progress, results (if complete)
        """
        return await self._request(
            "GET",
            f"/api/queue/status/{job_id}",
            agent=agent,
            credits=0
        )

    async def full_analysis(
        self,
        url: str,
        agent: str = "kublai",
        poll_interval: int = 5,
        max_wait: int = 300,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit and wait for full article analysis.

        Convenience method that handles polling automatically.

        Cost: 3 credits

        Args:
            url: Article URL to analyze
            agent: Name of Kurultai agent
            poll_interval: Seconds between status checks
            max_wait: Maximum seconds to wait
            options: Optional analysis options

        Returns:
            Complete analysis results
        """
        # Submit job
        job = await self.submit_analysis(url, agent, options)
        job_id = job["jobId"]

        # Poll for completion
        start_time = time.time()
        while True:
            if time.time() - start_time > max_wait:
                raise ParseAPIError(f"Analysis timed out after {max_wait}s")

            status = await self.get_analysis_status(job_id, agent)

            if status.get("status") == "completed":
                return status.get("results", status)
            elif status.get("status") == "failed":
                raise ParseAPIError(f"Analysis failed: {status.get('error', 'Unknown error')}")

            await asyncio.sleep(poll_interval)

    # ========================================================================
    # Rewrite (Bias-Free)
    # ========================================================================

    async def rewrite(
        self,
        url: str,
        agent: str = "chagatai",
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a bias-free rewrite of an article.

        Cost: 1 credit

        Args:
            url: Article URL to rewrite
            agent: Name of Kurultai agent
            options: Rewrite options (preserveStructure, highlightChanges, style)

        Returns:
            Rewritten article with changes summary
        """
        body = {"url": url}
        if options:
            body["options"] = options

        return await self._request(
            "POST",
            "/api/v1/article/rewrite",
            agent=agent,
            credits=CREDIT_COSTS["rewrite"],
            json=body
        )

    # ========================================================================
    # Claim Verification
    # ========================================================================

    async def verify_claim(
        self,
        claim: str,
        agent: str = "jochi"
    ) -> Dict[str, Any]:
        """
        Verify a specific claim using Parse's fact-checking.

        Cost: 1 credit

        Args:
            claim: The claim text to verify
            agent: Name of Kurultai agent

        Returns:
            Verification result with status and evidence
        """
        return await self._request(
            "POST",
            "/api/v1/claim/test",
            agent=agent,
            credits=CREDIT_COSTS["claim_test"],
            json={"claim": claim}
        )

    # ========================================================================
    # Credits & Balance
    # ========================================================================

    async def get_credits(self, agent: str = "ögedei") -> Dict[str, Any]:
        """
        Get current credit balance and subscription info.

        Cost: 0 credits

        Returns:
            Dict with balance, lifetimeCredits, reservedCredits, subscription
        """
        return await self._request(
            "GET",
            "/api/v1/credits",
            agent=agent,
            credits=0
        )

    # ========================================================================
    # Utility Methods
    # ========================================================================

    @staticmethod
    def get_credibility_level(score: int) -> CredibilityLevel:
        """Convert numeric score to credibility level."""
        if score >= 85:
            return CredibilityLevel.VERY_HIGH
        elif score >= 70:
            return CredibilityLevel.HIGH
        elif score >= 55:
            return CredibilityLevel.MODERATE
        elif score >= 40:
            return CredibilityLevel.LOW
        else:
            return CredibilityLevel.VERY_LOW

    @staticmethod
    def get_usage_stats() -> ParseUsageStats:
        """Get current usage statistics."""
        _usage_stats.reset_if_new_day()
        return _usage_stats

    @staticmethod
    def reset_usage_stats() -> None:
        """Reset usage statistics (for testing)."""
        global _usage_stats
        _usage_stats = ParseUsageStats(
            daily_limit=int(os.getenv("PARSE_DAILY_CREDIT_LIMIT", "100"))
        )
        _request_cache.clear()


# ============================================================================
# Convenience Functions
# ============================================================================

async def quick_score(url: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Quick truth score for an article."""
    async with ParseClient(api_key=api_key) as client:
        return await client.quick_score(url)


async def analyze_article(
    url: str,
    api_key: Optional[str] = None,
    wait: bool = True
) -> Dict[str, Any]:
    """Full article analysis (waits for completion by default)."""
    async with ParseClient(api_key=api_key) as client:
        if wait:
            return await client.full_analysis(url)
        else:
            return await client.submit_analysis(url)


async def rewrite_article(
    url: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Generate bias-free rewrite of an article."""
    async with ParseClient(api_key=api_key) as client:
        return await client.rewrite(url)
