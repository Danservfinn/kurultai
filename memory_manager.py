"""
MemoryManager - Tiered Memory Management for OpenClaw System.

This module provides bounded file-based memory with tiered loading from Neo4j:
- Hot tier: In-memory (~1,600 tokens), eagerly loaded
- Warm tier: On-demand from Neo4j (~400 tokens), lazy loaded
- Cold tier: On-demand with timeout (~200 tokens), 5s timeout
- Archive tier: Query only, never loaded into memory

Key Features:
- Fixed initialization cost regardless of conversation length
- Bounded MEMORY.md size (2,000 tokens max)
- Full history retained in Neo4j
- Async-safe implementation
- Graceful degradation when Neo4j unavailable
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from contextlib import asynccontextmanager
from functools import wraps

# Lazy imports for neo4j to avoid numpy recursion issues during test collection
# The neo4j driver imports numpy which can cause RecursionError when pytest's -W error is enabled
_AsyncGraphDatabase = None
_AsyncDriver = None
_ServiceUnavailable = None
_Neo4jError = None
_TransientError = None


def _import_neo4j():
    """Lazy import neo4j modules."""
    global _AsyncGraphDatabase, _AsyncDriver, _ServiceUnavailable, _Neo4jError, _TransientError
    if _AsyncGraphDatabase is None:
        from neo4j import AsyncGraphDatabase, AsyncDriver
        from neo4j.exceptions import ServiceUnavailable, Neo4jError, TransientError
        _AsyncGraphDatabase = AsyncGraphDatabase
        _AsyncDriver = AsyncDriver
        _ServiceUnavailable = ServiceUnavailable
        _Neo4jError = Neo4jError
        _TransientError = TransientError


# Configure logging
logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """Memory access tiers ordered by recency/accessibility."""
    HOT = "hot"       # In memory, always available (~1,600 tokens)
    WARM = "warm"     # Lazy loaded from Neo4j (~400 tokens)
    COLD = "cold"     # On-demand with timeout (~200 tokens)
    ARCHIVE = "archive"  # Query only, never loaded


class MemoryLoadError(Exception):
    """Raised when memory tier loading fails."""
    pass


class Neo4jTimeoutError(Exception):
    """Raised when Neo4j query exceeds timeout."""
    pass


@dataclass
class MemoryEntry:
    """Single memory entry with metadata."""
    id: str
    content: str
    tier: MemoryTier
    token_count: int
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    agent: str = "system"
    entry_type: str = "general"
    embedding: Optional[List[float]] = None

    def touch(self) -> None:
        """Update last accessed timestamp and access count."""
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1


@dataclass
class TierStats:
    """Statistics for a memory tier."""
    entry_count: int = 0
    token_count: int = 0
    max_tokens: int = 0
    hit_count: int = 0
    miss_count: int = 0
    load_count: int = 0
    last_load: Optional[datetime] = None

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0

    @property
    def utilization(self) -> float:
        """Calculate token utilization percentage."""
        return (self.token_count / self.max_tokens * 100) if self.max_tokens > 0 else 0.0


@dataclass
class MemoryStats:
    """Complete memory statistics."""
    hot: TierStats = field(default_factory=lambda: TierStats(max_tokens=1600))
    warm: TierStats = field(default_factory=lambda: TierStats(max_tokens=400))
    cold: TierStats = field(default_factory=lambda: TierStats(max_tokens=200))
    archive: TierStats = field(default_factory=lambda: TierStats(max_tokens=0))
    neo4j_available: bool = False
    last_neo4j_check: Optional[datetime] = None


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses a simple approximation: ~4 characters per token for English text.
    This is a fast approximation - actual token counts require tiktoken.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    # Simple approximation: ~4 chars per token
    return len(text) // 4 + 1


def retry_with_backoff(max_retries: int = 3, base_delay: float = 0.1):
    """
    Decorator for async retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            _import_neo4j()
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (_ServiceUnavailable, _TransientError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Transient error in {func.__name__}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries exceeded in {func.__name__}: {e}"
                        )
            raise last_exception
        return wrapper
    return decorator


class MemoryManager:
    """
    Tiered memory manager for OpenClaw agents.

    Manages memory across 4 tiers with different access patterns:
    - Hot: Always in memory, immediate access
    - Warm: Lazy loaded from Neo4j on demand
    - Cold: Loaded with timeout protection
    - Archive: Query only, never cached

    Attributes:
        agent_name: Name of the agent using this memory manager
        hot_cache: In-memory cache for hot tier
        warm_cache: In-memory cache for warm tier
        cold_cache: In-memory cache for cold tier
        neo4j_uri: Neo4j connection URI
        neo4j_driver: Async Neo4j driver instance
    """

    # Token limits per tier
    HOT_TOKEN_LIMIT = 1600
    WARM_TOKEN_LIMIT = 400
    COLD_TOKEN_LIMIT = 200
    TOTAL_MEMORY_LIMIT = 2000  # Max tokens in MEMORY.md

    # Timeout configurations
    WARM_LOAD_TIMEOUT = 2.0  # seconds
    COLD_LOAD_TIMEOUT = 5.0  # seconds

    def __init__(
        self,
        agent_name: str,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        fallback_mode: bool = True,
        operational_memory: Optional[Any] = None
    ):
        """
        Initialize MemoryManager.

        Args:
            agent_name: Name of the agent (e.g., 'kublai', 'mongke')
            neo4j_uri: Neo4j bolt URI
            neo4j_username: Neo4j username
            neo4j_password: Neo4j password
            database: Neo4j database name
            fallback_mode: If True, operate without Neo4j if unavailable
            operational_memory: Optional OperationalMemory instance for shared connection
        """
        self.agent_name = agent_name
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.fallback_mode = fallback_mode

        # Use shared operational memory if provided
        self._operational_memory = operational_memory
        self._driver: Optional[Any] = None  # Type is _AsyncDriver when initialized
        self._owns_driver = operational_memory is None

        # In-memory caches
        self._hot_cache: Dict[str, MemoryEntry] = {}
        self._warm_cache: Dict[str, MemoryEntry] = {}
        self._cold_cache: Dict[str, MemoryEntry] = {}

        # Cache locks for async safety
        self._hot_lock = asyncio.Lock()
        self._warm_lock = asyncio.Lock()
        self._cold_lock = asyncio.Lock()

        # Statistics
        self._stats = MemoryStats()

        # Load tracking
        self._warm_loaded = False
        self._cold_loaded = False

        logger.info(f"MemoryManager initialized for agent: {agent_name}")

    async def initialize(self) -> bool:
        """
        Initialize Neo4j connection and load hot tier.

        Returns:
            True if initialization successful
        """
        try:
            # Initialize driver if we own it
            if self._owns_driver:
                await self._initialize_driver()
            else:
                # Use operational memory's session factory
                self._stats.neo4j_available = True

            # Load hot tier (eager load)
            await self._load_hot_tier()

            logger.info(f"MemoryManager initialized successfully for {self.agent_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize MemoryManager: {e}")
            if not self.fallback_mode:
                raise
            return False

    async def _initialize_driver(self) -> None:
        """Initialize async Neo4j driver."""
        if self.neo4j_password is None:
            raise ValueError("Neo4j password is required")

        try:
            _import_neo4j()
            self._driver = _AsyncGraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_username, self.neo4j_password),
                max_connection_pool_size=10
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            self._stats.neo4j_available = True
            self._stats.last_neo4j_check = datetime.now(timezone.utc)
            logger.info(f"Async Neo4j driver initialized: {self.neo4j_uri}")
        except _ServiceUnavailable as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self._driver = None
            self._stats.neo4j_available = False
            if not self.fallback_mode:
                raise

    @asynccontextmanager
    async def _session(self):
        """Async context manager for Neo4j sessions."""
        if self._operational_memory is not None:
            # Use operational memory's session
            # This is a sync context manager, so we need to handle it differently
            # For now, create our own session
            pass

        if self._driver is None:
            if self.fallback_mode:
                logger.warning("Neo4j unavailable, operating in fallback mode")
                yield None
                return
            else:
                raise MemoryLoadError("Neo4j is not available")

        session = None
        try:
            session = self._driver.session(database=self.database)
            yield session
        except _ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            self._driver = None
            self._stats.neo4j_available = False
            if self.fallback_mode:
                yield None
            else:
                raise
        finally:
            if session:
                await session.close()

    async def _execute_with_timeout(
        self,
        query_func: Callable,
        timeout: float,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a query with timeout protection.

        Args:
            query_func: Async function to execute
            timeout: Timeout in seconds
            *args, **kwargs: Arguments for query_func

        Returns:
            Query result

        Raises:
            Neo4jTimeoutError: If query exceeds timeout
        """
        try:
            return await asyncio.wait_for(
                query_func(*args, **kwargs),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise Neo4jTimeoutError(f"Query exceeded {timeout}s timeout")

    # ========================================================================
    # Tier Loading Methods
    # ========================================================================

    async def _load_hot_tier(self) -> None:
        """
        Load hot tier into memory (eager loading).

        Hot tier contains:
        - Current session context
        - Active tasks
        - Recent critical notifications
        - Agent state
        """
        async with self._hot_lock:
            if not self._stats.neo4j_available:
                logger.warning("Neo4j unavailable, hot tier will be empty")
                return

            try:
                entries = await self._fetch_hot_tier_entries()

                total_tokens = 0
                for entry_data in entries:
                    tokens = estimate_tokens(entry_data.get("content", ""))
                    if total_tokens + tokens > self.HOT_TOKEN_LIMIT:
                        break

                    entry = MemoryEntry(
                        id=entry_data["id"],
                        content=entry_data["content"],
                        tier=MemoryTier.HOT,
                        token_count=tokens,
                        created_at=entry_data.get("created_at", datetime.now(timezone.utc)),
                        last_accessed=datetime.now(timezone.utc),
                        agent=entry_data.get("agent", self.agent_name),
                        entry_type=entry_data.get("entry_type", "general"),
                        embedding=entry_data.get("embedding")
                    )

                    self._hot_cache[entry.id] = entry
                    total_tokens += tokens

                self._stats.hot.token_count = total_tokens
                self._stats.hot.entry_count = len(self._hot_cache)
                self._stats.hot.load_count += 1
                self._stats.hot.last_load = datetime.now(timezone.utc)

                logger.info(
                    f"Hot tier loaded: {self._stats.hot.entry_count} entries, "
                    f"{self._stats.hot.token_count} tokens"
                )

            except Exception as e:
                logger.error(f"Failed to load hot tier: {e}")
                if not self.fallback_mode:
                    raise

    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def _fetch_hot_tier_entries(self) -> List[Dict[str, Any]]:
        """
        Fetch hot tier entries from Neo4j.

        Returns:
            List of entry dictionaries
        """
        cypher = """
        // Current session context
        MATCH (ctx:SessionContext {agent: $agent})
        WHERE ctx.active = true
        RETURN ctx.id as id, ctx.content as content, ctx.created_at as created_at,
               'session_context' as entry_type, $agent as agent

        UNION

        // Active tasks assigned to or created by this agent
        MATCH (t:Task)
        WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
          AND t.status IN ['pending', 'in_progress']
        RETURN t.id as id, t.description as content, t.created_at as created_at,
               'active_task' as entry_type, t.assigned_to as agent

        UNION

        // Recent critical notifications
        MATCH (n:Notification {agent: $agent, read: false})
        WHERE n.type IN ['task_completed', 'task_failed', 'critical_alert']
        RETURN n.id as id, n.summary as content, n.created_at as created_at,
               'notification' as entry_type, $agent as agent

        UNION

        // Recent high-confidence beliefs
        MATCH (b:Belief)
        WHERE (b.agent = $agent OR b.agent = 'shared')
          AND b.state = 'active'
          AND b.confidence >= 0.8
        RETURN b.id as id, b.content as content, b.created_at as created_at,
               'belief' as entry_type, b.agent as agent

        ORDER BY created_at DESC
        LIMIT 50
        """

        async with self._session() as session:
            if session is None:
                return []

            result = await session.run(cypher, agent=self.agent_name)
            records = await result.data()
            return records

    async def _load_warm_tier(self) -> None:
        """
        Load warm tier on-demand (lazy loading).

        Warm tier contains:
        - Recent completed tasks
        - Recent notifications
        - Medium-confidence beliefs
        """
        async with self._warm_lock:
            if self._warm_loaded or not self._stats.neo4j_available:
                return

            try:
                entries = await self._execute_with_timeout(
                    self._fetch_warm_tier_entries,
                    self.WARM_LOAD_TIMEOUT
                )

                total_tokens = 0
                for entry_data in entries:
                    tokens = estimate_tokens(entry_data.get("content", ""))
                    if total_tokens + tokens > self.WARM_TOKEN_LIMIT:
                        break

                    entry = MemoryEntry(
                        id=entry_data["id"],
                        content=entry_data["content"],
                        tier=MemoryTier.WARM,
                        token_count=tokens,
                        created_at=entry_data.get("created_at", datetime.now(timezone.utc)),
                        last_accessed=datetime.now(timezone.utc),
                        agent=entry_data.get("agent", self.agent_name),
                        entry_type=entry_data.get("entry_type", "general")
                    )

                    self._warm_cache[entry.id] = entry
                    total_tokens += tokens

                self._stats.warm.token_count = total_tokens
                self._stats.warm.entry_count = len(self._warm_cache)
                self._stats.warm.load_count += 1
                self._stats.warm.last_load = datetime.now(timezone.utc)
                self._warm_loaded = True

                logger.info(
                    f"Warm tier loaded: {self._stats.warm.entry_count} entries, "
                    f"{self._stats.warm.token_count} tokens"
                )

            except Neo4jTimeoutError:
                logger.warning("Warm tier load timed out, will retry on next access")
                self._stats.warm.miss_count += 1
            except Exception as e:
                logger.error(f"Failed to load warm tier: {e}")

    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def _fetch_warm_tier_entries(self) -> List[Dict[str, Any]]:
        """Fetch warm tier entries from Neo4j."""
        cypher = """
        // Recent completed tasks (last 24 hours)
        MATCH (t:Task)
        WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
          AND t.status = 'completed'
          AND t.completed_at >= datetime() - duration('P1D')
        RETURN t.id as id, t.description as content, t.completed_at as created_at,
               'completed_task' as entry_type, t.assigned_to as agent

        UNION

        // Recent notifications (last 24 hours)
        MATCH (n:Notification {agent: $agent})
        WHERE n.created_at >= datetime() - duration('P1D')
        RETURN n.id as id, n.summary as content, n.created_at as created_at,
               'notification' as entry_type, $agent as agent

        UNION

        // Medium-confidence beliefs
        MATCH (b:Belief)
        WHERE (b.agent = $agent OR b.agent = 'shared')
          AND b.state = 'active'
          AND b.confidence >= 0.5 AND b.confidence < 0.8
        RETURN b.id as id, b.content as content, b.created_at as created_at,
               'belief' as entry_type, b.agent as agent

        ORDER BY created_at DESC
        LIMIT 30
        """

        async with self._session() as session:
            if session is None:
                return []

            result = await session.run(cypher, agent=self.agent_name)
            records = await result.data()
            return records

    async def _load_cold_tier(self) -> None:
        """
        Load cold tier with timeout protection.

        Cold tier contains:
        - Older completed tasks (last 7 days)
        - Archived beliefs
        - Historical context
        """
        async with self._cold_lock:
            if self._cold_loaded or not self._stats.neo4j_available:
                return

            try:
                entries = await self._execute_with_timeout(
                    self._fetch_cold_tier_entries,
                    self.COLD_LOAD_TIMEOUT
                )

                total_tokens = 0
                for entry_data in entries:
                    tokens = estimate_tokens(entry_data.get("content", ""))
                    if total_tokens + tokens > self.COLD_TOKEN_LIMIT:
                        break

                    entry = MemoryEntry(
                        id=entry_data["id"],
                        content=entry_data["content"],
                        tier=MemoryTier.COLD,
                        token_count=tokens,
                        created_at=entry_data.get("created_at", datetime.now(timezone.utc)),
                        last_accessed=datetime.now(timezone.utc),
                        agent=entry_data.get("agent", self.agent_name),
                        entry_type=entry_data.get("entry_type", "general")
                    )

                    self._cold_cache[entry.id] = entry
                    total_tokens += tokens

                self._stats.cold.token_count = total_tokens
                self._stats.cold.entry_count = len(self._cold_cache)
                self._stats.cold.load_count += 1
                self._stats.cold.last_load = datetime.now(timezone.utc)
                self._cold_loaded = True

                logger.info(
                    f"Cold tier loaded: {self._stats.cold.entry_count} entries, "
                    f"{self._stats.cold.token_count} tokens"
                )

            except Neo4jTimeoutError:
                logger.warning("Cold tier load timed out, will retry on next access")
                self._stats.cold.miss_count += 1
            except Exception as e:
                logger.error(f"Failed to load cold tier: {e}")

    @retry_with_backoff(max_retries=1, base_delay=0.1)
    async def _fetch_cold_tier_entries(self) -> List[Dict[str, Any]]:
        """Fetch cold tier entries from Neo4j."""
        cypher = """
        // Older completed tasks (7-30 days)
        MATCH (t:Task)
        WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
          AND t.status = 'completed'
          AND t.completed_at >= datetime() - duration('P7D')
          AND t.completed_at < datetime() - duration('P1D')
        RETURN t.id as id, t.description as content, t.completed_at as created_at,
               'historical_task' as entry_type, t.assigned_to as agent

        UNION

        // Archived beliefs
        MATCH (b:Belief)
        WHERE (b.agent = $agent OR b.agent = 'shared')
          AND b.state = 'archived'
        RETURN b.id as id, b.content as content, b.created_at as created_at,
               'archived_belief' as entry_type, b.agent as agent

        ORDER BY created_at DESC
        LIMIT 20
        """

        async with self._session() as session:
            if session is None:
                return []

            result = await session.run(cypher, agent=self.agent_name)
            records = await result.data()
            return records

    # ========================================================================
    # Public API
    # ========================================================================

    async def get_memory_context(self, include_warm: bool = False, include_cold: bool = False) -> str:
        """
        Get formatted memory context for the agent.

        Args:
            include_warm: Whether to include warm tier
            include_cold: Whether to include cold tier

        Returns:
            Formatted memory context string
        """
        sections = []

        # Always include hot tier
        hot_content = await self._format_tier_content(MemoryTier.HOT)
        if hot_content:
            sections.append(f"## Current Context\n{hot_content}")

        # Include warm tier if requested
        if include_warm:
            if not self._warm_loaded:
                await self._load_warm_tier()
            warm_content = await self._format_tier_content(MemoryTier.WARM)
            if warm_content:
                sections.append(f"## Recent Activity\n{warm_content}")

        # Include cold tier if requested
        if include_cold:
            if not self._cold_loaded:
                await self._load_cold_tier()
            cold_content = await self._format_tier_content(MemoryTier.COLD)
            if cold_content:
                sections.append(f"## Historical Context\n{cold_content}")

        return "\n\n".join(sections)

    async def _format_tier_content(self, tier: MemoryTier) -> str:
        """Format cache content for a tier."""
        if tier == MemoryTier.HOT:
            entries = list(self._hot_cache.values())
        elif tier == MemoryTier.WARM:
            entries = list(self._warm_cache.values())
        elif tier == MemoryTier.COLD:
            entries = list(self._cold_cache.values())
        else:
            return ""

        if not entries:
            return ""

        # Sort by recency
        entries.sort(key=lambda e: e.last_accessed, reverse=True)

        formatted = []
        for entry in entries:
            entry.touch()
            timestamp = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else ""
            formatted.append(f"[{entry.entry_type}] {timestamp}: {entry.content}")

        return "\n".join(formatted)

    async def query_archive(
        self,
        query_text: Optional[str] = None,
        entry_type: Optional[str] = None,
        days: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query archive tier (never loaded into memory).

        Args:
            query_text: Optional text to search for
            entry_type: Optional entry type filter
            days: How many days back to search
            limit: Maximum results

        Returns:
            List of matching entries
        """
        if not self._stats.neo4j_available:
            logger.warning("Neo4j unavailable, cannot query archive")
            return []

        try:
            return await self._execute_with_timeout(
                self._fetch_archive_entries,
                self.COLD_LOAD_TIMEOUT,
                query_text,
                entry_type,
                days,
                limit
            )
        except Neo4jTimeoutError:
            logger.warning("Archive query timed out")
            return []

    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def _fetch_archive_entries(
        self,
        query_text: Optional[str],
        entry_type: Optional[str],
        days: int,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fetch archive entries from Neo4j."""
        # Build dynamic query
        conditions = ["created_at >= datetime() - duration('P' + $days + 'D')"]
        params: Dict[str, Any] = {"agent": self.agent_name, "days": days, "limit": limit}

        if entry_type:
            conditions.append("entry_type = $entry_type")
            params["entry_type"] = entry_type

        if query_text:
            # Use full-text search if available
            cypher = """
            CALL db.index.fulltext.queryNodes('knowledge_content', $query_text)
            YIELD node, score
            WHERE (node.agent = $agent OR node.agent = 'shared')
              AND node.created_at >= datetime() - duration('P' + $days + 'D')
            RETURN node.id as id, node.content as content,
                   node.created_at as created_at, labels(node)[0] as entry_type,
                   node.agent as agent, score
            ORDER BY score DESC
            LIMIT $limit
            """
            params["query_text"] = query_text
        else:
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            cypher = f"""
            MATCH (n)
            WHERE (n:Task OR n:Belief OR n:Research OR n:Content OR n:Analysis)
              AND (n.agent = $agent OR n.agent = 'shared')
              AND n.created_at >= datetime() - duration('P' + $days + 'D')
            RETURN n.id as id, n.content as content,
                   n.created_at as created_at, labels(n)[0] as entry_type,
                   n.agent as agent
            ORDER BY n.created_at DESC
            LIMIT $limit
            """

        async with self._session() as session:
            if session is None:
                return []

            result = await session.run(cypher, **params)
            records = await result.data()
            self._stats.archive.hit_count += len(records)
            return records

    async def add_entry(
        self,
        content: str,
        entry_type: str,
        tier: MemoryTier = MemoryTier.HOT,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a new memory entry.

        Args:
            content: Entry content
            entry_type: Type of entry
            tier: Target tier
            confidence: Confidence level (0-1)
            metadata: Optional metadata

        Returns:
            Entry ID
        """
        entry_id = f"{self.agent_name}_{int(time.time() * 1000)}"
        tokens = estimate_tokens(content)

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            tier=tier,
            token_count=tokens,
            created_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            agent=self.agent_name,
            entry_type=entry_type
        )

        # Store in appropriate cache
        if tier == MemoryTier.HOT:
            async with self._hot_lock:
                # Evict oldest if needed
                while (self._stats.hot.token_count + tokens > self.HOT_TOKEN_LIMIT
                       and self._hot_cache):
                    oldest = min(self._hot_cache.values(), key=lambda e: e.last_accessed)
                    del self._hot_cache[oldest.id]
                    self._stats.hot.token_count -= oldest.token_count
                    self._stats.hot.entry_count -= 1

                self._hot_cache[entry_id] = entry
                self._stats.hot.token_count += tokens
                self._stats.hot.entry_count += 1

        elif tier == MemoryTier.WARM:
            async with self._warm_lock:
                self._warm_cache[entry_id] = entry
                self._stats.warm.token_count += tokens
                self._stats.warm.entry_count += 1

        elif tier == MemoryTier.COLD:
            async with self._cold_lock:
                self._cold_cache[entry_id] = entry
                self._stats.cold.token_count += tokens
                self._stats.cold.entry_count += 1

        # Persist to Neo4j
        if self._stats.neo4j_available:
            await self._persist_entry(entry, confidence, metadata)

        return entry_id

    async def _persist_entry(
        self,
        entry: MemoryEntry,
        confidence: float,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Persist entry to Neo4j."""
        cypher = """
        CREATE (e:MemoryEntry {
            id: $id,
            content: $content,
            tier: $tier,
            token_count: $token_count,
            agent: $agent,
            entry_type: $entry_type,
            confidence: $confidence,
            created_at: $created_at,
            metadata: $metadata
        })
        RETURN e.id as id
        """

        async with self._session() as session:
            if session is None:
                return

            try:
                await session.run(
                    cypher,
                    id=entry.id,
                    content=entry.content,
                    tier=entry.tier.value,
                    token_count=entry.token_count,
                    agent=entry.agent,
                    entry_type=entry.entry_type,
                    confidence=confidence,
                    created_at=entry.created_at,
                    metadata=str(metadata) if metadata else None
                )
            except _Neo4jError as e:
                logger.error(f"Failed to persist entry: {e}")

    async def get_stats(self) -> MemoryStats:
        """Get current memory statistics."""
        return self._stats

    async def invalidate_tier(self, tier: MemoryTier) -> None:
        """
        Invalidate a memory tier, forcing reload on next access.

        Args:
            tier: Tier to invalidate
        """
        if tier == MemoryTier.HOT:
            async with self._hot_lock:
                self._hot_cache.clear()
                self._stats.hot = TierStats(max_tokens=self.HOT_TOKEN_LIMIT)
        elif tier == MemoryTier.WARM:
            async with self._warm_lock:
                self._warm_cache.clear()
                self._warm_loaded = False
                self._stats.warm = TierStats(max_tokens=self.WARM_TOKEN_LIMIT)
        elif tier == MemoryTier.COLD:
            async with self._cold_lock:
                self._cold_cache.clear()
                self._cold_loaded = False
                self._stats.cold = TierStats(max_tokens=self.COLD_TOKEN_LIMIT)

    async def refresh(self) -> None:
        """Refresh all tiers from Neo4j."""
        await self.invalidate_tier(MemoryTier.HOT)
        await self.invalidate_tier(MemoryTier.WARM)
        await self.invalidate_tier(MemoryTier.COLD)
        await self._load_hot_tier()

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self._owns_driver and self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("MemoryManager Neo4j connection closed")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# ============================================================================
# Integration with OperationalMemory
# ============================================================================

class MemoryManagerFactory:
    """
    Factory for creating MemoryManager instances.

    Ensures proper integration with OperationalMemory and shared connections.
    """

    _instances: Dict[str, MemoryManager] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_manager(
        cls,
        agent_name: str,
        operational_memory: Optional[Any] = None,
        **kwargs
    ) -> MemoryManager:
        """
        Get or create a MemoryManager for an agent.

        Args:
            agent_name: Name of the agent
            operational_memory: Optional shared OperationalMemory
            **kwargs: Additional arguments for MemoryManager

        Returns:
            MemoryManager instance
        """
        async with cls._lock:
            if agent_name not in cls._instances:
                manager = MemoryManager(
                    agent_name=agent_name,
                    operational_memory=operational_memory,
                    **kwargs
                )
                await manager.initialize()
                cls._instances[agent_name] = manager

            return cls._instances[agent_name]

    @classmethod
    async def close_all(cls) -> None:
        """Close all managed MemoryManager instances."""
        async with cls._lock:
            for manager in cls._instances.values():
                await manager.close()
            cls._instances.clear()


# ============================================================================
# Convenience Functions
# ============================================================================

async def create_memory_manager(
    agent_name: str,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: Optional[str] = None,
    operational_memory: Optional[Any] = None
) -> MemoryManager:
    """
    Create and initialize a MemoryManager.

    Args:
        agent_name: Name of the agent
        neo4j_uri: Neo4j URI
        neo4j_username: Neo4j username
        neo4j_password: Neo4j password
        operational_memory: Optional shared OperationalMemory

    Returns:
        Initialized MemoryManager
    """
    manager = MemoryManager(
        agent_name=agent_name,
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        operational_memory=operational_memory
    )
    await manager.initialize()
    return manager


async def get_kublai_memory(
    operational_memory: Optional[Any] = None,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_password: Optional[str] = None
) -> MemoryManager:
    """
    Get MemoryManager for Kublai (squad lead).

    Kublai gets full access including warm tier by default.
    """
    return await create_memory_manager(
        agent_name="kublai",
        neo4j_uri=neo4j_uri,
        neo4j_password=neo4j_password,
        operational_memory=operational_memory
    )


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    import os

    async def example():
        """Example usage of MemoryManager."""
        # Configure logging
        logging.basicConfig(level=logging.INFO)

        print("MemoryManager Example")
        print("=" * 50)

        # Get Neo4j credentials from environment
        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_password = os.environ.get("NEO4J_PASSWORD")

        # Create memory manager for Kublai
        async with MemoryManager(
            agent_name="kublai",
            neo4j_uri=neo4j_uri,
            neo4j_password=neo4j_password,
            fallback_mode=True
        ) as memory:

            # Get memory context (hot tier only by default)
            context = await memory.get_memory_context()
            print(f"\nHot Tier Context:\n{context}")

            # Get full context with warm tier
            full_context = await memory.get_memory_context(
                include_warm=True,
                include_cold=False
            )
            print(f"\nFull Context (with warm):\n{full_context[:500]}...")

            # Query archive for specific information
            archive_results = await memory.query_archive(
                query_text="async patterns",
                days=7,
                limit=5
            )
            print(f"\nArchive Results: {len(archive_results)} entries")

            # Add a new memory entry
            entry_id = await memory.add_entry(
                content="User requested analysis of async patterns in Python",
                entry_type="task_request",
                tier=MemoryTier.HOT,
                confidence=1.0
            )
            print(f"\nAdded entry: {entry_id}")

            # Get stats
            stats = await memory.get_stats()
            print(f"\nMemory Stats:")
            print(f"  Hot: {stats.hot.entry_count} entries, {stats.hot.token_count} tokens")
            print(f"  Warm: {stats.warm.entry_count} entries, {stats.warm.token_count} tokens")
            print(f"  Cold: {stats.cold.entry_count} entries, {stats.cold.token_count} tokens")
            print(f"  Neo4j Available: {stats.neo4j_available}")

    # Run example
    asyncio.run(example())
