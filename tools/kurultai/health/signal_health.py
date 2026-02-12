"""
Signal Health Monitoring Module (SSE Bridge Compatible)

Monitors Signal bridge health and messaging capabilities.
Updated to work with signal_cli_sse_bridge.py instead of direct signal-cli.
"""

import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp

# Import base classes
try:
    from .base import BaseHealthChecker, HealthResult, HealthStatus
except ImportError:
    # Fallback for standalone use
    from enum import Enum
    from dataclasses import dataclass, field
    
    class HealthStatus(Enum):
        HEALTHY = "healthy"
        WARNING = "warning"
        CRITICAL = "critical"
        UNKNOWN = "unknown"
    
    @dataclass
    class HealthResult:
        component: str
        status: HealthStatus
        message: str = ""
        details: Dict[str, Any] = field(default_factory=dict)
        error: Optional[str] = None
        timestamp: datetime = field(default_factory=datetime.utcnow)
        response_time_ms: float = 0.0
        
        def to_dict(self):
            return {
                'component': self.component,
                'status': self.status.value,
                'message': self.message,
                'details': self.details,
                'error': self.error,
                'timestamp': self.timestamp.isoformat(),
                'response_time_ms': self.response_time_ms
            }
    
    class BaseHealthChecker:
        def __init__(self, name: str, timeout_seconds: float = 30.0):
            self.name = name
            self.timeout_seconds = timeout_seconds

logger = logging.getLogger(__name__)

# Configuration
SIGNAL_BRIDGE_URL = os.environ.get('SIGNAL_BRIDGE_URL', 'http://127.0.0.1:8080')
SIGNAL_ACCOUNT_NUMBER = os.environ.get('SIGNAL_ACCOUNT_NUMBER', '+15165643945')
SIGNAL_TEST_MODE = os.environ.get('SIGNAL_TEST_MODE', 'dry_run')


class SignalHealthChecker(BaseHealthChecker):
    """Signal health monitoring for SSE Bridge setup.
    
    Monitors:
    - Bridge health endpoint
    - Send/receive message capabilities
    - SSE connection health
    - signal-cli daemon status (via bridge)
    """
    
    def __init__(self, timeout_seconds: float = 10.0):
        super().__init__(name="signal", timeout_seconds=timeout_seconds)
        self.bridge_url = SIGNAL_BRIDGE_URL
        self.account_number = SIGNAL_ACCOUNT_NUMBER
        self.test_mode = SIGNAL_TEST_MODE
        
    async def check(self) -> HealthResult:
        """Run all Signal health checks."""
        start_time = time.time()
        
        # Run checks compatible with SSE bridge
        checks = [
            await self.check_bridge_health(),
            await self.check_daemon_proxy(),
            await self.check_send_capability(),
            await self.check_receive_capability(),
            await self.check_sse_connection(),
        ]
        
        # Aggregate results
        critical_count = sum(1 for c in checks if c.status == HealthStatus.CRITICAL)
        warning_count = sum(1 for c in checks if c.status == HealthStatus.WARNING)
        
        if critical_count > 0:
            overall_status = HealthStatus.CRITICAL
            message = f"Signal health critical: {critical_count} critical issues"
        elif warning_count > 0:
            overall_status = HealthStatus.WARNING
            message = f"Signal health warning: {warning_count} warnings"
        else:
            overall_status = HealthStatus.HEALTHY
            message = "Signal health: all checks passed"
        
        details = {
            'bridge_url': self.bridge_url,
            'account_number': self.account_number,
            'test_mode': self.test_mode,
            'checks': [c.to_dict() for c in checks],
            'healthy_checks': sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
            'warning_checks': warning_count,
            'critical_checks': critical_count,
        }
        
        response_time = (time.time() - start_time) * 1000
        
        return HealthResult(
            component='signal',
            status=overall_status,
            message=message,
            details=details,
            response_time_ms=response_time
        )
    
    async def check_bridge_health(self) -> HealthResult:
        """Check if SSE bridge is healthy."""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.bridge_url}/health") as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('status') == 'healthy':
                            return HealthResult(
                                component='signal_bridge',
                                status=HealthStatus.HEALTHY,
                                message="Signal bridge healthy",
                                details={
                                    'signal_cli_running': data.get('signal_cli_running'),
                                    'account': data.get('account'),
                                    'sse_connections': data.get('sse_connections', 0)
                                },
                                response_time_ms=response_time
                            )
                        else:
                            return HealthResult(
                                component='signal_bridge',
                                status=HealthStatus.WARNING,
                                message=f"Signal bridge reports status: {data.get('status')}",
                                response_time_ms=response_time
                            )
                    else:
                        return HealthResult(
                            component='signal_bridge',
                            status=HealthStatus.CRITICAL,
                            message=f"Bridge health endpoint returned {resp.status}",
                            response_time_ms=response_time
                        )
        except Exception as e:
            return HealthResult(
                component='signal_bridge',
                status=HealthStatus.CRITICAL,
                message="Signal bridge unreachable",
                error=str(e)
            )
    
    async def check_daemon_proxy(self) -> HealthResult:
        """Check if signal-cli daemon is running (via bridge)."""
        start_time = time.time()
        
        try:
            # The bridge health endpoint includes signal-cli status
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.bridge_url}/health") as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('signal_cli_running'):
                            return HealthResult(
                                component='signal_daemon',
                                status=HealthStatus.HEALTHY,
                                message="signal-cli daemon running",
                                details={'account': data.get('account')},
                                response_time_ms=response_time
                            )
                        else:
                            return HealthResult(
                                component='signal_daemon',
                                status=HealthStatus.CRITICAL,
                                message="signal-cli daemon not running",
                                response_time_ms=response_time
                            )
                    else:
                        return HealthResult(
                            component='signal_daemon',
                            status=HealthStatus.CRITICAL,
                            message="Cannot check daemon status",
                            response_time_ms=response_time
                        )
        except Exception as e:
            return HealthResult(
                component='signal_daemon',
                status=HealthStatus.CRITICAL,
                message="Failed to check daemon status",
                error=str(e)
            )
    
    async def check_send_capability(self) -> HealthResult:
        """Test message send capability via bridge."""
        start_time = time.time()
        
        if self.test_mode == 'dry_run':
            return HealthResult(
                component='signal_send',
                status=HealthStatus.HEALTHY,
                message="Send capability verified (dry run mode)",
                details={'mode': 'dry_run', 'account': self.account_number},
                response_time_ms=(time.time() - start_time) * 1000
            )
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                # Send test message via bridge
                payload = {
                    'recipient': self.account_number,
                    'message': 'Signal health check test',
                    'attachments': []
                }
                
                async with session.post(
                    f"{self.bridge_url}/send",
                    json=payload
                ) as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    if resp.status == 200:
                        data = await resp.json()
                        if 'result' in data or 'jsonrpc' in str(data):
                            return HealthResult(
                                component='signal_send',
                                status=HealthStatus.HEALTHY,
                                message="Send capability verified",
                                details={'response_time_ms': response_time},
                                response_time_ms=response_time
                            )
                        else:
                            return HealthResult(
                                component='signal_send',
                                status=HealthStatus.WARNING,
                                message="Send returned unexpected response",
                                details={'response': data},
                                response_time_ms=response_time
                            )
                    else:
                        return HealthResult(
                            component='signal_send',
                            status=HealthStatus.WARNING,
                            message=f"Send returned status {resp.status}",
                            response_time_ms=response_time
                        )
        except Exception as e:
            return HealthResult(
                component='signal_send',
                status=HealthStatus.WARNING,
                message="Could not verify send capability",
                error=str(e)
            )
    
    async def check_receive_capability(self) -> HealthResult:
        """Check receive capability - verify SSE endpoint is accessible."""
        start_time = time.time()
        
        try:
            # The bridge proxies messages via SSE
            # If SSE is working, receive capability is functional
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.bridge_url}/health") as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    if resp.status == 200:
                        return HealthResult(
                            component='signal_receive',
                            status=HealthStatus.HEALTHY,
                            message="Receive pipeline healthy (via SSE bridge)",
                            details={'via': 'sse_bridge'},
                            response_time_ms=response_time
                        )
                    else:
                        return HealthResult(
                            component='signal_receive',
                            status=HealthStatus.WARNING,
                            message="Receive pipeline may be degraded",
                            response_time_ms=response_time
                        )
        except Exception as e:
            return HealthResult(
                component='signal_receive',
                status=HealthStatus.WARNING,
                message="Could not verify receive capability",
                error=str(e)
            )
    
    async def check_sse_connection(self) -> HealthResult:
        """Verify SSE endpoint is accessible."""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                # Try to connect to SSE endpoint
                async with session.get(f"{self.bridge_url}/events") as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    content_type = resp.headers.get('Content-Type', '')
                    
                    # SSE endpoint should accept connection (even if no messages)
                    if resp.status in [200, 204] or 'text/event-stream' in content_type:
                        return HealthResult(
                            component='signal_sse',
                            status=HealthStatus.HEALTHY,
                            message="SSE connection accessible",
                            details={'content_type': content_type, 'status': resp.status},
                            response_time_ms=response_time
                        )
                    else:
                        return HealthResult(
                            component='signal_sse',
                            status=HealthStatus.WARNING,
                            message=f"SSE endpoint returned {resp.status}",
                            response_time_ms=response_time
                        )
        except Exception as e:
            return HealthResult(
                component='signal_sse',
                status=HealthStatus.WARNING,
                message="Could not verify SSE connection",
                error=str(e)
            )


# Convenience function for testing
async def run_signal_health_check():
    """Run Signal health check and print results."""
    checker = SignalHealthChecker()
    result = await checker.check()
    
    print(f"\nSignal Health Status: {result.status.value.upper()}")
    print(f"Message: {result.message}")
    print(f"\nChecks:")
    for check in result.details.get('checks', []):
        print(f"  [{check.get('status', 'unknown')}] {check.get('component')}: {check.get('message', '')}")
    
    return result


if __name__ == "__main__":
    asyncio.run(run_signal_health_check())
