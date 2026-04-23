"""
Molt Protocols Package

This package contains protocol implementations for the multi-agent system.

NOTE: file_consistency, backend_analysis, failover, and security_audit
have been superseded by their tools/ equivalents and archived to archived/.
The canonical implementations are now:
  - tools.file_consistency.FileConsistencyChecker
  - tools.backend_collaboration.BackendCodeReviewer
  - tools.failover_monitor.FailoverMonitor
  - tools.security (package)
"""

from .delegation import DelegationProtocol

__all__ = [
    'DelegationProtocol',
]
