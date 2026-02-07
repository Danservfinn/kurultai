"""
Health Check Tests for Kurultai System

This package contains health check tests for the Kurultai multi-agent system.
Tests are organized by component (neo4j, openclaw, heartbeat, services).

Usage:
    pytest tests/health/ -v                    # Run all health checks
    pytest tests/health/ -k neo4j -v          # Run Neo4j checks only
    pytest tests/health/ -k openclaw -v       # Run OpenClaw checks only
    pytest tests/health/ -k heartbeat -v       # Run heartbeat checks only

Markers:
    @pytest.mark.health: Health check tests
    @pytest.mark.neo4j: Neo4j-specific tests
    @pytest.mark.openclaw: OpenClaw gateway tests
    @pytest.mark.heartbeat: Heartbeat freshness tests
    @pytest.mark.services: Service endpoint tests
"""

__version__ = "1.0.0"
