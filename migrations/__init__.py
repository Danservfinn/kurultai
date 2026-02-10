"""
Neo4j Schema Migration System for OpenClaw Multi-Agent Platform.

This package provides schema versioning and migration capabilities for Neo4j,
ensuring consistent database schema across all agent deployments.
"""

from .migration_manager import MigrationManager, MigrationError
from .v1_initial_schema import V1InitialSchema
from .v2_kurultai_dependencies import V2KurultaiDependencies
from .v3_capability_acquisition import V3CapabilityAcquisition
from .v4_identity_management import V4IdentityManagement

__all__ = [
    "MigrationManager",
    "MigrationError",
    "V1InitialSchema",
    "V2KurultaiDependencies",
    "V3CapabilityAcquisition",
    "V4IdentityManagement",
]

__version__ = "4.0.0"