"""
Neo4j Schema Migration System for OpenClaw Multi-Agent Platform.

This package provides schema versioning and migration capabilities for Neo4j,
ensuring consistent database schema across all agent deployments.
"""

from .migration_manager import MigrationManager, MigrationError
from .v1_initial_schema import V1InitialSchema
from .v2_kurultai_dependencies import V2KurultaiDependencies

__all__ = [
    "MigrationManager",
    "MigrationError",
    "V1InitialSchema",
    "V2KurultaiDependencies",
]

__version__ = "2.0.0"