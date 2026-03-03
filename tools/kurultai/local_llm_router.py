"""
Local LLM Router for Heartbeat Tasks

Routes routine heartbeat tasks to local LLM (qwen3.5-9b-mlx) with cloud fallback.
Tracks metrics for success rate, latency, and cost savings.

Usage:
    from local_llm_router import run_with_routing
    result = run_with_routing("task_pickup", "temujin", task_params)
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
import requests

# Configuration
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://10.200.136.34:1234/v1/chat/completions")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen3.5-9b-mlx")
CLOUD_LLM_MODEL = os.getenv("CLOUD_LLM_MODEL", "qwen3.5-plus")
LOCAL_TIMEOUT_SECONDS = int(os.getenv("LOCAL_LLM_TIMEOUT", "10"))

# Tasks that should use local LLM
LOCAL_LLM_TASKS = {
    "task_pickup": {"priority": "high", "reason": "Simple file polling"},
    "health_check": {"priority": "high", "reason": "System status checks"},
    "memory_curation_rapid": {"priority": "high", "reason": "Token budget enforcement"},
    "file_consistency": {"priority": "high", "reason": "File comparison"},
    "smoke_tests": {"priority": "high", "reason": "Quick pass/fail tests"},
    "status_synthesis": {"priority": "medium", "reason": "Status aggregation"},
}

METRICS_FILE = "/Users/kublai/.openclaw/agents/main/logs/heartbeat_metrics.jsonl"

def log_metric(agent: str, task: str, model: str, success: bool, latency_ms: int, tokens_used: int = 0):
    """Log execution metric"""
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    
    metric = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "task": task,
        "model": model,
        "success": success,
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
        "is_local": model == LOCAL_LLM_MODEL
    }
    
    with open(METRICS_FILE, 'a') as f:
        f.write(json.dumps(metric) + '\n')

def call_local_llm(prompt: str, timeout: int = LOCAL_TIMEOUT_SECONDS) -> Optional[Dict]:
    """Call local LLM with timeout and connection check"""
    try:
        start = time.time()
        
        # First check if server is reachable
        try:
            requests.get(LOCAL_LLM_URL.replace('/chat/completions', '/models'), timeout=2)
        except:
            return {
                "success": False,
                "error": "Local LLM server unreachable",
                "latency_ms": 0,
                "model": LOCAL_LLM_MODEL,
                "fallback_recommended": True
            }
        
        response = requests.post(
            LOCAL_LLM_URL,
            json={
                "model": LOCAL_LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful AI assistant. Be concise and accurate."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000,
                "temperature": 0.7
            },
            timeout=timeout
        )
        
        latency_ms = int((time.time() - start) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            return {
                "success": True,
                "content": content,
                "latency_ms": latency_ms,
                "model": LOCAL_LLM_MODEL,
                "tokens_used": data.get('usage', {}).get('total_tokens', 0)
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "latency_ms": latency_ms,
                "model": LOCAL_LLM_MODEL,
                "fallback_recommended": True
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Timeout",
            "latency_ms": timeout * 1000,
            "model": LOCAL_LLM_MODEL,
            "fallback_recommended": True
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency_ms": 0,
            "model": LOCAL_LLM_MODEL,
            "fallback_recommended": True
        }

def call_cloud_llm(prompt: str) -> Dict:
    """Call cloud LLM (via OpenClaw)"""
    # This would integrate with OpenClaw's LLM routing
    # For now, return a placeholder
    return {
        "success": True,
        "content": f"[Cloud LLM response for: {prompt[:50]}...]",
        "latency_ms": 5000,
        "model": CLOUD_LLM_MODEL,
        "tokens_used": 500
    }

def should_use_local(agent: str, task_name: str) -> bool:
    """Determine if task should use local LLM"""
    if task_name not in LOCAL_LLM_TASKS:
        return False
    
    # Check recent success rate for this task
    recent_metrics = get_recent_metrics(agent, task_name, hours=1)
    
    if len(recent_metrics) >= 5:
        local_metrics = [m for m in recent_metrics if m.get('is_local')]
        if len(local_metrics) >= 3:
            success_rate = sum(1 for m in local_metrics if m.get('success')) / len(local_metrics)
            if success_rate < 0.8:  # Less than 80% success rate
                return False
    
    return True

def get_recent_metrics(agent: str, task: str, hours: int = 1) -> list:
    """Get recent metrics for a task"""
    metrics = []
    
    if not os.path.exists(METRICS_FILE):
        return metrics
    
    cutoff = time.time() - (hours * 3600)
    
    try:
        with open(METRICS_FILE, 'r') as f:
            for line in f:
                try:
                    m = json.loads(line)
                    if m.get('agent') == agent and m.get('task') == task:
                        metric_time = datetime.fromisoformat(m['timestamp']).timestamp()
                        if metric_time >= cutoff:
                            metrics.append(m)
                except:
                    pass
    except:
        pass
    
    return metrics

def run_with_routing(agent: str, task_name: str, prompt: str, force_cloud: bool = False) -> Dict:
    """
    Run task with intelligent LLM routing.
    
    Args:
        agent: Agent name
        task_name: Task name
        prompt: Prompt to send to LLM
        force_cloud: If True, skip local and use cloud
    
    Returns:
        Dict with success, content, latency_ms, model, tokens_used
    """
    start_time = time.time()
    
    # Determine routing
    use_local = not force_cloud and should_use_local(agent, task_name)
    
    if use_local:
        # Try local first
        result = call_local_llm(prompt)
        
        if result['success'] and result.get('content'):
            # Local succeeded
            log_metric(agent, task_name, result['model'], True, result['latency_ms'], result.get('tokens_used', 0))
            return result
        
        # Local failed - fallback to cloud
        log_metric(agent, task_name, LOCAL_LLM_MODEL, False, result.get('latency_ms', 0), 0)
        
        # Try cloud
        cloud_result = call_cloud_llm(prompt)
        cloud_result['fallback_from_local'] = True
        log_metric(agent, task_name, cloud_result['model'], cloud_result['success'], cloud_result['latency_ms'], cloud_result.get('tokens_used', 0))
        
        return cloud_result
    
    else:
        # Use cloud directly
        result = call_cloud_llm(prompt)
        log_metric(agent, task_name, result['model'], result['success'], result['latency_ms'], result.get('tokens_used', 0))
        
        return result

def get_metrics_summary(agent: str = None, hours: int = 24) -> Dict:
    """Get metrics summary for dashboard"""
    metrics = []
    
    if os.path.exists(METRICS_FILE):
        cutoff = time.time() - (hours * 3600)
        
        with open(METRICS_FILE, 'r') as f:
            for line in f:
                try:
                    m = json.loads(line)
                    metric_time = datetime.fromisoformat(m['timestamp']).timestamp()
                    if metric_time >= cutoff:
                        if agent is None or m.get('agent') == agent:
                            metrics.append(m)
                except:
                    pass
    
    if not metrics:
        return {"total_executions": 0}
    
    # Calculate stats
    total = len(metrics)
    local_count = sum(1 for m in metrics if m.get('is_local'))
    cloud_count = total - local_count
    
    local_success = sum(1 for m in metrics if m.get('is_local') and m.get('success'))
    cloud_success = sum(1 for m in metrics if not m.get('is_local') and m.get('success'))
    
    local_latency_avg = sum(m.get('latency_ms', 0) for m in metrics if m.get('is_local')) / max(local_count, 1)
    cloud_latency_avg = sum(m.get('latency_ms', 0) for m in metrics if not m.get('is_local')) / max(cloud_count, 1)
    
    return {
        "period_hours": hours,
        "total_executions": total,
        "local": {
            "count": local_count,
            "success_rate": f"{100 * local_success / max(local_count, 1):.1f}%",
            "avg_latency_ms": int(local_latency_avg),
            "percentage": f"{100 * local_count / max(total, 1):.1f}%"
        },
        "cloud": {
            "count": cloud_count,
            "success_rate": f"{100 * cloud_success / max(cloud_count, 1):.1f}%",
            "avg_latency_ms": int(cloud_latency_avg),
            "percentage": f"{100 * cloud_count / max(total, 1):.1f}%"
        },
        "estimated_savings": {
            "description": "Local LLM calls are free vs ~$0.02 per cloud call",
            "estimated_daily_savings": f"${local_count * 0.02:.2f}"
        }
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Local LLM Router')
    parser.add_argument('--metrics', action='store_true', help='Show metrics summary')
    parser.add_argument('--agent', help='Filter by agent')
    parser.add_argument('--hours', type=int, default=24, help='Hours to look back')
    
    args = parser.parse_args()
    
    if args.metrics:
        summary = get_metrics_summary(args.agent, args.hours)
        print(json.dumps(summary, indent=2))
    else:
        # Test routing
        result = run_with_routing("test", "task_pickup", "Test prompt")
        print(json.dumps(result, indent=2))
