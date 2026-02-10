#!/usr/bin/env python3
"""
Cost Monitor for Railway Deployment

Tracks daily costs, queries Railway API for usage,
and sends alerts when approaching budget thresholds.

Usage:
    python cost_monitor.py [--check] [--daily-log]
    
Environment Variables:
    RAILWAY_API_TOKEN - Railway API token for authentication
    COST_ALERT_THRESHOLD - Budget threshold in USD (default: 50)
    COST_CRITICAL_THRESHOLD - Critical budget threshold in USD (default: 80)
    ALERT_WEBHOOK_URL - Optional webhook URL for alerts
"""

import os
import sys
import json
import httpx
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Configuration
LOG_DIR = Path("/data/workspace/souls/main/logs")
LOG_FILE = LOG_DIR / "daily_costs.jsonl"
DEFAULT_THRESHOLD = 50.0  # USD
DEFAULT_CRITICAL_THRESHOLD = 80.0  # USD

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)


class RailwayCostMonitor:
    """Monitor Railway deployment costs via API."""
    
    BASE_URL = "https://backboard.railway.app/graphql/v2"
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.environ.get('RAILWAY_API_TOKEN')
        self.threshold = float(os.environ.get('COST_ALERT_THRESHOLD', DEFAULT_THRESHOLD))
        self.critical_threshold = float(os.environ.get('COST_CRITICAL_THRESHOLD', DEFAULT_CRITICAL_THRESHOLD))
        
        if not self.api_token:
            raise ValueError("RAILWAY_API_TOKEN environment variable required")
    
    def _query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute GraphQL query against Railway API."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self.BASE_URL,
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Railway API error: {response.status_code} - {response.text}")
            
            data = response.json()
            if 'errors' in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            
            return data.get('data', {})
    
    def get_current_usage(self) -> Dict:
        """Get current billing usage for the project."""
        # Query for project usage and billing info
        query = """
        query {
            me {
                projects {
                    edges {
                        node {
                            id
                            name
                            billing {
                                currentSpend
                                spendLimit
                                usage {
                                    startTime
                                    endTime
                                    amount
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        try:
            result = self._query(query)
            
            # Extract project data
            projects = result.get('me', {}).get('projects', {}).get('edges', [])
            
            usage_data = {
                'timestamp': datetime.now().isoformat(),
                'projects': [],
                'total_spend': 0.0,
                'spend_limit': 0.0,
                'percent_used': 0.0
            }
            
            for edge in projects:
                project = edge.get('node', {})
                billing = project.get('billing', {})
                
                project_data = {
                    'id': project.get('id'),
                    'name': project.get('name'),
                    'current_spend': billing.get('currentSpend', 0),
                    'spend_limit': billing.get('spendLimit', 0)
                }
                
                usage_data['projects'].append(project_data)
                usage_data['total_spend'] += project_data['current_spend']
                usage_data['spend_limit'] += project_data['spend_limit']
            
            # Calculate percentage
            if usage_data['spend_limit'] > 0:
                usage_data['percent_used'] = (usage_data['total_spend'] / usage_data['spend_limit']) * 100
            
            return usage_data
            
        except Exception as e:
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'total_spend': 0.0,
                'percent_used': 0.0
            }
    
    def check_thresholds(self, usage: Dict) -> List[Dict]:
        """Check if usage exceeds thresholds and return alerts."""
        alerts = []
        
        current_spend = usage.get('total_spend', 0)
        percent_used = usage.get('percent_used', 0)
        
        # Check critical threshold
        if current_spend >= self.critical_threshold:
            alerts.append({
                'level': 'CRITICAL',
                'message': f"Cost critical: ${current_spend:.2f} exceeds critical threshold ${self.critical_threshold:.2f}",
                'current': current_spend,
                'threshold': self.critical_threshold,
                'percent_used': percent_used
            })
        # Check warning threshold
        elif current_spend >= self.threshold:
            alerts.append({
                'level': 'WARNING',
                'message': f"Cost warning: ${current_spend:.2f} exceeds threshold ${self.threshold:.2f}",
                'current': current_spend,
                'threshold': self.threshold,
                'percent_used': percent_used
            })
        
        return alerts
    
    def log_daily_cost(self, usage: Dict):
        """Log daily cost to file."""
        log_entry = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.now().isoformat(),
            'total_spend': usage.get('total_spend', 0),
            'spend_limit': usage.get('spend_limit', 0),
            'percent_used': usage.get('percent_used', 0),
            'projects': usage.get('projects', [])
        }
        
        # Append to log file
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def get_cost_trend(self, days: int = 7) -> Dict:
        """Get cost trend over the last N days."""
        if not LOG_FILE.exists():
            return {'error': 'No cost data available'}
        
        entries = []
        with open(LOG_FILE, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
        
        # Sort by date
        entries.sort(key=lambda x: x.get('date', ''))
        
        # Get last N days
        recent_entries = entries[-days:] if len(entries) > days else entries
        
        if not recent_entries:
            return {'error': 'No recent cost data'}
        
        # Calculate trend
        spends = [e.get('total_spend', 0) for e in recent_entries]
        avg_spend = sum(spends) / len(spends) if spends else 0
        
        # Project monthly cost based on recent average
        days_counted = len(recent_entries)
        if days_counted > 0:
            daily_avg = avg_spend / days_counted if days_counted > 0 else 0
            projected_monthly = daily_avg * 30
        else:
            projected_monthly = 0
        
        return {
            'days_analyzed': days_counted,
            'average_spend': round(avg_spend, 2),
            'projected_monthly': round(projected_monthly, 2),
            'recent_entries': recent_entries
        }
    
    def send_alert(self, alert: Dict):
        """Send alert via available channels."""
        print(f"\n🚨 COST ALERT [{alert['level']}]")
        print(f"   {alert['message']}")
        print(f"   Current: ${alert['current']:.2f} | Threshold: ${alert['threshold']:.2f}")
        
        # Could extend to send to webhook, email, etc.
        webhook_url = os.environ.get('ALERT_WEBHOOK_URL')
        if webhook_url:
            try:
                with httpx.Client(timeout=10.0) as client:
                    client.post(webhook_url, json={
                        'level': alert['level'],
                        'message': alert['message'],
                        'timestamp': datetime.now().isoformat(),
                        'service': 'cost_monitor'
                    })
            except Exception as e:
                print(f"   Failed to send webhook alert: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Railway Cost Monitor')
    parser.add_argument('--check', action='store_true', 
                       help='Check current usage and send alerts if needed')
    parser.add_argument('--daily-log', action='store_true',
                       help='Log current usage to daily cost log')
    parser.add_argument('--trend', type=int, metavar='DAYS',
                       help='Show cost trend for last N days')
    parser.add_argument('--threshold', type=float,
                       help='Set alert threshold (overrides env var)')
    
    args = parser.parse_args()
    
    try:
        monitor = RailwayCostMonitor()
        
        if args.threshold:
            monitor.threshold = args.threshold
        
        # Get current usage
        usage = monitor.get_current_usage()
        
        if 'error' in usage:
            print(f"❌ Error fetching usage: {usage['error']}")
            sys.exit(1)
        
        print("\n📊 Railway Cost Report")
        print("=" * 50)
        print(f"Timestamp: {usage['timestamp']}")
        print(f"Total Spend: ${usage['total_spend']:.2f}")
        print(f"Spend Limit: ${usage['spend_limit']:.2f}")
        print(f"Percent Used: {usage['percent_used']:.1f}%")
        
        if usage['projects']:
            print("\nProjects:")
            for proj in usage['projects']:
                print(f"  - {proj['name']}: ${proj['current_spend']:.2f}")
        
        # Check thresholds
        if args.check:
            alerts = monitor.check_thresholds(usage)
            for alert in alerts:
                monitor.send_alert(alert)
            
            if not alerts:
                print(f"\n✅ Costs within normal range (threshold: ${monitor.threshold:.2f})")
        
        # Log daily cost
        if args.daily_log:
            monitor.log_daily_cost(usage)
            print(f"\n📝 Logged to {LOG_FILE}")
        
        # Show trend
        if args.trend:
            trend = monitor.get_cost_trend(args.trend)
            if 'error' not in trend:
                print(f"\n📈 {args.trend}-Day Trend")
                print(f"   Average Spend: ${trend['average_spend']:.2f}")
                print(f"   Projected Monthly: ${trend['projected_monthly']:.2f}")
            else:
                print(f"\n⚠️ {trend['error']}")
        
        print()
        
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
