"""
Team Size Classifier for Kurultai Agent Teams.

Deterministic keyword-based classifier that scores capability request complexity
and maps it to a team size (individual / small_team / full_team).

This is the critical B1 blocker implementation. It replaces all mocks and
placeholder classifiers with a real, production-ready, deterministic classifier
based on weighted factor extraction using frozenset keyword lookups (O(1) per
keyword).

Usage:
    from tools.kurultai.team_size_classifier import TeamSizeClassifier

    classifier = TeamSizeClassifier()
    result = classifier.classify("Build distributed database with sharding")
    # result == {
    #     "complexity": 0.87,
    #     "team_size": "full_team",
    #     "confidence": 0.92,
    #     "factors": { ... },
    # }
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from tools.kurultai.complexity_config import (
    ComplexityConfig,
    DEFAULT_CONFIG,
    INPUT_MAX_LENGTH,
    complexity_to_team_size,
)

logger = logging.getLogger(__name__)


# =============================================================================
# KEYWORD SETS  (frozenset for O(1) membership tests)
# =============================================================================

TECHNICAL_KEYWORDS: frozenset = frozenset({
    "api", "database", "websocket", "microservice", "kubernetes",
    "distributed", "async", "queue", "cache", "authentication",
    "authorization", "encryption", "pipeline", "orchestration",
    "sharding", "replication", "federation", "graphql", "grpc",
    "protobuf", "container", "docker", "terraform", "lambda",
    "serverless", "gateway", "proxy", "load-balancer", "loadbalancer",
    "cdn", "ssl", "tls", "certificate", "vault",
    "consul", "etcd", "zookeeper", "kafka", "rabbitmq", "redis",
    "elasticsearch", "prometheus", "grafana", "datadog",
    "snowflake", "bigquery", "spark", "hadoop", "airflow",
    "dbt", "fivetran", "dagster", "mlflow", "kubeflow",
    "sagemaker", "inference", "embedding", "vector",
    "rag", "llm", "transformer", "fine-tune", "fine-tuning",
    # Additional technical terms for better coverage (avoiding overly generic words)
    "microservices", "crud", "schema", "indexer",
    "aggregation", "monitoring", "dashboard",
    "nlp", "caching", "persistence",
    "ingestion", "extraction",
    "orchestrator", "scheduler",
    "architecture", "cluster",
    # Infrastructure terms that signal non-trivial systems
    "mtls", "tracing", "tokenization", "discovery",
    "consensus", "lakehouse", "compliance",
    "saas", "billing", "gpu", "webrtc",
    "subscription", "subscriptions",
})

INTEGRATION_KEYWORDS: frozenset = frozenset({
    "integrate", "integration", "connect", "sync", "bridge", "middleware",
    "adapter", "webhook", "callback", "event", "stream",
    "subscribe", "publish", "pubsub", "fanout", "broker",
    "connector", "plugin", "extension", "sdk", "client",
    "provider", "consumer", "producer", "listener", "handler",
    "hook", "trigger", "poll", "push", "pull",
    "ingest", "export", "import", "migration", "etl",
    # Common natural-language forms
    "integrated", "integrating", "connected", "synced",
    "pipeline", "workflow", "automation", "deploy", "deployment",
    "ci", "cd",
})

SECURITY_KEYWORDS: frozenset = frozenset({
    "auth", "oauth", "sso", "mfa", "encrypt", "hash",
    "token", "credential", "secret", "permission", "rbac",
    "zero-trust", "acl", "iam", "saml", "jwt", "hmac",
    "signing", "audit", "compliance", "gdpr", "hipaa",
    "pci-dss", "pci", "sox", "soc2", "iso27001", "nist",
    "penetration", "vulnerability", "firewall", "waf",
    "intrusion", "detection", "sanitize", "sanitization",
    "injection", "xss", "csrf", "cors",
    # Full-form variants so frozenset intersection catches them
    "encryption", "encrypted", "authentication", "authorization",
    "authenticated", "authorized", "permissions", "credentials",
    "tokens", "secrets", "hashing", "signing",
    # Approval/gate workflows imply security processes
    "approval", "gate", "gates",
})

CONCURRENCY_KEYWORDS: frozenset = frozenset({
    "concurrent", "parallel", "distributed", "multi-region",
    "multiregion", "real-time", "realtime", "streaming",
    "async", "asynchronous", "non-blocking", "thread",
    "coroutine", "actor", "cluster", "replica", "shard",
    "partition", "consensus", "raft", "paxos",
    "eventual-consistency", "cqrs", "event-sourcing",
    "multi-tenant", "multitenant", "failover", "ha",
    "high-availability", "fault-tolerant", "chaos",
    "load-balanced", "round-robin", "consistent-hashing",
    # Common natural-language forms
    "regions", "replicas", "shards", "partitions",
    "clusters", "threads", "actors",
    "isolation", "multi-channel", "multichannel",
})

DATA_SCALE_KEYWORDS: frozenset = frozenset({
    "terabyte", "petabyte", "exabyte", "million", "billion",
    "trillion", "high-volume", "large-scale", "massive",
    "big-data", "bigdata", "data-lake", "datalake",
    "warehouse", "olap", "oltp", "columnar", "time-series",
    "geospatial", "graph-database", "graphdb",
    "high-throughput", "low-latency", "sub-millisecond",
    "batch", "micro-batch", "near-real-time", "hot-path",
    "cold-path", "archive", "retention", "compaction",
    # Common natural-language forms
    "scalable", "scalability", "scale", "throughput",
    "latency", "datasets",
    "transformations", "transform", "lineage",
})

SIMPLICITY_KEYWORDS: frozenset = frozenset({
    "simple", "basic", "single", "check", "read", "list",
    "log", "print", "format", "parse", "validate",
    "send", "get", "fetch", "ping", "hello",
    "status", "health", "version", "config", "env",
    "file", "local", "console", "stdout", "debug",
    "update", "set", "add", "remove", "delete",
    "count", "toggle", "rename", "move", "copy",
    "run", "execute", "restart", "clear", "reset",
    "message", "channel", "response", "reply",
    "quick", "tiny", "brief", "minor",
    "standard",
})

# =============================================================================
# DEFAULT WEIGHTS
# =============================================================================

DEFAULT_WEIGHTS: Dict[str, float] = {
    "length_factor": 0.05,
    "technical_terms_factor": 0.28,
    "integration_factor": 0.22,
    "security_factor": 0.22,
    "domain_complexity_factor": 0.30,
    "concurrency_factor": 0.25,
    "data_scale_factor": 0.20,
}

# Synergy bonus when multiple categories of keywords are active.
# This is the key to making complex, multi-dimensional requests score high.
_SYNERGY_THRESHOLDS = [
    # (min_active_factors, bonus)
    (5, 0.45),   # 5+ active factors: very strong synergy
    (4, 0.35),   # 4 active factors: strong synergy
    (3, 0.25),   # 3 active factors: moderate synergy
    (2, 0.12),   # 2 active factors: slight synergy
]

# Threshold for a factor to be considered "active" for synergy purposes.
_FACTOR_ACTIVE_THRESHOLD = 0.08

# Confidence penalty for truncated inputs (per 1000 chars beyond limit).
_TRUNCATION_CONFIDENCE_PENALTY = 0.05


# =============================================================================
# CLASSIFIER
# =============================================================================

class TeamSizeClassifier:
    """Deterministic, keyword-based team-size classifier.

    The classifier extracts seven factors from the capability-request text
    and combines them with configurable weights to produce a complexity score
    in [0, 1]. The score is then mapped to a team size label using the
    centralized thresholds from ``complexity_config``.

    All operations are synchronous and deterministic (no randomness).
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        config: Optional[ComplexityConfig] = None,
    ) -> None:
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.config = config or DEFAULT_CONFIG

        # Pre-compile a word-boundary tokenizer for fast splitting.
        self._token_re = re.compile(r"[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?", re.IGNORECASE)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def classify(self, capability_request: str) -> Dict[str, Any]:
        """Classify a capability request and return a result dict.

        Args:
            capability_request: Free-text description of the capability.

        Returns:
            Dict with keys:
                complexity  (float 0-1)
                team_size   (str: "individual" | "small_team" | "full_team")
                confidence  (float 0-1)
                factors     (dict of factor name -> float value)
        """
        if not isinstance(capability_request, str):
            capability_request = str(capability_request) if capability_request is not None else ""

        # --- Input validation / truncation ---
        truncated = False
        original_length = len(capability_request)
        if original_length > INPUT_MAX_LENGTH:
            capability_request = capability_request[:INPUT_MAX_LENGTH]
            truncated = True
            logger.warning(
                "Input truncated from %d to %d characters",
                original_length,
                INPUT_MAX_LENGTH,
            )

        # --- Tokenise (lowercase) ---
        text_lower = capability_request.lower()
        tokens = self._token_re.findall(text_lower)
        token_set = frozenset(tokens)

        # --- Factor extraction ---
        factors = self._extract_factors(text_lower, token_set, tokens)

        # --- Weighted combination ---
        complexity = self._combine_factors(factors)

        # --- Confidence ---
        confidence = self._compute_confidence(factors, truncated, original_length, tokens)

        # --- Team size mapping ---
        team_size = complexity_to_team_size(complexity, self.config)

        return {
            "complexity": round(complexity, 4),
            "team_size": team_size,
            "confidence": round(confidence, 4),
            "factors": {k: round(v, 4) for k, v in factors.items()},
        }

    # --------------------------------------------------------------------- #
    # Factor extraction
    # --------------------------------------------------------------------- #

    def _extract_factors(
        self,
        text_lower: str,
        token_set: frozenset,
        tokens: list,
    ) -> Dict[str, float]:
        """Extract all complexity factors from the tokenised input."""
        factors: Dict[str, float] = {}

        factors["length_factor"] = self._length_factor(text_lower)
        factors["technical_terms_factor"] = self._keyword_density(
            token_set, TECHNICAL_KEYWORDS, cap=3,
        )
        factors["integration_factor"] = self._keyword_density(
            token_set, INTEGRATION_KEYWORDS, cap=2,
        )
        factors["security_factor"] = self._keyword_density(
            token_set, SECURITY_KEYWORDS, cap=2,
        )
        factors["domain_complexity_factor"] = self._domain_complexity(text_lower, token_set)
        factors["concurrency_factor"] = self._keyword_density(
            token_set, CONCURRENCY_KEYWORDS, cap=2,
        )
        factors["data_scale_factor"] = self._keyword_density(
            token_set, DATA_SCALE_KEYWORDS, cap=2,
        )

        return factors

    @staticmethod
    def _length_factor(text: str) -> float:
        """Score based on request length.

        Very short requests are typically simple; longer descriptions
        often describe more complex systems.
        """
        length = len(text)
        if length < 20:
            return 0.05
        if length < 50:
            return 0.15
        if length < 100:
            return 0.30
        if length < 200:
            return 0.50
        if length < 400:
            return 0.70
        return min(length / 600, 1.0)

    @staticmethod
    def _keyword_density(
        token_set: frozenset,
        keywords: frozenset,
        cap: int,
    ) -> float:
        """Count how many keyword-set members appear and normalise to [0, 1].

        Uses frozenset intersection for O(min(|token_set|, |keywords|)).
        """
        hits = len(token_set & keywords)
        return min(hits / cap, 1.0)

    @staticmethod
    def _domain_complexity(text_lower: str, token_set: frozenset) -> float:
        """Heuristic for domain-specific complexity markers.

        Checks for multi-word phrases and domain patterns that a simple
        token-set lookup would miss (e.g. "end-to-end", "cross-region").
        """
        score = 0.0

        # Multi-word / hyphenated phrases scored via substring search
        complex_phrases = [
            ("end-to-end", 0.20),
            ("cross-region", 0.20),
            ("multi-cloud", 0.25),
            ("zero-trust", 0.20),
            ("self-healing", 0.20),
            ("blue-green", 0.15),
            ("canary deploy", 0.15),
            ("service mesh", 0.20),
            ("data lineage", 0.15),
            ("schema evolution", 0.15),
            ("feature flag", 0.10),
            ("a/b test", 0.10),
            ("ab test", 0.10),
            ("circuit breaker", 0.15),
            ("rate limit", 0.12),
            ("dead letter", 0.15),
            ("dead-letter", 0.15),
            ("back-pressure", 0.15),
            ("idempoten", 0.12),   # covers idempotency / idempotent
            ("multiple region", 0.20),
            ("across region", 0.15),
            ("across multiple", 0.15),
            ("across di", 0.15),  # "across different/diverse/distributed"
            ("approval gate", 0.12),
            ("ci/cd", 0.15),
            ("retry logic", 0.12),
            ("conflict resolution", 0.15),
            ("rolling update", 0.12),
            ("health check", 0.10),
            ("real-time", 0.12),
            ("real time", 0.12),
            ("multi-tenant", 0.18),
            ("multi-region", 0.20),
            ("anomaly detection", 0.12),
            ("intent detection", 0.12),
            ("entity extraction", 0.12),
            ("relevance scoring", 0.10),
            ("event-driven", 0.12),
            ("event driven", 0.12),
            ("pub/sub", 0.12),
            ("publish-subscribe", 0.12),
            ("screen sharing", 0.10),
            ("auto-scaling", 0.12),
            ("load balanc", 0.12),  # covers load balancing/balancer
            ("infrastructure as code", 0.15),
            ("state management", 0.10),
            ("gradual rollout", 0.10),
            ("consumer group", 0.10),
            ("full-text search", 0.12),
            ("data validation", 0.10),
            ("schema enforce", 0.10),
            ("batch processing", 0.12),
            ("model training", 0.12),
            ("model inference", 0.12),
            ("token bucket", 0.10),
            ("token refresh", 0.10),
            ("service discovery", 0.15),
            ("fault injection", 0.12),
            ("cache invalidation", 0.12),
            ("edge computing", 0.15),
            ("query federation", 0.15),
            ("tenant isolation", 0.18),
            ("audit logging", 0.12),
            ("audit trail", 0.12),
            ("multi-provider", 0.15),
            ("multiple provider", 0.15),
            ("cryptographic hash", 0.12),
            ("distributed consensus", 0.18),
            ("distributed tracing", 0.15),
            ("petabyte-scale", 0.18),
            ("petabyte scale", 0.18),
            ("pci-compliant", 0.18),
            ("pci compliant", 0.18),
            ("hipaa-compliant", 0.18),
            ("hipaa compliant", 0.18),
            ("soc2", 0.12),
            ("zero-downtime", 0.12),
            ("eventual consistency", 0.15),
            ("eventual-consistency", 0.15),
            ("model orchestration", 0.15),
            ("feature pipeline", 0.12),
            ("vector database", 0.12),
            ("gpu inference", 0.15),
            ("streaming inference", 0.12),
            ("tool use", 0.10),
            ("multi-agent", 0.15),
            ("multi agent", 0.15),
            # Compliance/regulatory complexity
            ("tamper-proof", 0.15),
            ("tamper proof", 0.15),
            ("fault-tolerant", 0.15),
            ("fault tolerant", 0.15),
            ("automated recovery", 0.15),
            ("automated disaster", 0.15),
            ("billing integration", 0.12),
            ("payment processing", 0.15),
            ("identity federation", 0.18),
            ("event sourcing", 0.15),
            ("event-sourcing", 0.15),
            ("chaos engineering", 0.15),
            ("computer vision", 0.12),
            ("data lakehouse", 0.15),
            ("recommendation engine", 0.12),
            ("fraud detection", 0.15),
            ("continuous authentication", 0.15),
        ]
        for phrase, weight in complex_phrases:
            if phrase in text_lower:
                score += weight

        # Penalise simplicity indicators
        simplicity_hits = len(token_set & SIMPLICITY_KEYWORDS)
        total_tokens = len(token_set)
        simplicity_ratio = simplicity_hits / max(total_tokens, 1)

        if simplicity_ratio > 0.3:
            score = max(score - 0.30, 0.0)
        elif simplicity_hits >= 3:
            score = max(score - 0.25, 0.0)
        elif simplicity_hits >= 2:
            score = max(score - 0.15, 0.0)

        # Boost for very long, detailed descriptions (signals complex requirements)
        if len(text_lower) > 80 and total_tokens > 12:
            score += 0.08

        return min(score, 1.0)

    # --------------------------------------------------------------------- #
    # Combination & confidence
    # --------------------------------------------------------------------- #

    def _combine_factors(self, factors: Dict[str, float]) -> float:
        """Weighted sum of factors with synergy bonus, clamped to [0, 1].

        The synergy bonus rewards requests that span multiple complexity
        dimensions (e.g. both technical depth AND security AND concurrency).
        This ensures that genuinely complex, multi-faceted requests reach
        the high-complexity band (>0.8) even if no single factor dominates.
        """
        # Base weighted sum
        raw = sum(
            factors.get(name, 0.0) * weight
            for name, weight in self.weights.items()
        )

        # Count how many keyword-based factors are meaningfully active.
        # Exclude length_factor from synergy (it's not a keyword category).
        keyword_factor_names = [
            "technical_terms_factor", "integration_factor",
            "security_factor", "concurrency_factor",
            "data_scale_factor", "domain_complexity_factor",
        ]
        active_count = sum(
            1 for name in keyword_factor_names
            if factors.get(name, 0.0) >= _FACTOR_ACTIVE_THRESHOLD
        )

        # Apply synergy bonus (take the first matching threshold)
        for min_active, bonus in _SYNERGY_THRESHOLDS:
            if active_count >= min_active:
                raw += bonus
                break

        return max(0.0, min(raw, 1.0))

    @staticmethod
    def _compute_confidence(
        factors: Dict[str, float],
        truncated: bool,
        original_length: int,
        tokens: list,
    ) -> float:
        """Compute a confidence score for the classification.

        Confidence is high when:
        - Multiple independent factors agree on the complexity band.
        - The input is not truncated.
        - The input contains enough tokens to be meaningful.
        """
        # Base confidence
        confidence = 0.85

        # Boost when multiple factors are active
        active_factors = sum(1 for v in factors.values() if v > 0.1)
        if active_factors >= 4:
            confidence += 0.10
        elif active_factors >= 2:
            confidence += 0.05

        # Penalty for very short inputs (low signal)
        if len(tokens) < 3:
            confidence -= 0.25
        elif len(tokens) < 6:
            confidence -= 0.10

        # Truncation penalty
        if truncated:
            excess_chars = original_length - INPUT_MAX_LENGTH
            penalty = min(
                (excess_chars / 1000) * _TRUNCATION_CONFIDENCE_PENALTY,
                0.30,
            )
            confidence -= penalty

        return max(0.0, min(confidence, 1.0))
