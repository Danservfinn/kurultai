"""
Continuous Task Registry - For never-ending tasks (monitors, watchers)

Usage in agent_tasks.py:
    register_continuous_task(hb, "ogedei", "uptime_monitor", ogedei_uptime_monitor, 
                            frequency_minutes=1, max_tokens=100)
"""

from .heartbeat_master import HeartbeatTask

CONTINUOUS_TASKS = []

def register_continuous_task(hb, agent, name, handler, frequency_minutes=1, max_tokens=100, description=""):
    """
    Register a continuous (never-ending) task.
    
    These tasks:
    - Never complete (run forever)
    - Are tracked separately from one-shot tasks
    - Can be stopped via subagents action=kill
    """
    task = HeartbeatTask(
        name=name,
        agent=agent,
        frequency_minutes=frequency_minutes,
        max_tokens=max_tokens,
        handler=handler,
        description=description or f"Continuous {name} for {agent}",
        continuous=True  # Flag for never-ending
    )
    
    hb.register(task)
    CONTINUOUS_TASKS.append(task)
    
    return task


def get_continuous_tasks():
    """Get all registered continuous tasks"""
    return CONTINUOUS_TASKS


# Example continuous task handlers
async def example_uptime_monitor(driver) -> dict:
    """
    Example: Monitor a URL's uptime continuously.
    Runs every 1 minute, never completes.
    """
    import urllib.request
    import time
    
    url = "https://parsethe.media/"
    start = time.time()
    
    try:
        urllib.request.urlopen(url, timeout=10)
        latency = time.time() - start
        status = "up"
    except Exception as e:
        latency = 0
        status = f"down: {str(e)}"
    
    return {
        "summary": f"Parse {status} (latency: {latency:.2f}s)",
        "tokens_used": 50,
        "data": {
            "url": url,
            "status": status,
            "latency": latency,
            "continuous": True
        }
    }


async def example_session_watcher(driver) -> dict:
    """
    Example: Watch for new sessions and log them.
    Runs every 30 seconds, never completes.
    """
    # This would integrate with OpenClaw session tracking
    return {
        "summary": "Session watcher active",
        "tokens_used": 30,
        "data": {"continuous": True, "watching": True}
    }
