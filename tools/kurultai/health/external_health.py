"""
External API Health Checker - Phase 7 of Jochi Health Check Enhancement Plan

Monitors external API connectivity:
- Notion API
- GitHub API
- Parse API
- OpenClaw gateway
- Railway API
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

from .base import BaseHealthChecker, HealthResult, HealthStatus

logger = logging.getLogger(__name__)

# API endpoints
ENDPOINTS = {
    'notion': {
        'url': 'https://api.notion.com/v1/users/me',
        'timeout': 10,
    },
    'github': {
        'url': 'https://api.github.com/rate_limit',
        'timeout': 10,
    },
    'parse': {
        'url': 'https://kind-playfulness-production.up.railway.app/health',
        'timeout': 10,
    },
    'openclaw_gateway': {
        'url': 'http://localhost:18789/health',
        'timeout': 5,
    },
}


class ExternalHealthChecker(BaseHealthChecker):
    """Health checker for external API connectivity."""
    
    def __init__(self, timeout_seconds: float = 30.0, endpoints: Optional[Dict] = None):
        super().__init__("external", timeout_seconds)
        self.endpoints = endpoints or ENDPOINTS
    
    async def check(self) -> HealthResult:
        """Run all external API health checks."""
        start_time = asyncio.get_event_loop().time()
        
        # Run all endpoint checks concurrently
        tasks = [
            self._check_endpoint(name, config)
            for name, config in self.endpoints.items()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        errors = []
        warnings = []
        details = {}
        
        for result in results:
            if isinstance(result, Exception):
                errors.append(f"Check failed: {result}")
                continue
                
            check_name = result.get('check')
            status = result.get('status')
            details[check_name] = result
            
            if status == 'error':
                errors.append(f"{check_name}: {result.get('message')}")
            elif status == 'warning':
                warnings.append(f"{check_name}: {result.get('message')}")
        
        response_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # Determine overall status
        if errors:
            status = HealthStatus.CRITICAL
            message = f"External APIs critical: {'; '.join(errors)}"
        elif warnings:
            status = HealthStatus.WARNING
            message = f"External APIs degraded: {'; '.join(warnings)}"
        else:
            status = HealthStatus.HEALTHY
            message = "All external APIs healthy"
        
        return HealthResult(
            component='external_apis',
            status=status,
            message=message,
            details=details,
            error='; '.join(errors) if errors else None,
            response_time_ms=response_time
        )
    
    async def _check_endpoint(self, name: str, config: Dict) -> Dict[str, Any]:
        """Check a single API endpoint."""
        url = config['url']
        timeout = config.get('timeout', 10)
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                headers = {}
                
                # Add auth headers if available
                if name == 'notion':
                    token = os.environ.get('NOTION_TOKEN')
                    if token:
                        headers['Authorization'] = f'Bearer {token}'
                        headers['Notion-Version'] = '2022-06-28'
                
                elif name == 'github':
                    token = os.environ.get('GITHUB_TOKEN')
                    if token:
                        headers['Authorization'] = f'token {token}'
                
                start_time = asyncio.get_event_loop().time()
                
                async with session.get(url, headers=headers) as response:
                    elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                    
                    if response.status == 200:
                        data = await response.json() if 'json' in response.content_type else None
                        
                        # Extract rate limit info for GitHub
                        if name == 'github' and data:
                            rate_limit = data.get('rate', {})
                            remaining = rate_limit.get('remaining', 0)
                            limit = rate_limit.get('limit', 0)
                            
                            if remaining < limit * 0.1:  # Less than 10% remaining
                                return {
                                    'check': name,
                                    'status': 'warning',
                                    'message': f'GitHub rate limit low: {remaining}/{limit} remaining',
                                    'response_time_ms': round(elapsed_ms, 2),
                                    'rate_limit_remaining': remaining,
                                    'rate_limit_total': limit
                                }
                        
                        return {
                            'check': name,
                            'status': 'ok',
                            'message': f'{name} API responding',
                            'response_time_ms': round(elapsed_ms, 2),
                            'status_code': response.status
                        }
                    
                    elif response.status in [401, 403]:
                        return {
                            'check': name,
                            'status': 'warning',
                            'message': f'{name} API auth issue (status {response.status})',
                            'response_time_ms': round(elapsed_ms, 2),
                            'status_code': response.status
                        }
                    
                    else:
                        return {
                            'check': name,
                            'status': 'error',
                            'message': f'{name} API returned {response.status}',
                            'response_time_ms': round(elapsed_ms, 2),
                            'status_code': response.status
                        }
                        
        except asyncio.TimeoutError:
            return {
                'check': name,
                'status': 'error',
                'message': f'{name} API connection timed out after {timeout}s'
            }
        except aiohttp.ClientConnectorError as e:
            return {
                'check': name,
                'status': 'error',
                'message': f'{name} API connection failed: {str(e)}'
            }
        except Exception as e:
            return {
                'check': name,
                'status': 'error',
                'message': f'{name} API check failed: {str(e)}'
            }
    
    async def check_notion(self) -> Dict[str, Any]:
        """Quick check for Notion API."""
        return await self._check_endpoint('notion', self.endpoints['notion'])
    
    async def check_github(self) -> Dict[str, Any]:
        """Quick check for GitHub API."""
        return await self._check_endpoint('github', self.endpoints['github'])
    
    async def check_parse(self) -> Dict[str, Any]:
        """Quick check for Parse API."""
        return await self._check_endpoint('parse', self.endpoints['parse'])
    
    async def check_openclaw(self) -> Dict[str, Any]:
        """Quick check for OpenClaw gateway."""
        return await self._check_endpoint('openclaw_gateway', self.endpoints['openclaw_gateway'])
