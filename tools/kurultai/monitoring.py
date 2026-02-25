#!/usr/bin/env python3
"""
Monitoring and Alerting for Kurultai v4.0

Sends alerts for:
- Failed tasks
- Service outages
- Queue backlog
- Disk space warnings
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("kurultai.monitoring")


@dataclass
class AlertConfig:
    """Configuration for alerting."""
    webhook_url: Optional[str] = None  # Slack/Discord webhook
    email: Optional[str] = None
    alert_on_failure: bool = True
    alert_on_backlog: bool = True
    backlog_threshold: int = 10  # Alert if >10 jobs queued
    disk_threshold: float = 90.0  # Alert if disk >90%
    
    @classmethod
    def from_env(cls) -> 'AlertConfig':
        """Load from environment."""
        return cls(
            webhook_url=os.getenv('ALERT_WEBHOOK_URL'),
            email=os.getenv('ALERT_EMAIL'),
            alert_on_failure=os.getenv('ALERT_ON_FAILURE', 'true').lower() == 'true',
            alert_on_backlog=os.getenv('ALERT_ON_BACKLOG', 'true').lower() == 'true',
            backlog_threshold=int(os.getenv('ALERT_BACKLOG_THRESHOLD', '10')),
            disk_threshold=float(os.getenv('ALERT_DISK_THRESHOLD', '90.0'))
        )


class AlertManager:
    """Manages alerts and notifications."""
    
    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig.from_env()
        self._last_alert = {}  # Rate limiting
    
    def send_alert(self, title: str, message: str, severity: str = "warning"):
        """Send alert via configured channels."""
        # Rate limiting (max 1 alert per 5 minutes per title)
        now = datetime.now()
        if title in self._last_alert:
            if now - self._last_alert[title] < timedelta(minutes=5):
                return
        self._last_alert[title] = now
        
        # Log always
        log_func = getattr(logger, severity, logger.warning)
        log_func(f"[{severity.upper()}] {title}: {message}")
        
        # Send webhook if configured
        if self.config.webhook_url and HAS_REQUESTS:
            self._send_webhook(title, message, severity)
        
        # Send email if configured
        if self.config.email:
            self._send_email(title, message, severity)
    
    def _send_webhook(self, title: str, message: str, severity: str):
        """Send to Slack/Discord webhook."""
        try:
            color = {
                "info": "#36a64f",
                "warning": "#ff9900",
                "error": "#ff0000",
                "critical": "#990000"
            }.get(severity, "#ff9900")
            
            payload = {
                "text": f"Kurultai Alert: {title}",
                "attachments": [{
                    "color": color,
                    "fields": [
                        {"title": "Severity", "value": severity.upper(), "short": True},
                        {"title": "Time", "value": datetime.now().isoformat(), "short": True},
                        {"title": "Details", "value": message, "short": False}
                    ]
                }]
            }
            
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"✅ Alert sent to webhook")
            
        except Exception as e:
            logger.error(f"❌ Failed to send webhook alert: {e}")
    
    def _send_email(self, title: str, message: str, severity: str):
        """Send email alert (placeholder - requires SMTP config)."""
        # TODO: Implement SMTP email sending
        logger.info(f"📧 Email alert (not implemented): {title}")
    
    def check_system_health(self) -> Dict[str, Any]:
        """Check system health and send alerts if needed."""
        alerts_sent = []
        
        # Check 1: Redis connectivity
        try:
            from redis import Redis
            r = Redis()
            if not r.ping():
                self.send_alert("Redis Down", "Redis is not responding", "critical")
                alerts_sent.append("redis_down")
        except Exception as e:
            self.send_alert("Redis Error", f"Cannot connect: {e}", "critical")
            alerts_sent.append("redis_error")
        
        # Check 2: Queue backlog
        if self.config.alert_on_backlog:
            try:
                from rq import Queue
                q = Queue('kurultai-tasks', connection=Redis())
                count = q.count
                if count > self.config.backlog_threshold:
                    self.send_alert(
                        "Queue Backlog",
                        f"{count} jobs pending (threshold: {self.config.backlog_threshold})",
                        "warning"
                    )
                    alerts_sent.append("queue_backlog")
            except Exception as e:
                logger.error(f"Failed to check queue: {e}")
        
        # Check 3: Disk space
        try:
            import shutil
            stat = shutil.disk_usage(".")
            used_pct = (stat.used / stat.total) * 100
            if used_pct > self.config.disk_threshold:
                self.send_alert(
                    "Disk Space Low",
                    f"{used_pct:.1f}% disk used (threshold: {self.config.disk_threshold}%)",
                    "warning"
                )
                alerts_sent.append("disk_space")
        except Exception as e:
            logger.error(f"Failed to check disk: {e}")
        
        # Check 4: Failed jobs
        try:
            from rq import Queue
            from redis import Redis
            q = Queue('kurultai-tasks', connection=Redis())
            failed_count = len(q.failed_job_registry)
            if failed_count > 0 and self.config.alert_on_failure:
                self.send_alert(
                    "Failed Jobs",
                    f"{failed_count} jobs failed in queue",
                    "error"
                )
                alerts_sent.append("failed_jobs")
        except Exception as e:
            logger.error(f"Failed to check failed jobs: {e}")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "checks_performed": 4,
            "alerts_sent": alerts_sent
        }


# Singleton
_alert_manager: Optional[AlertManager] = None

def get_alert_manager() -> AlertManager:
    """Get or create alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


if __name__ == "__main__":
    # Test alerts
    print("Testing alert system...")
    am = get_alert_manager()
    
    # Send test alert
    am.send_alert("Test Alert", "This is a test of the alerting system", "info")
    
    # Run health check
    result = am.check_system_health()
    print(f"Health check: {result}")
