#!/usr/bin/env python3
"""
Model Analytics API - HTTP endpoint and utility for model usage stats.

Usage as API:
    python3 model-analytics-api.py --serve --port 8080
    curl http://localhost:8080/api/analytics/models?days=7

Usage as utility:
    python3 model-analytics-api.py --stats --days 7
    python3 model-analytics-api.py --agent temujin --days 7
"""

import argparse
import json
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_tracker import ModelTracker


def get_model_stats(days: int = 7, agent: str = None):
    """Get model statistics."""
    tracker = ModelTracker()
    try:
        stats = tracker.get_model_stats(days=days, agent=agent)
        agent_stats = tracker.get_agent_model_stats(days=days)
        provider_stats = tracker.get_provider_stats(days=days)
        error_breakdown = tracker.get_model_error_breakdown(days=days)

        return {
            "ok": True,
            "timestamp": datetime.now().isoformat(),
            "query": {"days": days, "agent": agent},
            "data": {
                "model_stats": stats,
                "agent_model_stats": agent_stats,
                "provider_stats": provider_stats,
                "error_breakdown": error_breakdown,
            },
        }
    finally:
        tracker.close()


def get_recent_usage(limit: int = 50):
    """Get recent model usage events."""
    tracker = ModelTracker()
    try:
        usage = tracker.get_recent_model_usage(limit=limit)
        return {
            "ok": True,
            "timestamp": datetime.now().isoformat(),
            "data": {"recent_usage": usage},
        }
    finally:
        tracker.close()


class ModelAnalyticsHandler(BaseHTTPRequestHandler):
    """HTTP request handler for model analytics API."""

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # Parse query params
        days = int(params.get("days", [7])[0])
        agent = params.get("agent", [None])[0]
        limit = int(params.get("limit", [50])[0])

        if path == "/api/analytics/models":
            # Main model stats endpoint
            result = get_model_stats(days=days, agent=agent)
            self._send_json(result)

        elif path == "/api/analytics/models/recent":
            # Recent usage endpoint
            result = get_recent_usage(limit=limit)
            self._send_json(result)

        elif path == "/health":
            # Health check
            self._send_json({"ok": True, "timestamp": datetime.now().isoformat()})

        else:
            self._send_json(
                {"ok": False, "error": "Not found", "paths": ["/api/analytics/models", "/api/analytics/models/recent", "/health"]},
                status=404,
            )

    def log_message(self, format, *args):
        print(f"[{datetime.now().isoformat()}] {args[0]}")


def serve(port: int):
    """Start HTTP server."""
    server = HTTPServer(("localhost", port), ModelAnalyticsHandler)
    print(f"Model Analytics API server starting on http://localhost:{port}")
    print(f"Endpoints:")
    print(f"  GET /api/analytics/models?days=7&agent=temujin")
    print(f"  GET /api/analytics/models/recent?limit=50")
    print(f"  GET /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Model Analytics API")
    parser.add_argument("--serve", action="store_true", help="Start HTTP server")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--stats", action="store_true", help="Print model stats")
    parser.add_argument("--recent", action="store_true", help="Print recent usage")
    parser.add_argument("--days", type=int, default=7, help="Days to query (default: 7)")
    parser.add_argument("--agent", type=str, help="Filter by agent")
    parser.add_argument("--limit", type=int, default=50, help="Recent usage limit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.serve:
        serve(args.port)
        return

    if args.stats:
        result = get_model_stats(days=args.days, agent=args.agent)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            data = result["data"]
            print(f"\n=== Model Stats (Last {args.days} days) ===")
            for m in data["model_stats"]:
                print(f"  {m['model']} ({m['provider']}): {m['total']} tasks, {m['success_rate']}% success, {m['avg_duration_seconds']}s avg")

            print(f"\n=== Provider Stats ===")
            for p in data["provider_stats"]:
                print(f"  {p['provider']}: {p['total']} tasks, {p['success_rate']}% success")

            if args.agent and data["agent_model_stats"]:
                print(f"\n=== {args.agent} Model Stats ===")
                for m in data["agent_model_stats"].get(args.agent, []):
                    print(f"  {m['model']}: {m['total']} tasks, {m['success_rate']}% success")

            print(f"\n=== Error Breakdown ===")
            for model, errors in data["error_breakdown"].items():
                print(f"  {model}:")
                for e in errors:
                    print(f"    - {e['error_type']}: {e['count']}")

        return

    if args.recent:
        result = get_recent_usage(limit=args.limit)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Recent Model Usage (Last {args.limit} events) ===")
            for entry in result["data"]["recent_usage"]:
                status = "✓" if entry.get("success") else "✗"
                print(f"  {entry['ts']}: {entry['agent']} used {entry['model']} - {status}")
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
