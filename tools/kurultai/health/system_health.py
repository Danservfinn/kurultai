"""
System Health Checker - Phase 2 of Jochi Health Check Enhancement Plan

Monitors system resources:
- Disk space usage
- Memory utilization
- CPU load
- Container health
- Log file sizes
- Zombie processes
"""

import asyncio
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from .base import BaseHealthChecker, HealthResult, HealthStatus

logger = logging.getLogger(__name__)

# Default thresholds (can be overridden via config)
DEFAULT_THRESHOLDS = {
    'disk_usage_percent': 80,
    'disk_critical_percent': 90,
    'memory_usage_percent': 90,
    'memory_critical_percent': 95,
    'cpu_load_percent': 80,
    'cpu_load_critical_percent': 95,
    'log_size_mb': 1000,
    'zombie_processes': 100,
    'zombie_critical': 500,
}

# Paths to monitor for disk usage
DISK_PATHS = ['/data', '/tmp', '/', '/var/log']


class SystemHealthChecker(BaseHealthChecker):
    """Health checker for system resources."""
    
    def __init__(self, timeout_seconds: float = 30.0, thresholds: Optional[Dict] = None):
        super().__init__("system", timeout_seconds)
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    
    async def check(self) -> HealthResult:
        """Run all system health checks."""
        start_time = asyncio.get_event_loop().time()
        
        checks = [
            self._check_disk_space(),
            self._check_memory(),
            self._check_cpu(),
            self._check_containers(),
            self._check_logs(),
            self._check_zombies(),
        ]
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
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
            message = f"System critical: {'; '.join(errors)}"
        elif warnings:
            status = HealthStatus.WARNING
            message = f"System degraded: {'; '.join(warnings)}"
        else:
            status = HealthStatus.HEALTHY
            message = "System resources healthy"
        
        return HealthResult(
            component='system',
            status=status,
            message=message,
            details=details,
            error='; '.join(errors) if errors else None,
            response_time_ms=response_time
        )
    
    async def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space usage on configured paths."""
        try:
            disk_issues = []
            disk_info = {}
            
            for path in DISK_PATHS:
                try:
                    usage = shutil.disk_usage(path)
                    total_gb = usage.total / (1024**3)
                    used_gb = usage.used / (1024**3)
                    free_gb = usage.free / (1024**3)
                    percent_used = (usage.used / usage.total) * 100
                    
                    disk_info[path] = {
                        'total_gb': round(total_gb, 2),
                        'used_gb': round(used_gb, 2),
                        'free_gb': round(free_gb, 2),
                        'percent_used': round(percent_used, 1)
                    }
                    
                    if percent_used > self.thresholds['disk_critical_percent']:
                        disk_issues.append(f"{path}: {percent_used:.1f}% full (CRITICAL)")
                    elif percent_used > self.thresholds['disk_usage_percent']:
                        disk_issues.append(f"{path}: {percent_used:.1f}% full (WARNING)")
                        
                except FileNotFoundError:
                    disk_info[path] = {'error': 'Path not found'}
                except PermissionError:
                    disk_info[path] = {'error': 'Permission denied'}
            
            if disk_issues:
                critical_count = sum(1 for i in disk_issues if 'CRITICAL' in i)
                return {
                    'check': 'disk_space',
                    'status': 'error' if critical_count > 0 else 'warning',
                    'message': '; '.join(disk_issues),
                    'disks': disk_info
                }
            
            return {
                'check': 'disk_space',
                'status': 'ok',
                'message': f'All disks below {self.thresholds["disk_usage_percent"]}% usage',
                'disks': disk_info
            }
            
        except Exception as e:
            return {
                'check': 'disk_space',
                'status': 'error',
                'message': f'Disk check failed: {str(e)}'
            }
    
    async def _check_memory(self) -> Dict[str, Any]:
        """Check memory utilization."""
        try:
            # Read memory info from /proc/meminfo on Linux
            mem_info = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        mem_info[key.strip()] = int(value.strip().split()[0])  # in KB
            
            total_kb = mem_info.get('MemTotal', 0)
            available_kb = mem_info.get('MemAvailable', mem_info.get('MemFree', 0))
            used_kb = total_kb - available_kb
            
            if total_kb > 0:
                percent_used = (used_kb / total_kb) * 100
            else:
                percent_used = 0
            
            memory_data = {
                'total_mb': round(total_kb / 1024, 2),
                'used_mb': round(used_kb / 1024, 2),
                'available_mb': round(available_kb / 1024, 2),
                'percent_used': round(percent_used, 1)
            }
            
            if percent_used > self.thresholds['memory_critical_percent']:
                return {
                    'check': 'memory',
                    'status': 'error',
                    'message': f'Memory usage at {percent_used:.1f}% (critical)',
                    'memory': memory_data
                }
            elif percent_used > self.thresholds['memory_usage_percent']:
                return {
                    'check': 'memory',
                    'status': 'warning',
                    'message': f'Memory usage at {percent_used:.1f}% (warning)',
                    'memory': memory_data
                }
            
            return {
                'check': 'memory',
                'status': 'ok',
                'message': f'Memory usage at {percent_used:.1f}%',
                'memory': memory_data
            }
            
        except FileNotFoundError:
            # Try alternative method using psutil if available
            try:
                import psutil
                mem = psutil.virtual_memory()
                percent_used = mem.percent
                
                memory_data = {
                    'total_mb': round(mem.total / (1024**2), 2),
                    'used_mb': round(mem.used / (1024**2), 2),
                    'available_mb': round(mem.available / (1024**2), 2),
                    'percent_used': percent_used
                }
                
                if percent_used > self.thresholds['memory_critical_percent']:
                    return {
                        'check': 'memory',
                        'status': 'error',
                        'message': f'Memory usage at {percent_used:.1f}% (critical)',
                        'memory': memory_data
                    }
                elif percent_used > self.thresholds['memory_usage_percent']:
                    return {
                        'check': 'memory',
                        'status': 'warning',
                        'message': f'Memory usage at {percent_used:.1f}% (warning)',
                        'memory': memory_data
                    }
                
                return {
                    'check': 'memory',
                    'status': 'ok',
                    'message': f'Memory usage at {percent_used:.1f}%',
                    'memory': memory_data
                }
            except ImportError:
                return {
                    'check': 'memory',
                    'status': 'warning',
                    'message': 'Cannot check memory: /proc/meminfo not available and psutil not installed'
                }
                
        except Exception as e:
            return {
                'check': 'memory',
                'status': 'error',
                'message': f'Memory check failed: {str(e)}'
            }
    
    async def _check_cpu(self) -> Dict[str, Any]:
        """Check CPU load."""
        try:
            # Read load average from /proc/loadavg
            with open('/proc/loadavg', 'r') as f:
                loadavg = f.read().strip().split()
            
            load_1min = float(loadavg[0])
            load_5min = float(loadavg[1])
            load_15min = float(loadavg[2])
            
            # Get number of CPUs for normalization
            try:
                cpu_count = os.cpu_count() or 1
            except:
                cpu_count = 1
            
            # Calculate percentage (load / cpu_count * 100)
            load_percent = (load_5min / cpu_count) * 100
            
            cpu_data = {
                'load_1min': load_1min,
                'load_5min': load_5min,
                'load_15min': load_15min,
                'cpu_count': cpu_count,
                'load_percent': round(load_percent, 1)
            }
            
            if load_percent > self.thresholds['cpu_load_critical_percent']:
                return {
                    'check': 'cpu',
                    'status': 'error',
                    'message': f'CPU load at {load_percent:.1f}% (critical)',
                    'cpu': cpu_data
                }
            elif load_percent > self.thresholds['cpu_load_percent']:
                return {
                    'check': 'cpu',
                    'status': 'warning',
                    'message': f'CPU load at {load_percent:.1f}% (warning)',
                    'cpu': cpu_data
                }
            
            return {
                'check': 'cpu',
                'status': 'ok',
                'message': f'CPU load at {load_percent:.1f}%',
                'cpu': cpu_data
            }
            
        except FileNotFoundError:
            return {
                'check': 'cpu',
                'status': 'warning',
                'message': 'Cannot check CPU: /proc/loadavg not available'
            }
        except Exception as e:
            return {
                'check': 'cpu',
                'status': 'error',
                'message': f'CPU check failed: {str(e)}'
            }
    
    async def _check_containers(self) -> Dict[str, Any]:
        """Check container health if running in Docker/containerd."""
        try:
            # Check if docker is available
            result = await asyncio.create_subprocess_exec(
                'docker', 'ps', '--format', '{{.Names}}|{{.Status}}|{{.State}}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                # Docker not available or not running - not an error, just skip
                return {
                    'check': 'containers',
                    'status': 'ok',
                    'message': 'Docker not available, skipping container check'
                }
            
            containers = []
            unhealthy = []
            
            for line in stdout.decode().strip().split('\n'):
                if '|' in line:
                    name, status, state = line.split('|', 2)
                    containers.append({'name': name, 'status': status, 'state': state})
                    
                    if 'unhealthy' in status.lower() or state != 'running':
                        unhealthy.append(name)
            
            if unhealthy:
                return {
                    'check': 'containers',
                    'status': 'warning',
                    'message': f'Unhealthy containers: {", ".join(unhealthy)}',
                    'containers': containers,
                    'unhealthy_count': len(unhealthy)
                }
            
            return {
                'check': 'containers',
                'status': 'ok',
                'message': f'All {len(containers)} containers healthy',
                'containers': containers
            }
            
        except FileNotFoundError:
            return {
                'check': 'containers',
                'status': 'ok',
                'message': 'Docker not installed, skipping container check'
            }
        except Exception as e:
            return {
                'check': 'containers',
                'status': 'warning',
                'message': f'Container check failed: {str(e)}'
            }
    
    async def _check_logs(self) -> Dict[str, Any]:
        """Check log file sizes."""
        try:
            log_paths = ['/var/log', '/data/logs', '/tmp']
            large_logs = []
            total_size_mb = 0
            
            for log_dir in log_paths:
                if os.path.exists(log_dir):
                    try:
                        for root, dirs, files in os.walk(log_dir):
                            for file in files:
                                if file.endswith('.log') or '.log.' in file:
                                    filepath = os.path.join(root, file)
                                    try:
                                        size = os.path.getsize(filepath)
                                        size_mb = size / (1024 * 1024)
                                        total_size_mb += size_mb
                                        
                                        if size_mb > self.thresholds['log_size_mb']:
                                            large_logs.append({
                                                'path': filepath,
                                                'size_mb': round(size_mb, 2)
                                            })
                                    except (OSError, PermissionError):
                                        pass
                    except PermissionError:
                        pass
            
            if large_logs:
                return {
                    'check': 'logs',
                    'status': 'warning',
                    'message': f'{len(large_logs)} log files exceed {self.thresholds["log_size_mb"]}MB',
                    'large_logs': large_logs[:10],  # Limit to first 10
                    'total_size_mb': round(total_size_mb, 2)
                }
            
            return {
                'check': 'logs',
                'status': 'ok',
                'message': f'Log files under control (total: {round(total_size_mb, 2)}MB)',
                'total_size_mb': round(total_size_mb, 2)
            }
            
        except Exception as e:
            return {
                'check': 'logs',
                'status': 'warning',
                'message': f'Log check failed: {str(e)}'
            }
    
    async def _check_zombies(self) -> Dict[str, Any]:
        """Check for zombie processes."""
        try:
            # Count zombie processes
            result = await asyncio.create_subprocess_exec(
                'ps', 'aux',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            zombie_count = 0
            zombies = []
            
            for line in stdout.decode().split('\n'):
                if '<zombie>' in line.lower() or ' Z ' in line:
                    zombie_count += 1
                    parts = line.split()
                    if len(parts) > 10:
                        zombies.append({
                            'pid': parts[1] if len(parts) > 1 else 'unknown',
                            'command': parts[10] if len(parts) > 10 else 'unknown'
                        })
            
            if zombie_count > self.thresholds['zombie_critical']:
                return {
                    'check': 'zombies',
                    'status': 'error',
                    'message': f'{zombie_count} zombie processes (critical)',
                    'zombie_count': zombie_count,
                    'zombies': zombies[:10]
                }
            elif zombie_count > self.thresholds['zombie_processes']:
                return {
                    'check': 'zombies',
                    'status': 'warning',
                    'message': f'{zombie_count} zombie processes (warning)',
                    'zombie_count': zombie_count,
                    'zombies': zombies[:10]
                }
            
            return {
                'check': 'zombies',
                'status': 'ok',
                'message': f'{zombie_count} zombie processes',
                'zombie_count': zombie_count
            }
            
        except FileNotFoundError:
            return {
                'check': 'zombies',
                'status': 'ok',
                'message': 'ps command not available, skipping zombie check'
            }
        except Exception as e:
            return {
                'check': 'zombies',
                'status': 'warning',
                'message': f'Zombie check failed: {str(e)}'
            }
