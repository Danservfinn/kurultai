"""
Resilient Neo4j Connection Wrapper

Provides:
- Connection pooling with health checking
- Retry logic with exponential backoff
- Graceful degradation to fallback storage
- Circuit breaker pattern for failing connections
"""

import os
import time
import json
import logging
import sqlite3
import threading
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

# Configure logging
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state for circuit breaker pattern."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class ConnectionStats:
    """Statistics for connection monitoring."""
    total_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    retry_attempts: int = 0
    circuit_opens: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    average_response_ms: float = 0.0


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    half_open_max_calls: int = 3


class FallbackStorage:
    """
    SQLite-based fallback storage when Neo4j is unavailable.
    
    Provides basic CRUD operations for agent memories and tasks.
    Data is synchronized back to Neo4j when connection is restored.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize fallback storage.
        
        Args:
            db_path: Path to SQLite database. Defaults to workspace/memory/fallback_neo4j.db
        """
        if db_path is None:
            workspace = os.environ.get('WORKSPACE', '/data/workspace/souls/main')
            db_path = os.path.join(workspace, 'memory', 'fallback_neo4j.db')
        
        self.db_path = db_path
        self._local = threading.local()
        self._ensure_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def _ensure_db(self):
        """Ensure database schema exists."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Agent memories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_memories (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source_task_id TEXT,
                related_agents TEXT,  -- JSON array
                tags TEXT,  -- JSON array
                importance REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                synced_to_neo4j BOOLEAN DEFAULT 0,
                neo4j_sync_attempts INTEGER DEFAULT 0
            )
        ''')
        
        # Tasks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                description TEXT,
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                assigned_to TEXT,
                delegated_by TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                result TEXT,  -- JSON
                synced_to_neo4j BOOLEAN DEFAULT 0
            )
        ''')
        
        # Agent state table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_state (
                agent_name TEXT PRIMARY KEY,
                status TEXT,
                current_task TEXT,
                last_heartbeat TEXT,
                metadata TEXT  -- JSON
            )
        ''')
        
        # Sync queue for when Neo4j comes back
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                record_id TEXT NOT NULL,
                operation TEXT NOT NULL,  -- CREATE, UPDATE, DELETE
                created_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT
            )
        ''')
        
        # Indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_agent ON agent_memories(agent_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_type ON agent_memories(memory_type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sync_queue_pending ON sync_queue(retry_count, created_at)
        ''')
        
        conn.commit()
    
    def add_memory(self, memory_data: Dict[str, Any]) -> bool:
        """Add a memory entry to fallback storage."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO agent_memories 
                (id, agent_name, memory_type, content, source_task_id, related_agents, 
                 tags, importance, created_at, synced_to_neo4j)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                memory_data.get('id'),
                memory_data.get('agent_name'),
                memory_data.get('memory_type'),
                memory_data.get('content'),
                memory_data.get('source_task_id'),
                json.dumps(memory_data.get('related_agents', [])),
                json.dumps(memory_data.get('tags', [])),
                memory_data.get('importance', 0.5),
                memory_data.get('created_at', datetime.utcnow().isoformat()),
                False
            ))
            
            # Add to sync queue
            cursor.execute('''
                INSERT INTO sync_queue (table_name, record_id, operation, created_at)
                VALUES (?, ?, ?, ?)
            ''', ('agent_memories', memory_data.get('id'), 'CREATE', datetime.utcnow().isoformat()))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add memory to fallback storage: {e}")
            return False
    
    def get_agent_memories(self, agent_name: str, memory_type: Optional[str] = None,
                          limit: int = 10) -> List[Dict[str, Any]]:
        """Get memories for an agent from fallback storage."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if memory_type:
                cursor.execute('''
                    SELECT * FROM agent_memories 
                    WHERE agent_name = ? AND memory_type = ?
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                ''', (agent_name, memory_type, limit))
            else:
                cursor.execute('''
                    SELECT * FROM agent_memories 
                    WHERE agent_name = ?
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                ''', (agent_name, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get memories from fallback storage: {e}")
            return []
    
    def get_pending_sync_items(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get items pending sync to Neo4j."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM sync_queue 
                WHERE retry_count < 5
                ORDER BY created_at ASC
                LIMIT ?
            ''', (limit,))
            
            return [self._row_to_dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pending sync items: {e}")
            return []
    
    def mark_synced(self, table_name: str, record_id: str) -> bool:
        """Mark a record as successfully synced to Neo4j."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f'''
                UPDATE {table_name} SET synced_to_neo4j = 1 WHERE id = ?
            ''', (record_id,))
            
            cursor.execute('''
                DELETE FROM sync_queue WHERE table_name = ? AND record_id = ?
            ''', (table_name, record_id))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark record as synced: {e}")
            return False
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert SQLite row to dictionary."""
        result = dict(row)
        # Parse JSON fields
        for key in ['related_agents', 'tags', 'result', 'metadata']:
            if key in result and result[key]:
                try:
                    result[key] = json.loads(result[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fallback storage statistics."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute('SELECT COUNT(*) FROM agent_memories')
            stats['total_memories'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM agent_memories WHERE synced_to_neo4j = 0')
            stats['unsynced_memories'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM tasks')
            stats['total_tasks'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM sync_queue')
            stats['pending_sync'] = cursor.fetchone()[0]
            
            return stats
        except Exception as e:
            logger.error(f"Failed to get fallback stats: {e}")
            return {}


class ResilientNeo4jConnection:
    """
    Resilient Neo4j connection wrapper with retry, circuit breaker, and fallback.
    
    Features:
    - Automatic retry with exponential backoff
    - Circuit breaker pattern to prevent cascading failures
    - Fallback to SQLite when Neo4j is unavailable
    - Connection health monitoring
    - Graceful degradation
    """
    
    def __init__(
        self,
        uri: Optional[str] = None,
        username: str = "neo4j",
        password: Optional[str] = None,
        fallback_enabled: bool = True,
        retry_config: Optional[RetryConfig] = None,
        circuit_config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize resilient Neo4j connection.
        
        Args:
            uri: Neo4j bolt URI (defaults to NEO4J_URI env var)
            username: Neo4j username
            password: Neo4j password (defaults to NEO4J_PASSWORD env var)
            fallback_enabled: Whether to enable SQLite fallback
            retry_config: Retry configuration
            circuit_config: Circuit breaker configuration
        """
        self.uri = uri or os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        self.username = username
        self.password = password or os.environ.get('NEO4J_PASSWORD')
        
        self.retry_config = retry_config or RetryConfig()
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        
        # Connection state
        self._driver = None
        self._state = ConnectionState.UNAVAILABLE
        self._state_lock = threading.RLock()
        self._failure_count = 0
        self._circuit_opened_at: Optional[datetime] = None
        self._half_open_calls = 0
        
        # Statistics
        self.stats = ConnectionStats()
        
        # Fallback storage
        self.fallback = FallbackStorage() if fallback_enabled else None
        self._fallback_mode = False
        
        # Try initial connection
        self._try_connect()
    
    def _try_connect(self) -> bool:
        """Attempt to connect to Neo4j."""
        try:
            from neo4j import GraphDatabase
            
            if self._driver:
                try:
                    self._driver.close()
                except:
                    pass
            
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                connection_timeout=10,
                max_connection_pool_size=10
            )
            
            # Verify connectivity
            self._driver.verify_connectivity()
            
            with self._state_lock:
                self._state = ConnectionState.HEALTHY
                self._failure_count = 0
                self._circuit_opened_at = None
                self._half_open_calls = 0
                self._fallback_mode = False
            
            self.stats.successful_connections += 1
            self.stats.last_success = datetime.now()
            
            logger.info(f"✅ Neo4j connected: {self.uri}")
            
            # Sync any pending fallback data
            if self.fallback:
                self._sync_fallback_data()
            
            return True
            
        except ImportError:
            logger.error("❌ neo4j package not installed")
            self._set_fallback_mode("neo4j package not installed")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Neo4j connection failed: {e}")
            self._handle_failure()
            return False
    
    def _handle_failure(self):
        """Handle connection failure with circuit breaker logic."""
        with self._state_lock:
            self._failure_count += 1
            self.stats.failed_connections += 1
            self.stats.last_failure = datetime.now()
            
            # Check if we should open the circuit
            if self._failure_count >= self.circuit_config.failure_threshold:
                if self._state != ConnectionState.CIRCUIT_OPEN:
                    self._state = ConnectionState.CIRCUIT_OPEN
                    self._circuit_opened_at = datetime.now()
                    self.stats.circuit_opens += 1
                    logger.warning("🔴 Circuit breaker OPEN - Neo4j marked as unavailable")
                    self._set_fallback_mode("circuit breaker opened")
    
    def _set_fallback_mode(self, reason: str):
        """Enable fallback mode."""
        self._fallback_mode = True
        with self._state_lock:
            self._state = ConnectionState.DEGRADED
        logger.info(f"📦 Fallback mode enabled: {reason}")
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset."""
        with self._state_lock:
            if self._state != ConnectionState.CIRCUIT_OPEN:
                return False
            
            if self._circuit_opened_at is None:
                return True
            
            elapsed = (datetime.now() - self._circuit_opened_at).total_seconds()
            return elapsed >= self.circuit_config.recovery_timeout
    
    def _get_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff."""
        delay = self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt)
        delay = min(delay, self.retry_config.max_delay)
        
        if self.retry_config.jitter:
            import random
            delay = delay * (0.5 + random.random())
        
        return delay
    
    def execute(self, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute a Neo4j operation with retry and fallback.
        
        Args:
            operation: Function to execute (receives driver as first arg)
            *args, **kwargs: Arguments to pass to operation
            
        Returns:
            Operation result, or fallback result if Neo4j unavailable
        """
        self.stats.total_attempts += 1
        
        # Check if we should try to reset circuit breaker
        if self._state == ConnectionState.CIRCUIT_OPEN and self._should_attempt_reset():
            with self._state_lock:
                self._state = ConnectionState.DEGRADED
                self._half_open_calls = 0
                logger.info("🟡 Circuit breaker HALF-OPEN - attempting recovery")
        
        # If circuit is open, go straight to fallback
        if self._state == ConnectionState.CIRCUIT_OPEN:
            return self._fallback_execute(operation, *args, **kwargs)
        
        # Attempt operation with retries
        last_exception = None
        for attempt in range(self.retry_config.max_retries):
            try:
                # Check if we need to reconnect
                if self._driver is None or self._state == ConnectionState.UNAVAILABLE:
                    if not self._try_connect():
                        raise Exception("Failed to connect to Neo4j")
                
                # Execute operation
                start = time.time()
                result = operation(self._driver, *args, **kwargs)
                elapsed_ms = (time.time() - start) * 1000
                
                # Update stats
                self.stats.average_response_ms = (
                    (self.stats.average_response_ms * (self.stats.total_attempts - 1) + elapsed_ms)
                    / self.stats.total_attempts
                )
                
                # Success - reset failure count
                with self._state_lock:
                    if self._state == ConnectionState.DEGRADED:
                        self._half_open_calls += 1
                        if self._half_open_calls >= self.circuit_config.half_open_max_calls:
                            self._state = ConnectionState.HEALTHY
                            self._failure_count = 0
                            logger.info("🟢 Circuit breaker CLOSED - Neo4j recovered")
                    else:
                        self._failure_count = 0
                
                return result
                
            except Exception as e:
                last_exception = e
                self.stats.retry_attempts += 1
                
                # Check if it's a transient error
                if self._is_transient_error(e):
                    if attempt < self.retry_config.max_retries - 1:
                        delay = self._get_delay(attempt)
                        logger.warning(f"Transient error, retrying in {delay:.2f}s: {e}")
                        time.sleep(delay)
                        continue
                
                # Non-transient error or max retries exceeded
                self._handle_failure()
                break
        
        # All retries failed, use fallback
        logger.error(f"Neo4j operation failed after {self.retry_config.max_retries} retries: {last_exception}")
        return self._fallback_execute(operation, *args, **kwargs)
    
    def _is_transient_error(self, error: Exception) -> bool:
        """Check if an error is transient and worth retrying."""
        error_str = str(error).lower()
        transient_keywords = [
            'timeout', 'transient', 'temporarily', 'unavailable',
            'pool', 'connection', 'network', 'reset'
        ]
        return any(kw in error_str for kw in transient_keywords)
    
    def _fallback_execute(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation using fallback storage."""
        if self.fallback is None:
            raise Exception("Neo4j unavailable and fallback disabled")
        
        # Return fallback indicator - caller should handle
        return {
            '_fallback': True,
            '_fallback_reason': 'neo4j_unavailable',
            '_fallback_storage': self.fallback
        }
    
    def _sync_fallback_data(self):
        """Sync pending data from fallback storage to Neo4j."""
        if not self.fallback:
            return
        
        pending = self.fallback.get_pending_sync_items(limit=100)
        if not pending:
            return
        
        logger.info(f"🔄 Syncing {len(pending)} items from fallback to Neo4j...")
        
        synced_count = 0
        for item in pending:
            try:
                # Attempt to sync based on table and operation
                table = item['table_name']
                record_id = item['record_id']
                
                if table == 'agent_memories':
                    # Get full record from fallback
                    conn = self.fallback._get_connection()
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM agent_memories WHERE id = ?', (record_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        # Sync to Neo4j
                        memory_data = self.fallback._row_to_dict(row)
                        self._sync_memory_to_neo4j(memory_data)
                        self.fallback.mark_synced(table, record_id)
                        synced_count += 1
                        
            except Exception as e:
                logger.error(f"Failed to sync item {item['id']}: {e}")
        
        if synced_count > 0:
            logger.info(f"✅ Synced {synced_count} items to Neo4j")
    
    def _sync_memory_to_neo4j(self, memory_data: Dict[str, Any]):
        """Sync a memory record to Neo4j."""
        def do_sync(driver):
            with driver.session() as session:
                session.run("""
                    MERGE (m:AgentMemory {id: $id})
                    SET m.agent_name = $agent_name,
                        m.memory_type = $memory_type,
                        m.content = $content,
                        m.source_task_id = $source_task_id,
                        m.importance = $importance,
                        m.created_at = $created_at
                """, **memory_data)
        
        # Direct execution without fallback
        if self._driver and self._state in [ConnectionState.HEALTHY, ConnectionState.DEGRADED]:
            do_sync(self._driver)
    
    @contextmanager
    def session(self):
        """
        Context manager for Neo4j sessions with fallback support.
        
        Usage:
            with conn.session() as session:
                if session.is_fallback:
                    # Use fallback storage
                else:
                    # Use Neo4j session
        """
        fallback_result = self.execute(lambda d: None)
        
        if isinstance(fallback_result, dict) and fallback_result.get('_fallback'):
            # Return fallback session wrapper
            yield FallbackSession(self.fallback)
        else:
            # Return real Neo4j session
            if self._driver:
                real_session = self._driver.session()
                try:
                    yield real_session
                finally:
                    real_session.close()
            else:
                yield FallbackSession(self.fallback)
    
    def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return self._state == ConnectionState.HEALTHY
    
    def is_fallback_mode(self) -> bool:
        """Check if running in fallback mode."""
        return self._fallback_mode
    
    def get_status(self) -> Dict[str, Any]:
        """Get connection status and statistics."""
        return {
            'state': self._state.value,
            'uri': self.uri,
            'fallback_mode': self._fallback_mode,
            'fallback_enabled': self.fallback is not None,
            'stats': {
                'total_attempts': self.stats.total_attempts,
                'successful_connections': self.stats.successful_connections,
                'failed_connections': self.stats.failed_connections,
                'retry_attempts': self.stats.retry_attempts,
                'circuit_opens': self.stats.circuit_opens,
                'average_response_ms': round(self.stats.average_response_ms, 2),
                'last_success': self.stats.last_success.isoformat() if self.stats.last_success else None,
                'last_failure': self.stats.last_failure.isoformat() if self.stats.last_failure else None,
            },
            'fallback_stats': self.fallback.get_stats() if self.fallback else None
        }
    
    def close(self):
        """Close the connection."""
        if self._driver:
            try:
                self._driver.close()
            except:
                pass
            self._driver = None


class FallbackSession:
    """Session wrapper for fallback storage that mimics Neo4j session API."""
    
    def __init__(self, fallback_storage: FallbackStorage):
        self._fallback = fallback_storage
        self.is_fallback = True
    
    def run(self, query: str, **parameters) -> 'FallbackResult':
        """
        Execute a query against fallback storage.
        
        Note: Only basic queries are supported. Complex Cypher will fail.
        """
        # Parse simple queries
        query_lower = query.lower()
        
        if 'agent_memories' in query_lower or 'agentmemory' in query_lower:
            # Handle memory queries
            agent_name = parameters.get('agent_name')
            if agent_name:
                memories = self._fallback.get_agent_memories(
                    agent_name,
                    parameters.get('memory_type'),
                    parameters.get('limit', 10)
                )
                return FallbackResult(memories)
        
        # Default: return empty result
        return FallbackResult([])
    
    def close(self):
        """No-op for fallback session."""
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


class FallbackResult:
    """Result wrapper that mimics Neo4j result API."""
    
    def __init__(self, data: List[Dict[str, Any]]):
        self._data = data
        self._index = 0
    
    def single(self) -> Optional[Dict[str, Any]]:
        """Get single result."""
        if self._data:
            return self._data[0]
        return None
    
    def __iter__(self):
        return iter(self._data)
    
    def __next__(self):
        if self._index >= len(self._data):
            raise StopIteration
        item = self._data[self._index]
        self._index += 1
        return item


# Convenience function
def get_resilient_connection(
    uri: Optional[str] = None,
    username: str = "neo4j",
    password: Optional[str] = None,
    fallback_enabled: bool = True
) -> ResilientNeo4jConnection:
    """
    Get or create a resilient Neo4j connection.
    
    Args:
        uri: Neo4j bolt URI
        username: Neo4j username
        password: Neo4j password
        fallback_enabled: Whether to enable SQLite fallback
        
    Returns:
        ResilientNeo4jConnection instance
    """
    return ResilientNeo4jConnection(
        uri=uri,
        username=username,
        password=password,
        fallback_enabled=fallback_enabled
    )
