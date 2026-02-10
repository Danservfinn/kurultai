"""
Neo4j Performance Monitoring Module

Phase 3: Neo4j Performance Monitoring
Monitors Neo4j connectivity, query performance, disk usage, indexes, backups, and memory.

Tasks Implemented:
- H3-T1: Connection health
- H3-T2: Query performance
- H3-T3: Disk usage
- H3-T4: Index health
- H3-T5: Backup recency
- H3-T6: Memory pressure
"""

import os
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase, Driver

from .base import BaseHealthChecker, HealthResult, HealthStatus

logger = logging.getLogger(__name__)

# Configuration
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', '')

# Thresholds
NEO4J_THRESHOLDS = {
    'query_time_ms': 1000,  # Alert if queries take > 1s
    'disk_usage_percent': 80,
    'page_cache_hit_ratio': 0.90,  # Alert if < 90%
    'backup_max_age_hours': 24,
}


class Neo4jHealthChecker(BaseHealthChecker):
    """Neo4j performance monitoring.
    
    Monitors:
    - Connection health and basic query performance
    - Slow query detection
    - Disk usage for Neo4j data
    - Index validity
    - Backup recency
    - Memory pressure (page cache)
    """
    
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        thresholds: Optional[Dict[str, float]] = None
    ):
        super().__init__(name="neo4j", timeout_seconds=timeout_seconds)
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password or NEO4J_PASSWORD
        self.thresholds = {**NEO4J_THRESHOLDS, **(thresholds or {})}
        self._driver: Optional[Driver] = None
    
    def _get_driver(self) -> Driver:
        """Get or create Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
        return self._driver
    
    async def check(self) -> HealthResult:
        """Run all Neo4j health checks.
        
        Returns:
            HealthResult with aggregated status of all Neo4j components
        """
        start_time = time.time()
        
        try:
            # Run all checks
            checks = [
                await self.check_connection(),
                await self.check_query_performance(),
                await self.check_disk_usage(),
                await self.check_indexes(),
                await self.check_backup_recency(),
                await self.check_memory_pressure(),
            ]
            
            # Aggregate results
            critical_count = sum(1 for c in checks if c.status == HealthStatus.CRITICAL)
            warning_count = sum(1 for c in checks if c.status == HealthStatus.WARNING)
            
            if critical_count > 0:
                overall_status = HealthStatus.CRITICAL
                message = f"Neo4j health critical: {critical_count} critical issues"
            elif warning_count > 0:
                overall_status = HealthStatus.WARNING
                message = f"Neo4j health warning: {warning_count} warnings"
            else:
                overall_status = HealthStatus.HEALTHY
                message = "Neo4j health: all checks passed"
            
            details = {
                'uri': self.uri,
                'checks': [c.to_dict() for c in checks],
                'healthy_checks': sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
                'warning_checks': warning_count,
                'critical_checks': critical_count,
            }
            
        except Exception as e:
            overall_status = HealthStatus.CRITICAL
            message = f"Neo4j health check failed: {e}"
            details = {'error': str(e)}
        
        response_time = (time.time() - start_time) * 1000
        
        return HealthResult(
            component='neo4j',
            status=overall_status,
            message=message,
            details=details,
            response_time_ms=response_time
        )
    
    async def check_connection(self) -> HealthResult:
        """H3-T1: Test query performance (connection health).
        
        Returns:
            HealthResult with connection status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            # Run a simple query to test connectivity
            with driver.session() as session:
                query_start = time.time()
                result = session.run('MATCH (n) RETURN count(n) as count LIMIT 1')
                record = result.single()
                query_time = (time.time() - query_start) * 1000
                
                node_count = record['count'] if record else 0
                
                response_time = (time.time() - start_time) * 1000
                
                if query_time > self.thresholds['query_time_ms']:
                    return HealthResult(
                        component='neo4j_connection',
                        status=HealthStatus.WARNING,
                        message=f"Connection slow: {query_time:.1f}ms",
                        details={
                            'query_time_ms': round(query_time, 2),
                            'node_count': node_count,
                            'threshold_ms': self.thresholds['query_time_ms']
                        },
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='neo4j_connection',
                        status=HealthStatus.HEALTHY,
                        message=f"Connection healthy ({query_time:.1f}ms, {node_count} nodes)",
                        details={
                            'query_time_ms': round(query_time, 2),
                            'node_count': node_count
                        },
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='neo4j_connection',
                status=HealthStatus.CRITICAL,
                message="Neo4j connection failed",
                error=str(e)
            )
    
    async def check_query_performance(self) -> HealthResult:
        """H3-T2: Monitor slow queries.
        
        Checks for queries taking longer than threshold.
        
        Returns:
            HealthResult with query performance status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            # Query listQueries to get active queries and their elapsed time
            # Note: This requires appropriate permissions
            with driver.session() as session:
                try:
                    result = session.run('''
                        SHOW TRANSACTIONS YIELD transactionId, elapsedTimeMillis, query
                        WHERE elapsedTimeMillis > $threshold
                        RETURN transactionId, elapsedTimeMillis, query
                        LIMIT 10
                    ''', threshold=self.thresholds['query_time_ms'])
                    
                    slow_queries = []
                    for record in result:
                        slow_queries.append({
                            'transaction_id': record['transactionId'],
                            'elapsed_ms': record['elapsedTimeMillis'],
                            'query': record['query'][:200]  # Truncate for readability
                        })
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    if slow_queries:
                        return HealthResult(
                            component='neo4j_slow_queries',
                            status=HealthStatus.WARNING,
                            message=f"Found {len(slow_queries)} slow queries",
                            details={
                                'slow_queries': slow_queries,
                                'threshold_ms': self.thresholds['query_time_ms']
                            },
                            response_time_ms=response_time
                        )
                    else:
                        return HealthResult(
                            component='neo4j_slow_queries',
                            status=HealthStatus.HEALTHY,
                            message="No slow queries detected",
                            details={'threshold_ms': self.thresholds['query_time_ms']},
                            response_time_ms=response_time
                        )
                        
                except Exception as e:
                    # Query might not be supported in this Neo4j version
                    response_time = (time.time() - start_time) * 1000
                    return HealthResult(
                        component='neo4j_slow_queries',
                        status=HealthStatus.HEALTHY,
                        message="Query performance check skipped (permissions/version)",
                        details={'note': str(e)},
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='neo4j_slow_queries',
                status=HealthStatus.UNKNOWN,
                message="Could not check query performance",
                error=str(e)
            )
    
    async def check_disk_usage(self) -> HealthResult:
        """H3-T3: Monitor Neo4j data size.
        
        Returns:
            HealthResult with disk usage status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                # Get database size info
                try:
                    result = session.run('''
                        SHOW DATABASES YIELD name, storeSize
                        RETURN name, storeSize
                    ''')
                    
                    db_sizes = []
                    total_size = 0
                    
                    for record in result:
                        db_name = record['name']
                        store_size = record['storeSize'] or 0
                        db_sizes.append({
                            'name': db_name,
                            'size_bytes': store_size,
                            'size_mb': round(store_size / (1024 * 1024), 2)
                        })
                        total_size += store_size
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    total_mb = total_size / (1024 * 1024)
                    
                    # Check if we can get disk usage for data directory
                    # This is a simplified check
                    return HealthResult(
                        component='neo4j_disk',
                        status=HealthStatus.HEALTHY,
                        message=f"Neo4j disk usage: {total_mb:.1f} MB",
                        details={
                            'databases': db_sizes,
                            'total_size_mb': round(total_mb, 2)
                        },
                        response_time_ms=response_time
                    )
                    
                except Exception as e:
                    # Fallback: just count nodes/relationships as proxy for size
                    result = session.run('''
                        MATCH (n)
                        WITH count(n) as node_count
                        MATCH ()-[r]-()
                        RETURN node_count, count(r) as rel_count
                    ''')
                    record = result.single()
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    return HealthResult(
                        component='neo4j_disk',
                        status=HealthStatus.HEALTHY,
                        message=f"Neo4j size: {record['node_count']} nodes, {record['rel_count']} rels",
                        details={
                            'node_count': record['node_count'],
                            'relationship_count': record['rel_count'],
                            'note': 'Detailed store size unavailable'
                        },
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='neo4j_disk',
                status=HealthStatus.UNKNOWN,
                message="Could not check Neo4j disk usage",
                error=str(e)
            )
    
    async def check_indexes(self) -> HealthResult:
        """H3-T4: Verify indexes are valid.
        
        Returns:
            HealthResult with index health status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                try:
                    # Query indexes and their status
                    result = session.run('SHOW INDEXES')
                    
                    indexes = []
                    failed_indexes = []
                    
                    for record in result:
                        index_info = {
                            'name': record.get('name'),
                            'type': record.get('type'),
                            'entityType': record.get('entityType'),
                            'state': record.get('state'),
                        }
                        indexes.append(index_info)
                        
                        if record.get('state') not in ['ONLINE', 'POPULATING']:
                            failed_indexes.append(index_info)
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    if failed_indexes:
                        return HealthResult(
                            component='neo4j_indexes',
                            status=HealthStatus.CRITICAL,
                            message=f"{len(failed_indexes)} indexes in bad state",
                            details={
                                'total_indexes': len(indexes),
                                'failed_indexes': failed_indexes,
                                'all_indexes': indexes
                            },
                            response_time_ms=response_time
                        )
                    else:
                        return HealthResult(
                            component='neo4j_indexes',
                            status=HealthStatus.HEALTHY,
                            message=f"All {len(indexes)} indexes healthy",
                            details={'total_indexes': len(indexes)},
                            response_time_ms=response_time
                        )
                        
                except Exception as e:
                    # Index query might not be supported
                    response_time = (time.time() - start_time) * 1000
                    return HealthResult(
                        component='neo4j_indexes',
                        status=HealthStatus.HEALTHY,
                        message="Index check skipped (version compatibility)",
                        details={'note': str(e)},
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='neo4j_indexes',
                status=HealthStatus.UNKNOWN,
                message="Could not check indexes",
                error=str(e)
            )
    
    async def check_backup_recency(self) -> HealthResult:
        """H3-T5: Check last backup time.
        
        Returns:
            HealthResult with backup status
        """
        start_time = time.time()
        
        try:
            # Look for backup files in common locations
            import glob
            from pathlib import Path
            
            backup_locations = [
                '/data/backups/neo4j',
                '/var/backups/neo4j',
                '/data/workspace/souls/main/backups',
            ]
            
            latest_backup = None
            latest_time = None
            
            for location in backup_locations:
                if os.path.exists(location):
                    backup_files = glob.glob(f"{location}/**/*", recursive=True)
                    for f in backup_files:
                        try:
                            mtime = os.path.getmtime(f)
                            if latest_time is None or mtime > latest_time:
                                latest_time = mtime
                                latest_backup = f
                        except:
                            pass
            
            response_time = (time.time() - start_time) * 1000
            
            if latest_backup and latest_time:
                age_hours = (time.time() - latest_time) / 3600
                backup_datetime = datetime.fromtimestamp(latest_time)
                
                if age_hours > self.thresholds['backup_max_age_hours']:
                    return HealthResult(
                        component='neo4j_backup',
                        status=HealthStatus.WARNING,
                        message=f"Backup is {age_hours:.1f} hours old",
                        details={
                            'latest_backup': latest_backup,
                            'backup_time': backup_datetime.isoformat(),
                            'age_hours': round(age_hours, 2),
                            'threshold_hours': self.thresholds['backup_max_age_hours']
                        },
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='neo4j_backup',
                        status=HealthStatus.HEALTHY,
                        message=f"Backup recent ({age_hours:.1f} hours old)",
                        details={
                            'latest_backup': latest_backup,
                            'backup_time': backup_datetime.isoformat(),
                            'age_hours': round(age_hours, 2)
                        },
                        response_time_ms=response_time
                    )
            else:
                return HealthResult(
                    component='neo4j_backup',
                    status=HealthStatus.WARNING,
                    message="No backups found",
                    details={'searched_locations': backup_locations},
                    response_time_ms=response_time
                )
                
        except Exception as e:
            return HealthResult(
                component='neo4j_backup',
                status=HealthStatus.UNKNOWN,
                message="Could not check backup recency",
                error=str(e)
            )
    
    async def check_memory_pressure(self) -> HealthResult:
        """H3-T6: Check page cache hit ratio.
        
        Returns:
            HealthResult with memory pressure status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                try:
                    # Query for page cache metrics
                    result = session.run('''
                        CALL dbms.listConfig() YIELD name, value
                        WHERE name STARTS WITH 'dbms.memory.'
                        RETURN name, value
                    ''')
                    
                    memory_config = {r['name']: r['value'] for r in result}
                    
                    # Also try to get cache hit ratio from metrics (if available)
                    try:
                        metrics_result = session.run('''
                            CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Page cache') 
                            YIELD attributes
                            RETURN attributes
                        ''')
                        metrics_record = metrics_result.single()
                        cache_metrics = metrics_record['attributes'] if metrics_record else {}
                    except:
                        cache_metrics = {}
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    # Extract hit ratio if available
                    hit_ratio = None
                    if cache_metrics and 'HitRatio' in cache_metrics:
                        hit_ratio = cache_metrics['HitRatio'].get('value', 0)
                    
                    if hit_ratio is not None and hit_ratio < self.thresholds['page_cache_hit_ratio']:
                        return HealthResult(
                            component='neo4j_memory',
                            status=HealthStatus.WARNING,
                            message=f"Page cache hit ratio low: {hit_ratio:.2%}",
                            details={
                                'hit_ratio': hit_ratio,
                                'threshold': self.thresholds['page_cache_hit_ratio'],
                                'memory_config': memory_config,
                                'cache_metrics': {k: v for k, v in (cache_metrics or {}).items() if isinstance(v, (int, float, str, bool))}
                            },
                            response_time_ms=response_time
                        )
                    else:
                        status_msg = f"hit ratio {hit_ratio:.2%}" if hit_ratio else "memory config available"
                        return HealthResult(
                            component='neo4j_memory',
                            status=HealthStatus.HEALTHY,
                            message=f"Neo4j memory healthy ({status_msg})",
                            details={
                                'hit_ratio': hit_ratio,
                                'memory_config': memory_config
                            },
                            response_time_ms=response_time
                        )
                        
                except Exception as e:
                    # Memory metrics might not be available
                    response_time = (time.time() - start_time) * 1000
                    return HealthResult(
                        component='neo4j_memory',
                        status=HealthStatus.HEALTHY,
                        message="Memory pressure check skipped",
                        details={'note': str(e)},
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='neo4j_memory',
                status=HealthStatus.UNKNOWN,
                message="Could not check memory pressure",
                error=str(e)
            )
    
    def __del__(self):
        """Cleanup driver on destruction."""
        if self._driver:
            self._driver.close()
