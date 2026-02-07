"""
MigrationManager - Neo4j Schema Migration System

Provides schema versioning, migration tracking, and rollback capabilities
for the OpenClaw multi-agent platform.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from contextlib import contextmanager

from neo4j import GraphDatabase, Driver, Session, Transaction
from neo4j.exceptions import Neo4jError, ServiceUnavailable, AuthError


logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Base exception for migration errors."""
    pass


class MigrationConnectionError(MigrationError):
    """Raised when connection to Neo4j fails."""
    pass


class MigrationVersionError(MigrationError):
    """Raised when version conflicts or invalid versions occur."""
    pass


class MigrationExecutionError(MigrationError):
    """Raised when migration execution fails."""
    pass


@dataclass
class MigrationRecord:
    """Represents a registered migration."""
    version: int
    name: str
    up_cypher: str
    down_cypher: str
    description: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class MigrationHistory:
    """Represents a migration execution record."""
    version: int
    name: str
    applied_at: datetime
    execution_time_ms: int
    success: bool
    error_message: Optional[str] = None


class MigrationManager:
    """
    Manages Neo4j schema migrations with versioning, tracking, and rollback support.

    Features:
    - Schema version tracking in Neo4j
    - Up/down migration support
    - Conflict detection
    - Atomic transactions
    - Idempotent migrations
    - Comprehensive logging

    Example:
        manager = MigrationManager("bolt://localhost:7687", "neo4j", "password")

        # Register migrations
        manager.register_migration(1, "initial_schema", up_cypher, down_cypher)

        # Run migrations
        manager.migrate(target_version=1)

        # Rollback if needed
        manager.rollback(steps=1)
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        max_connection_pool_size: int = 10,
        connection_timeout: int = 30
    ):
        """
        Initialize migration manager with Neo4j connection.

        Args:
            neo4j_uri: Neo4j connection URI (e.g., bolt://localhost:7687)
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            max_connection_pool_size: Maximum connection pool size
            connection_timeout: Connection timeout in seconds

        Raises:
            MigrationConnectionError: If connection to Neo4j fails
        """
        self._uri = neo4j_uri
        self._user = neo4j_user
        self._password = neo4j_password
        self._migrations: Dict[int, MigrationRecord] = {}
        self._driver: Optional[Driver] = None

        try:
            self._driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password),
                max_connection_pool_size=max_connection_pool_size,
                connection_timeout=connection_timeout
            )
            # Verify connection
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {neo4j_uri}")
        except ServiceUnavailable as e:
            raise MigrationConnectionError(f"Neo4j service unavailable at {neo4j_uri}: {e}")
        except AuthError as e:
            raise MigrationConnectionError(f"Authentication failed for Neo4j: {e}")
        except Exception as e:
            raise MigrationConnectionError(f"Failed to connect to Neo4j: {e}")

    def close(self):
        """Close the Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    @contextmanager
    def _session(self):
        """Get a Neo4j session context manager."""
        if not self._driver:
            raise MigrationConnectionError("Not connected to Neo4j")

        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    def _ensure_migration_schema(self, session: Session):
        """
        Ensure migration tracking schema exists.
        Creates Migration and MigrationControl nodes if they don't exist.
        """
        # Create constraint for Migration version uniqueness
        try:
            session.run("""
                CREATE CONSTRAINT migration_version_unique IF NOT EXISTS
                FOR (m:Migration) REQUIRE m.version IS UNIQUE
            """)
        except Neo4jError as e:
            # Constraint might already exist with different syntax
            logger.debug(f"Constraint creation note: {e}")

        # Create index for Migration version
        try:
            session.run("""
                CREATE INDEX migration_version_index IF NOT EXISTS
                FOR (m:Migration) ON (m.version)
            """)
        except Neo4jError as e:
            logger.debug(f"Index creation note: {e}")

        # Ensure MigrationControl node exists
        result = session.run("""
            MATCH (mc:MigrationControl)
            RETURN mc.version as version
            LIMIT 1
        """).single()

        if result is None:
            session.run("""
                CREATE (mc:MigrationControl {
                    version: 0,
                    last_updated: datetime(),
                    created_at: datetime()
                })
            """)
            logger.info("Created initial MigrationControl node at version 0")

    def get_current_version(self) -> int:
        """
        Get current schema version from Neo4j.

        Returns:
            Current schema version (0 if no migrations applied)

        Raises:
            MigrationConnectionError: If not connected to Neo4j
        """
        with self._session() as session:
            self._ensure_migration_schema(session)

            result = session.run("""
                MATCH (mc:MigrationControl)
                RETURN mc.version as version
                ORDER BY mc.last_updated DESC
                LIMIT 1
            """).single()

            if result and result["version"] is not None:
                return result["version"]
            return 0

    def get_migration_history(self, limit: int = 100) -> List[MigrationHistory]:
        """
        Get migration execution history.

        Args:
            limit: Maximum number of history records to return

        Returns:
            List of migration history records
        """
        with self._session() as session:
            self._ensure_migration_schema(session)

            results = session.run("""
                MATCH (m:Migration)
                RETURN m.version as version,
                       m.name as name,
                       m.applied_at as applied_at,
                       m.execution_time_ms as execution_time_ms,
                       m.success as success,
                       m.error_message as error_message
                ORDER BY m.applied_at DESC
                LIMIT $limit
            """, limit=limit)

            history = []
            for record in results:
                history.append(MigrationHistory(
                    version=record["version"],
                    name=record["name"],
                    applied_at=record["applied_at"],
                    execution_time_ms=record["execution_time_ms"] or 0,
                    success=record["success"] or False,
                    error_message=record["error_message"]
                ))
            return history

    def register_migration(
        self,
        version: int,
        name: str,
        up_cypher: str,
        down_cypher: str,
        description: str = ""
    ):
        """
        Register a migration.

        Args:
            version: Migration version number (must be positive integer)
            name: Migration name
            up_cypher: Cypher query to apply migration
            down_cypher: Cypher query to rollback migration
            description: Optional description

        Raises:
            MigrationVersionError: If version is invalid or already registered
        """
        if not isinstance(version, int) or version <= 0:
            raise MigrationVersionError(f"Version must be positive integer, got {version}")

        if version in self._migrations:
            raise MigrationVersionError(f"Migration version {version} already registered")

        self._migrations[version] = MigrationRecord(
            version=version,
            name=name,
            up_cypher=up_cypher,
            down_cypher=down_cypher,
            description=description
        )
        logger.debug(f"Registered migration v{version}: {name}")

    @staticmethod
    def _split_cypher(cypher: str) -> list:
        """Split multi-statement Cypher into individual statements.

        Removes comments and splits on semicolons, filtering empty lines.
        """
        statements = []
        for raw_stmt in cypher.split(";"):
            # Remove comment-only lines and whitespace
            lines = []
            for line in raw_stmt.strip().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("//"):
                    lines.append(line)
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt)
        return statements

    @staticmethod
    def _is_schema_statement(stmt: str) -> bool:
        """Check if a Cypher statement is a schema modification (constraint/index)."""
        upper = stmt.strip().upper()
        return any(upper.startswith(prefix) for prefix in [
            "CREATE CONSTRAINT", "DROP CONSTRAINT",
            "CREATE INDEX", "DROP INDEX",
            "CREATE VECTOR INDEX", "DROP VECTOR INDEX",
        ])

    def _apply_migration_split(self, session: Session, migration: MigrationRecord) -> None:
        """Apply a migration, running schema and data statements in separate transactions.

        Neo4j 5.x forbids mixing schema modifications with data modifications
        in the same transaction.
        """
        start_time = datetime.utcnow()

        # Check if already applied
        result = session.run("""
            MATCH (m:Migration {version: $version})
            RETURN m.success as success
        """, version=migration.version).single()

        if result and result["success"]:
            logger.info(f"Migration v{migration.version} already applied, skipping")
            return

        logger.info(f"Applying migration v{migration.version}: {migration.name}")

        statements = self._split_cypher(migration.up_cypher)
        schema_stmts = [s for s in statements if self._is_schema_statement(s)]
        data_stmts = [s for s in statements if not self._is_schema_statement(s)]

        try:
            # Run schema statements one-by-one in auto-commit mode
            for i, stmt in enumerate(schema_stmts, 1):
                logger.debug(f"  Schema {i}/{len(schema_stmts)}: {stmt[:80]}...")
                session.run(stmt)

            # Run data statements in a write transaction
            if data_stmts:
                def run_data(tx):
                    for i, stmt in enumerate(data_stmts, 1):
                        logger.debug(f"  Data {i}/{len(data_stmts)}: {stmt[:80]}...")
                        tx.run(stmt)
                session.execute_write(run_data)

            # Record migration success
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            session.run("""
                MERGE (m:Migration {version: $version})
                SET m.name = $name,
                    m.applied_at = datetime(),
                    m.execution_time_ms = $execution_time,
                    m.success = true,
                    m.error_message = null
            """,
                version=migration.version,
                name=migration.name,
                execution_time=execution_time,
            )

            # Update control version
            session.run("""
                MATCH (mc:MigrationControl)
                SET mc.version = $version,
                    mc.last_updated = datetime()
            """, version=migration.version)

            logger.info(f"Migration v{migration.version} applied in {execution_time}ms")

        except Exception as e:
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            try:
                session.run("""
                    MERGE (m:Migration {version: $version})
                    SET m.name = $name,
                        m.applied_at = datetime(),
                        m.execution_time_ms = $execution_time,
                        m.success = false,
                        m.error_message = $error_message
                """,
                    version=migration.version,
                    name=migration.name,
                    execution_time=execution_time,
                    error_message=str(e)[:500]
                )
            except Exception as record_error:
                logger.warning(f"Failed to record migration failure: {record_error}")

            raise MigrationExecutionError(
                f"Migration v{migration.version} failed: {e}"
            ) from e

    def _apply_migration(self, tx: Transaction, migration: MigrationRecord) -> bool:
        """
        Apply a single migration within a transaction.

        Args:
            tx: Neo4j transaction (provided by execute_write)
            migration: Migration to apply

        Returns:
            True if successful

        Raises:
            MigrationExecutionError: If migration fails
        """
        start_time = datetime.utcnow()

        try:
            # Check if already applied
            existing = tx.run("""
                MATCH (m:Migration {version: $version})
                RETURN m.success as success
            """, version=migration.version).single()

            if existing and existing["success"]:
                logger.info(f"Migration v{migration.version} already applied, skipping")
                return True

            # Execute migration — split multi-statement Cypher into individual statements
            logger.info(f"Applying migration v{migration.version}: {migration.name}")
            statements = self._split_cypher(migration.up_cypher)
            for i, stmt in enumerate(statements, 1):
                logger.debug(f"  Running statement {i}/{len(statements)}: {stmt[:80]}...")
                tx.run(stmt)

            # Record migration
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            tx.run("""
                MERGE (m:Migration {version: $version})
                SET m.name = $name,
                    m.applied_at = datetime(),
                    m.execution_time_ms = $execution_time,
                    m.success = true,
                    m.error_message = null,
                    m.cypher_preview = $cypher_preview
            """,
                version=migration.version,
                name=migration.name,
                execution_time=execution_time,
                cypher_preview=migration.up_cypher[:200] + "..." if len(migration.up_cypher) > 200 else migration.up_cypher
            )

            # Update control version
            tx.run("""
                MATCH (mc:MigrationControl)
                SET mc.version = $version,
                    mc.last_updated = datetime()
            """, version=migration.version)

            logger.info(f"Migration v{migration.version} applied successfully in {execution_time}ms")
            return True

        except Exception as e:
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Record failed migration
            try:
                tx.run("""
                    MERGE (m:Migration {version: $version})
                    SET m.name = $name,
                        m.applied_at = datetime(),
                        m.execution_time_ms = $execution_time,
                        m.success = false,
                        m.error_message = $error_message
                """,
                    version=migration.version,
                    name=migration.name,
                    execution_time=execution_time,
                    error_message=str(e)[:500]
                )
            except Exception as record_error:
                logger.warning(f"Failed to record migration failure: {record_error}")

            raise MigrationExecutionError(
                f"Migration v{migration.version} failed: {e}"
            ) from e

    def _rollback_migration(self, tx: Transaction, migration: MigrationRecord) -> bool:
        """
        Rollback a single migration within a transaction.

        Args:
            tx: Neo4j transaction (provided by execute_write)
            migration: Migration to rollback

        Returns:
            True if successful

        Raises:
            MigrationExecutionError: If rollback fails
        """
        start_time = datetime.utcnow()

        try:
            logger.info(f"Rolling back migration v{migration.version}: {migration.name}")
            statements = self._split_cypher(migration.down_cypher)
            for i, stmt in enumerate(statements, 1):
                logger.debug(f"  Rolling back statement {i}/{len(statements)}: {stmt[:80]}...")
                tx.run(stmt)

            # Remove migration record
            tx.run("""
                MATCH (m:Migration {version: $version})
                DELETE m
            """, version=migration.version)

            # Update control version to previous
            previous_version = migration.version - 1
            tx.run("""
                MATCH (mc:MigrationControl)
                SET mc.version = $version,
                    mc.last_updated = datetime()
            """, version=previous_version)

            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            logger.info(f"Migration v{migration.version} rolled back in {execution_time}ms")
            return True

        except Exception as e:
            raise MigrationExecutionError(
                f"Rollback of v{migration.version} failed: {e}"
            ) from e

    def migrate(self, target_version: Optional[int] = None) -> bool:
        """
        Run migrations up to target version.

        Args:
            target_version: Target version (None = latest registered)

        Returns:
            True if all migrations applied successfully

        Raises:
            MigrationError: If migration fails
        """
        with self._session() as session:
            self._ensure_migration_schema(session)

            current_version = self.get_current_version()

            # Determine target
            if target_version is None:
                target_version = max(self._migrations.keys()) if self._migrations else 0

            if target_version < current_version:
                logger.warning(
                    f"Target version {target_version} is less than current {current_version}. "
                    "Use rollback() to downgrade."
                )
                return False

            if target_version == current_version:
                logger.info(f"Already at version {current_version}")
                return True

            # Get migrations to apply
            versions_to_apply = sorted([
                v for v in self._migrations.keys()
                if current_version < v <= target_version
            ])

            if not versions_to_apply:
                logger.info(f"No migrations to apply (current: {current_version}, target: {target_version})")
                return True

            logger.info(f"Migrating from v{current_version} to v{target_version}")

            # Apply migrations in order
            for version in versions_to_apply:
                migration = self._migrations[version]

                try:
                    self._apply_migration_split(session, migration)
                except Exception as e:
                    logger.error(f"Migration failed at v{version}: {e}")
                    raise

            logger.info(f"Migration complete. Now at v{target_version}")
            return True

    def rollback(self, steps: int = 1) -> bool:
        """
        Rollback migrations.

        Args:
            steps: Number of versions to rollback

        Returns:
            True if rollback successful

        Raises:
            MigrationError: If rollback fails
        """
        if steps < 1:
            raise MigrationVersionError("Steps must be at least 1")

        with self._session() as session:
            self._ensure_migration_schema(session)

            current_version = self.get_current_version()
            target_version = max(0, current_version - steps)

            if current_version == 0:
                logger.info("No migrations to rollback (at version 0)")
                return True

            # Get migrations to rollback (in reverse order)
            versions_to_rollback = sorted([
                v for v in self._migrations.keys()
                if target_version < v <= current_version
            ], reverse=True)

            if not versions_to_rollback:
                logger.warning(f"No migrations found to rollback from v{current_version}")
                return False

            logger.info(f"Rolling back {len(versions_to_rollback)} migration(s)")

            # Rollback migrations in reverse order
            for version in versions_to_rollback:
                migration = self._migrations.get(version)

                if not migration:
                    raise MigrationVersionError(
                        f"Cannot rollback v{version}: migration not registered"
                    )

                def rollback_tx(tx: Transaction):
                    return self._rollback_migration(tx, migration)

                try:
                    session.execute_write(rollback_tx)
                except Exception as e:
                    logger.error(f"Rollback failed at v{version}: {e}")
                    raise

            logger.info(f"Rollback complete. Now at v{target_version}")
            return True

    def get_pending_migrations(self) -> List[MigrationRecord]:
        """
        Get list of pending migrations.

        Returns:
            List of migrations that haven't been applied yet
        """
        current_version = self.get_current_version()

        pending = [
            self._migrations[v] for v in sorted(self._migrations.keys())
            if v > current_version
        ]
        return pending

    def validate_migrations(self) -> List[str]:
        """
        Validate registered migrations for conflicts.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self._migrations:
            errors.append("No migrations registered")
            return errors

        versions = sorted(self._migrations.keys())

        # Check for gaps
        for i, v in enumerate(versions):
            if i > 0 and versions[i-1] != v - 1:
                errors.append(
                    f"Version gap detected: {versions[i-1]} -> {v}"
                )

        # Check for empty cypher
        for version, migration in self._migrations.items():
            if not migration.up_cypher.strip():
                errors.append(f"v{version}: up_cypher is empty")
            if not migration.down_cypher.strip():
                errors.append(f"v{version}: down_cypher is empty")

        return errors

    def status(self) -> Dict[str, Any]:
        """
        Get migration status summary.

        Returns:
            Dictionary with status information
        """
        current = self.get_current_version()
        pending = self.get_pending_migrations()
        history = self.get_migration_history(limit=10)

        return {
            "current_version": current,
            "latest_registered": max(self._migrations.keys()) if self._migrations else 0,
            "pending_count": len(pending),
            "pending_versions": [m.version for m in pending],
            "registered_count": len(self._migrations),
            "recent_history": [
                {
                    "version": h.version,
                    "name": h.name,
                    "applied_at": h.applied_at.isoformat() if h.applied_at else None,
                    "success": h.success
                }
                for h in history[:5]
            ],
            "validation_errors": self.validate_migrations()
        }