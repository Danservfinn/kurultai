"""
Neo4j-Aware Task Helpers for agent_tasks.py

Provides wrapper functions that gracefully handle Neo4j unavailability
for all background tasks.
"""

import os
import logging
from typing import Dict, List, Optional, Callable, Any
from functools import wraps
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


# Global Neo4j availability flag (cached to avoid repeated connection attempts)
_neo4j_available: Optional[bool] = None
_last_check: Optional[datetime] = None


def check_neo4j_available(force: bool = False) -> bool:
    """
    Check if Neo4j is available with caching.
    
    Args:
        force: Force a fresh check even if cached result exists
        
    Returns:
        True if Neo4j is available, False otherwise
    """
    global _neo4j_available, _last_check
    
    # Use cached result if recent (within 60 seconds)
    if not force and _neo4j_available is not None and _last_check:
        elapsed = (datetime.now() - _last_check).total_seconds()
        if elapsed < 60:
            return _neo4j_available
    
    # Perform fresh check
    try:
        from neo4j import GraphDatabase
        
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        
        if not password:
            _neo4j_available = False
            _last_check = datetime.now()
            return False
        
        driver = GraphDatabase.driver(uri, auth=("neo4j", password))
        driver.verify_connectivity()
        driver.close()
        
        _neo4j_available = True
        _last_check = datetime.now()
        return True
        
    except Exception as e:
        logger.debug(f"Neo4j availability check failed: {e}")
        _neo4j_available = False
        _last_check = datetime.now()
        return False


def with_neo4j_fallback(skip_message: str = "Neo4j unavailable - skipping"):
    """
    Decorator that marks a task as skipped when Neo4j is unavailable.
    
    Usage:
        @with_neo4j_fallback("Skipping memory curation - Neo4j down")
        def memory_curation_rapid(driver) -> Dict:
            # This code only runs if Neo4j is available
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not check_neo4j_available():
                logger.warning(skip_message)
                return {
                    'status': 'skipped',
                    'reason': 'neo4j_unavailable',
                    'message': skip_message,
                    'timestamp': datetime.now().isoformat()
                }
            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_neo4j_partial(partial_func: Callable):
    """
    Decorator that runs a partial function when Neo4j is unavailable.
    
    Usage:
        def health_check_partial():
            return {'system': {'cpu': ...}, 'neo4j': {'connected': False}}
        
        @with_neo4j_partial(health_check_partial)
        def health_check(driver) -> Dict:
            # Full implementation with Neo4j
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not check_neo4j_available():
                logger.warning(f"Neo4j unavailable - running partial: {func.__name__}")
                return partial_func(*args, **kwargs)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def safe_neo4j_session(driver):
    """
    Context manager for safe Neo4j session usage.
    
    Usage:
        with safe_neo4j_session(driver) as session:
            if session is None:
                return  # Neo4j unavailable
            result = session.run("...")
    """
    class SafeSession:
        def __init__(self, driver):
            self.driver = driver
            self.session = None
            
        def __enter__(self):
            try:
                if self.driver:
                    self.session = self.driver.session()
                    return self.session
            except Exception as e:
                logger.warning(f"Could not create Neo4j session: {e}")
            return None
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.session:
                try:
                    self.session.close()
                except:
                    pass
    
    return SafeSession(driver)


def get_neo4j_driver_silent() -> Optional[Any]:
    """
    Get Neo4j driver without raising exceptions.
    
    Returns:
        Driver instance or None if unavailable
    """
    try:
        from neo4j import GraphDatabase
        
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        
        if not password:
            return None
        
        driver = GraphDatabase.driver(uri, auth=("neo4j", password))
        driver.verify_connectivity()
        return driver
        
    except Exception as e:
        logger.debug(f"Could not create Neo4j driver: {e}")
        return None


# =============================================================================
# Partial implementations for when Neo4j is unavailable
# =============================================================================

def health_check_partial() -> Dict:
    """
    Partial health check that works without Neo4j.
    
    Returns system metrics only, skips Neo4j-dependent checks.
    """
    health_data = {
        'timestamp': datetime.now().isoformat(),
        'system': {},
        'neo4j': {'connected': False, 'error': 'Neo4j unavailable'},
        'agents': [],
        'issues': ['Neo4j connection unavailable - operating in fallback mode'],
        'status': 'degraded'
    }
    
    # Try to get system metrics
    try:
        import psutil
        import shutil
        
        health_data['system']['cpu'] = {
            'percent': psutil.cpu_percent(interval=1),
            'cores': psutil.cpu_count()
        }
        
        memory = psutil.virtual_memory()
        health_data['system']['memory'] = {
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'percent': memory.percent
        }
        
        disk = shutil.disk_usage('/')
        health_data['system']['disk'] = {
            'total_gb': round(disk.total / (1024**3), 2),
            'free_gb': round(disk.free / (1024**3), 2),
            'percent': round((disk.used / disk.total) * 100, 2)
        }
        
    except ImportError:
        health_data['system']['note'] = 'psutil not available - limited metrics'
    except Exception as e:
        health_data['system']['error'] = str(e)
    
    return health_data


def file_consistency_partial() -> Dict:
    """
    Partial file consistency check without Neo4j verification.
    """
    issues = []
    checked = 0
    hashes = {}
    
    # Check agent SOUL.md files
    agents = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']
    soul_dir = "/data/workspace/souls"
    
    for agent in agents:
        soul_path = f"{soul_dir}/{agent}/SOUL.md"
        if not os.path.exists(soul_path):
            issues.append(f"Missing SOUL.md for agent: {agent}")
        else:
            checked += 1
            try:
                with open(soul_path, 'rb') as f:
                    content = f.read()
                    import hashlib
                    file_hash = hashlib.md5(content).hexdigest()
                    hashes[f"{agent}/SOUL.md"] = file_hash
            except Exception as e:
                issues.append(f"Cannot read {soul_path}: {e}")
    
    # Check critical system files
    critical_files = [
        "/data/workspace/souls/main/SOUL.md",
        "/data/workspace/souls/main/AGENTS.md",
        "/data/workspace/souls/main/TOOLS.md",
    ]
    
    for cf in critical_files:
        if not os.path.exists(cf):
            issues.append(f"Critical file missing: {cf}")
    
    return {
        'status': 'success' if not issues else 'warning',
        'issues_found': len(issues),
        'issues': issues,
        'agents_checked': len(agents),
        'files_checked': checked,
        'file_hashes': hashes,
        'note': 'Neo4j checks skipped - database unavailable'
    }


def smoke_tests_partial() -> Dict:
    """
    Partial smoke tests without Neo4j tests.
    """
    tests_run = 0
    failures = []
    
    # Test 1: File system access
    try:
        workspace = os.environ.get('WORKSPACE', '/data/workspace')
        assert os.path.exists(workspace)
        assert os.access(workspace, os.R_OK)
        tests_run += 1
    except Exception as e:
        failures.append(f"File system access: {e}")
    
    # Test 2: Python imports
    try:
        import httpx
        tests_run += 1
    except ImportError as e:
        failures.append(f"Python dependencies: {e}")
    
    # Note: Neo4j test skipped
    
    return {
        'status': 'success' if not failures else 'warning',
        'tests_run': tests_run,
        'tests_total': 2,
        'failures': len(failures),
        'failure_details': failures,
        'note': 'Neo4j tests skipped - database unavailable'
    }


def status_synthesis_partial() -> Dict:
    """
    Partial status synthesis without Neo4j agent data.
    """
    synthesis = {
        'timestamp': datetime.now().isoformat(),
        'agents': {},
        'tasks': {'note': 'Task data unavailable without Neo4j'},
        'system': {},
        'alerts': [{
            'type': 'system',
            'severity': 'warning',
            'message': 'Operating in fallback mode - Neo4j unavailable'
        }],
        'summary': {
            'total_agents': 0,
            'healthy_agents': 0,
            'note': 'Limited data available - Neo4j unavailable'
        },
        'status': 'degraded'
    }
    
    # Try to get system metrics
    try:
        import psutil
        synthesis['system'] = {
            'cpu_percent': psutil.cpu_percent(interval=0.5),
            'memory_percent': psutil.virtual_memory().percent,
            'timestamp': datetime.now().isoformat()
        }
    except:
        pass
    
    return synthesis


# =============================================================================
# Task Registry with Neo4j Dependencies Documented
# =============================================================================

TASK_NEO4J_REQUIREMENTS = {
    # Ögedei (Ops)
    'health_check': {'required': False, 'partial': health_check_partial},
    'file_consistency': {'required': False, 'partial': file_consistency_partial},
    
    # Jochi (Analyst)
    'memory_curation_rapid': {'required': True, 'partial': None},
    'mvs_scoring_pass': {'required': True, 'partial': None},
    'smoke_tests': {'required': False, 'partial': smoke_tests_partial},
    'full_tests': {'required': False, 'partial': None},  # Can run partial
    'vector_dedup': {'required': True, 'partial': None},
    'deep_curation': {'required': True, 'partial': None},
    
    # Chagatai (Writer)
    'reflection_consolidation': {'required': True, 'partial': None},
    
    # Möngke (Researcher)
    'knowledge_gap_analysis': {'required': True, 'partial': None},
    'ordo_sacer_research': {'required': False, 'partial': None},  # External API
    'ecosystem_intelligence': {'required': False, 'partial': None},  # External API
    
    # Kublai (Main)
    'status_synthesis': {'required': False, 'partial': status_synthesis_partial},
    'weekly_reflection': {'required': True, 'partial': None},
    
    # System
    'notion_sync': {'required': True, 'partial': None},  # Uses Neo4j for task storage
}


def run_task_with_fallback(task_name: str, driver=None) -> Dict:
    """
    Run a task with automatic fallback handling.
    
    Args:
        task_name: Name of the task to run
        driver: Optional Neo4j driver
        
    Returns:
        Task result dict
    """
    from tools.kurultai.agent_tasks import TASK_REGISTRY
    
    if task_name not in TASK_REGISTRY:
        return {'status': 'error', 'error': f'Unknown task: {task_name}'}
    
    # Check if task requires Neo4j
    neo4j_req = TASK_NEO4J_REQUIREMENTS.get(task_name, {'required': True})
    
    if neo4j_req['required'] and not check_neo4j_available():
        # Task requires Neo4j but it's unavailable
        partial = neo4j_req.get('partial')
        if partial:
            logger.info(f"Running partial implementation for {task_name}")
            return partial()
        else:
            return {
                'status': 'skipped',
                'reason': 'neo4j_required_but_unavailable',
                'message': f'Task {task_name} requires Neo4j which is currently unavailable',
                'timestamp': datetime.now().isoformat()
            }
    
    # Run the full task
    task_fn = TASK_REGISTRY[task_name]['fn']
    
    try:
        if driver is None and neo4j_req['required']:
            # Create driver if needed
            from neo4j import GraphDatabase
            uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
            password = os.environ.get('NEO4J_PASSWORD')
            driver = GraphDatabase.driver(uri, auth=("neo4j", password))
            close_driver = True
        else:
            close_driver = False
        
        result = task_fn(driver)
        result['task'] = task_name
        result['timestamp'] = datetime.now().isoformat()
        
        if close_driver:
            driver.close()
        
        return result
        
    except Exception as e:
        return {
            'status': 'error',
            'task': task_name,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
