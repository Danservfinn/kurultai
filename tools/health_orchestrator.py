"""
Health Check Orchestrator for Kurultai System

Provides comprehensive health checking for:
- Neo4j database connectivity and operations
- OpenClaw gateway WebSocket and HTTP availability
- Agent heartbeat freshness (two-tier system)
- HTTP service endpoints

Usage:
    from tools.health_orchestrator import run_health_check, format_results

    # Run all health checks
    results = run_health_check()

    # Run specific categories
    results = run_health_check(categories=["neo4j", "openclaw"])

    # Format and display results
    print(format_results(results, format="table"))
    print(format_results(results, format="json"))
    print(format_results(results, format="emoji"))
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable


class HealthStatus(Enum):
    """Health check status values."""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class OutputFormat(Enum):
    """Output format options."""
    TABLE = "table"
    EMOJI = "emoji"
    JSON = "json"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    category: str
    check_name: str
    status: HealthStatus
    latency_ms: int
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """Complete health check report."""
    check_id: str
    timestamp: str
    duration_ms: int
    results: List[HealthCheckResult]
    summary: Dict[str, Any] = field(default_factory=dict)


def run_health_check(
    categories: Optional[List[str]] = None,
    config: Optional[Dict[str, str]] = None,
    parallel: bool = True,
    timeout_per_check: int = 30,
) -> HealthReport:
    """
    Run health checks for specified categories.

    Args:
        categories: List of categories to check (default: all)
        config: Configuration dict (uses env vars if None)
        parallel: Run checks in parallel
        timeout_per_check: Timeout per check in seconds

    Returns:
        Complete health report
    """
    start = time.time()
    check_id = f"health-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    if config is None:
        config = get_default_config()

    if categories is None:
        categories = ["neo4j", "openclaw", "heartbeat", "services"]

    results = []

    # Define check functions
    check_functions = {
        "neo4j": check_neo4j_health,
        "openclaw": check_openclaw_health,
        "heartbeat": check_heartbeat_freshness,
        "services": check_services_health,
    }

    if parallel:
        # Run checks in parallel
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run_parallel():
            tasks = []
            for category in categories:
                if category in check_functions:
                    func = check_functions[category]
                    tasks.append(run_in_executor(func, config, timeout_per_check))
            return await asyncio.gather(*tasks, return_exceptions=True)

        parallel_results = loop.run_until_complete(run_parallel())
        loop.close()

        for pr in parallel_results:
            if isinstance(pr, Exception):
                results.append(HealthCheckResult(
                    category="error",
                    check_name="parallel_execution",
                    status=HealthStatus.FAIL,
                    latency_ms=0,
                    details={"error": str(pr)}
                ))
            elif isinstance(pr, dict):
                for cat, res in pr.items():
                    results.append(HealthCheckResult(
                        category=cat,
                        check_name=res.get("check_name", cat),
                        status=HealthStatus(res.get("status", "fail")),
                        latency_ms=res.get("latency_ms", 0),
                        details=res.get("details", {})
                    ))
    else:
        # Run checks sequentially
        for category in categories:
            if category in check_functions:
                func = check_functions[category]
                result = func(config)
                results.append(HealthCheckResult(
                    category=category,
                    check_name=category,
                    status=HealthStatus(result.get("status", "fail")),
                    latency_ms=result.get("latency_ms", 0),
                    details=result.get("details", {})
                ))

    duration_ms = int((time.time() - start) * 1000)

    # Calculate summary
    summary = calculate_summary(results)

    return HealthReport(
        check_id=check_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        results=results,
        summary=summary,
    )


async def run_in_executor(
    func: Callable,
    config: Dict[str, Any],
    timeout: int
) -> Dict[str, Any]:
    """Run a function in an executor with timeout."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, config)


def get_default_config() -> Dict[str, str]:
    """Get default configuration from environment variables."""
    return {
        # Neo4j
        "neo4j_uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "neo4j_user": os.getenv("NEO4J_USER", "neo4j"),
        "neo4j_password": os.getenv("NEO4J_PASSWORD", ""),

        # OpenClaw
        "openclaw_ws_url": os.getenv("OPENCLAW_WS_URL", "ws://localhost:18789"),
        "openclaw_http_url": os.getenv("OPENCLAW_HTTP_URL", "http://localhost:18789"),
        "openclaw_token": os.getenv("OPENCLAW_TOKEN", ""),

        # Services
        "authentik_proxy_url": os.getenv("AUTHENTIK_PROXY_URL", "http://localhost:9000"),
        "moltbot_url": os.getenv("MOLTBOT_URL", "http://localhost:18789"),

        # Thresholds
        "heartbeat_threshold_s": int(os.getenv("HEARTBEAT_THRESHOLD_S", "90")),
        "query_timeout_ms": int(os.getenv("QUERY_TIMEOUT_MS", "1000")),
        "gateway_latency_ms": int(os.getenv("GATEWAY_LATENCY_MS", "5000")),
    }


def check_neo4j_health(config: Dict[str, str], timeout_ms: int = 1000) -> Dict[str, Any]:
    """Check Neo4j database health."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return {
            "status": "fail",
            "latency_ms": 0,
            "details": {"error": "neo4j package not installed"}
        }

    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {"connectivity": False}
    }

    try:
        driver = GraphDatabase.driver(
            config["neo4j_uri"],
            auth=(config["neo4j_user"], config["neo4j_password"]),
            max_connection_lifetime=30
        )

        driver.verify_connectivity()
        result["details"]["connectivity"] = True

        with driver.session() as session:
            # Test Cypher execution
            query_start = time.time()
            session.run("RETURN 1 AS ping").single()
            query_latency = (time.time() - query_start) * 1000
            result["details"]["query_latency_ms"] = round(query_latency, 2)
            result["details"]["cypher_executable"] = True

            if query_latency > timeout_ms:
                result["status"] = "warn"
                result["details"]["warning"] = f"Query latency {query_latency:.2f}ms exceeds threshold"

            # Get node count
            count_result = session.run("MATCH (n) RETURN count(n) AS count")
            result["details"]["node_count"] = count_result.single()["count"]

            # Get database version
            try:
                version_result = session.run(
                    "CALL dbms.components() YIELD versions RETURN versions[0] AS version"
                )
                result["details"]["database_version"] = version_result.single()["version"]
            except Exception:
                result["details"]["database_version"] = "unknown"

        driver.close()

    except Exception as e:
        result["status"] = "fail"
        result["details"]["error"] = str(e)

    result["latency_ms"] = round((time.time() - start) * 1000)
    return {"neo4j": result}


def check_openclaw_health(config: Dict[str, str], timeout_ms: int = 5000) -> Dict[str, Any]:
    """Check OpenClaw gateway health."""
    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {"ws_connected": False, "http_healthy": False}
    }

    # Check HTTP endpoint
    try:
        import requests
        response = requests.get(
            f"{config['openclaw_http_url']}/health",
            timeout=5
        )
        if response.status_code == 200:
            result["details"]["http_healthy"] = True
            try:
                result["details"].update(response.json())
            except ValueError:
                pass
    except Exception as e:
        result["details"]["http_error"] = str(e)

    # Check WebSocket
    try:
        import websockets
        import json as ws_json

        async def ws_check():
            try:
                async with websockets.connect(
                    config["openclaw_ws_url"],
                    close_timeout=5
                ) as ws:
                    return True
            except Exception:
                return False

        result["details"]["ws_connected"] = asyncio.run(ws_check())
    except Exception as e:
        result["details"]["ws_error"] = str(e)

    # Determine status
    http_ok = result["details"].get("http_healthy", False)
    ws_ok = result["details"].get("ws_connected", False)

    if http_ok and ws_ok:
        result["status"] = "pass"
    elif http_ok or ws_ok:
        result["status"] = "warn"
    else:
        result["status"] = "fail"

    result["latency_ms"] = round((time.time() - start) * 1000)
    return {"openclaw": result}


def check_heartbeat_freshness(config: Dict[str, str]) -> Dict[str, Any]:
    """Check agent heartbeat freshness (two-tier system)."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return {
            "heartbeat": {
                "status": "fail",
                "latency_ms": 0,
                "details": {"error": "neo4j package not installed"}
            }
        }

    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {
            "agents_checked": 0,
            "stale_agents": [],
            "oldest_heartbeat_age_s": 0,
            "two_tier_valid": False,
        }
    }

    try:
        driver = GraphDatabase.driver(
            config["neo4j_uri"],
            auth=(config["neo4j_user"], config["neo4j_password"])
        )

        with driver.session() as session:
            now = datetime.now(timezone.utc)
            threshold_s = config.get("heartbeat_threshold_s", 90)

            # Check both heartbeat types
            query = """
            MATCH (a:Agent)
            RETURN a.name AS name,
                   a.infra_heartbeat AS infra_ts,
                   a.last_heartbeat AS last_ts
            """
            records = session.run(query)

            agents_checked = set()
            stale_agents = []
            oldest_age = 0

            for record in records:
                name = record["name"]
                agents_checked.add(name)

                # Check infra heartbeat
                infra_ts = record["infra_ts"]
                if infra_ts is not None:
                    if isinstance(infra_ts, str):
                        ts = datetime.fromisoformat(infra_ts.replace('Z', '+00:00'))
                    else:
                        ts = infra_ts
                    age = (now - ts).total_seconds()
                    oldest_age = max(oldest_age, age)
                    if age > threshold_s:
                        stale_agents.append({
                            "name": name,
                            "age_s": int(age),
                            "type": "infra"
                        })

                # Check last heartbeat
                last_ts = record["last_ts"]
                if last_ts is not None:
                    if isinstance(last_ts, str):
                        ts = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
                    else:
                        ts = last_ts
                    age = (now - ts).total_seconds()
                    oldest_age = max(oldest_age, age)
                    if age > threshold_s:
                        existing = next(
                            (s for s in stale_agents if s["name"] == name),
                            None
                        )
                        if not existing:
                            stale_agents.append({
                                "name": name,
                                "age_s": int(age),
                                "type": "functional"
                            })

            result["details"]["agents_checked"] = len(agents_checked)
            result["details"]["stale_agents"] = stale_agents
            result["details"]["oldest_heartbeat_age_s"] = int(oldest_age)
            result["details"]["two_tier_valid"] = len(stale_agents) == 0

            if stale_agents:
                result["status"] = "fail"

        driver.close()

    except Exception as e:
        result["status"] = "fail"
        result["details"]["error"] = str(e)

    result["latency_ms"] = round((time.time() - start) * 1000)
    return {"heartbeat": result}


def check_services_health(config: Dict[str, str]) -> Dict[str, Any]:
    """Check HTTP service endpoints."""
    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {
            "total_services": 0,
            "healthy_services": 0,
            "degraded_services": 0,
            "unhealthy_services": 0,
            "services": []
        }
    }

    services = [
        ("authentik_proxy", config.get("authentik_proxy_url", "http://localhost:9000")),
        ("moltbot", config.get("moltbot_url", "http://localhost:18789")),
    ]

    try:
        import requests
    except ImportError:
        result["details"]["error"] = "requests library not installed"
        result["status"] = "skip"
        result["latency_ms"] = round((time.time() - start) * 1000)
        return {"services": result}

    for name, url in services:
        result["details"]["total_services"] += 1
        service_result = {"name": name, "url": url, "status": "unknown", "latency_ms": 0}

        try:
            service_start = time.time()
            response = requests.get(f"{url}/health", timeout=5)
            service_latency_ms = (time.time() - service_start) * 1000
            service_result["latency_ms"] = round(service_latency_ms, 2)

            if response.status_code == 200:
                service_result["status"] = "healthy"
                result["details"]["healthy_services"] += 1
            elif response.status_code in [401, 302]:
                service_result["status"] = "healthy"
                result["details"]["healthy_services"] += 1
            else:
                service_result["status"] = "degraded"
                result["details"]["degraded_services"] += 1

        except requests.exceptions.Timeout:
            service_result["status"] = "timeout"
            service_result["error"] = "Request timed out"
            result["details"]["unhealthy_services"] += 1
        except requests.exceptions.ConnectionError:
            service_result["status"] = "unreachable"
            service_result["error"] = "Connection refused"
            result["details"]["unhealthy_services"] += 1
        except Exception as e:
            service_result["status"] = "error"
            service_result["error"] = str(e)
            result["details"]["unhealthy_services"] += 1

        result["details"]["services"].append(service_result)

    # Determine overall status
    unhealthy = result["details"]["unhealthy_services"]
    total = result["details"]["total_services"]

    if unhealthy == 0:
        result["status"] = "pass"
    elif unhealthy < total:
        result["status"] = "warn"
    else:
        result["status"] = "fail"

    result["latency_ms"] = round((time.time() - start) * 1000)
    return {"services": result}


def calculate_summary(results: List[HealthCheckResult]) -> Dict[str, Any]:
    """Calculate summary statistics from health check results."""
    total = len(results)
    passed = sum(1 for r in results if r.status == HealthStatus.PASS)
    failed = sum(1 for r in results if r.status == HealthStatus.FAIL)
    warned = sum(1 for r in results if r.status == HealthStatus.WARN)
    skipped = sum(1 for r in results if r.status == HealthStatus.SKIP)

    # Determine overall status
    if failed > 0:
        overall = "unhealthy"
    elif warned > 0:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "total_checks": total,
        "passed": passed,
        "failed": failed,
        "warnings": warned,
        "skipped": skipped,
        "overall_status": overall
    }


def format_results(report: HealthReport, format: OutputFormat = OutputFormat.TABLE) -> str:
    """
    Format health check results for display.

    Args:
        report: Health check report
        format: Output format (table, emoji, json)

    Returns:
        Formatted string
    """
    if format == OutputFormat.JSON:
        return format_json(report)
    elif format == OutputFormat.EMOJI:
        return format_emoji(report)
    else:
        return format_table(report)


def format_table(report: HealthReport) -> str:
    """Format results as a table."""
    lines = []

    # Header
    lines.append("╔══════════════════════════════════════════════════════════════════╗")
    lines.append("║                    Health Check Report                         ║")
    lines.append(f"║                {report.timestamp[:19]} UTC" + " " * 22 + "║")
    lines.append("╠══════════════════════════════════════════════════════════════════╣")
    lines.append("║ Component           │ Status │ Latency │ Details                  ║")
    lines.append("╠══════════════════════════════════════════════════════════════════╣")

    # Results
    for result in report.results:
        status_str = result.status.value.upper().ljust(6)
        latency_str = f"{result.latency_ms:5d}ms"

        # Format details
        if result.status == HealthStatus.PASS:
            if result.category == "neo4j":
                node_count = result.details.get("node_count", 0)
                version = result.details.get("database_version", "unknown")
                details_str = f"{node_count:,} nodes, v{version}"
            elif result.category == "openclaw":
                sessions = result.details.get("active_sessions", 0)
                details_str = f"{sessions} active sessions"
            elif result.category == "heartbeat":
                agents = result.details.get("agents_checked", 0)
                age = result.details.get("oldest_heartbeat_age_s", 0)
                details_str = f"{agents} agents, newest: {age}s"
            elif result.category == "services":
                healthy = result.details.get("healthy_services", 0)
                total = result.details.get("total_services", 0)
                details_str = f"{healthy}/{total} services healthy"
            else:
                details_str = "OK"
        elif result.status == HealthStatus.WARN:
            details_str = result.details.get("warning", "Warning")[:24]
        else:
            error = result.details.get("error", "Failed")[:24]
            details_str = error

        line = f"║ {result.category[:18]:18} │ {status_str} │ {latency_str} │ {details_str:24} ║"
        lines.append(line)

    # Summary
    lines.append("╠══════════════════════════════════════════════════════════════════╣")
    summary = report.summary
    summary_str = f"Summary: {summary['passed']} pass, {summary['warnings']} warn, {summary['failed']} fail"
    overall_str = f"Overall: {summary['overall_status'].upper()}"
    lines.append(f"║ {summary_str:43} │ {overall_str:16} ║")
    lines.append("╚══════════════════════════════════════════════════════════════════╝")

    return "\n".join(lines)


def format_emoji(report: HealthReport) -> str:
    """Format results with emoji indicators."""
    lines = []

    lines.append(f"health_check {report.timestamp}")
    lines.append("")

    # Status emoji mapping
    emoji_map = {
        HealthStatus.PASS: "PASS",
        HealthStatus.WARN: "WARN",
        HealthStatus.FAIL: "FAIL",
        HealthStatus.SKIP: "SKIP",
    }

    for result in report.results:
        lines.append(f"{result.category}")
        lines.append(f"  status   {emoji_map[result.status]:6} {result.latency_ms}ms")

        # Add details
        if result.category == "neo4j" and result.status == HealthStatus.PASS:
            lines.append(f"  node_count     {result.details.get('node_count', 0):,} nodes")
            lines.append(f"  version        {result.details.get('database_version', 'unknown')}")
        elif result.category == "heartbeat" and result.status == HealthStatus.PASS:
            lines.append(f"  agents_checked {result.details.get('agents_checked', 0)}")
            lines.append(f"  oldest_age     {result.details.get('oldest_heartbeat_age_s', 0)}s")
            lines.append(f"  two_tier_valid  {'YES' if result.details.get('two_tier_valid') else 'NO'}")
        elif result.status != HealthStatus.PASS:
            error = result.details.get("error", "Unknown error")
            lines.append(f"  error          {error}")

        lines.append("")

    lines.append(f"Overall Status: {report.summary['overall_status'].upper()}")

    return "\n".join(lines)


def format_json(report: HealthReport) -> str:
    """Format results as JSON."""
    output = {
        "check_id": report.check_id,
        "timestamp": report.timestamp,
        "duration_ms": report.duration_ms,
        "summary": report.summary,
        "results": []
    }

    for result in report.results:
        output["results"].append({
            "category": result.category,
            "check_name": result.check_name,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "details": result.details
        })

    return json.dumps(output, indent=2)


def main():
    """CLI entry point for health checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Kurultai Health Check")
    parser.add_argument(
        "--categories", "-c",
        nargs="+",
        choices=["neo4j", "openclaw", "heartbeat", "services"],
        help="Categories to check (default: all)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["table", "emoji", "json"],
        default="table",
        help="Output format (default: table)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Timeout per check in seconds (default: 30)"
    )
    parser.add_argument(
        "--sequential", "-s",
        action="store_true",
        help="Run checks sequentially instead of in parallel"
    )

    args = parser.parse_args()

    # Run health checks
    report = run_health_check(
        categories=args.categories,
        parallel=not args.sequential,
        timeout_per_check=args.timeout
    )

    # Format and display results
    output = format_results(report, OutputFormat(args.format))
    print(output)

    # Exit with appropriate code
    if report.summary["overall_status"] == "healthy":
        return 0
    elif report.summary["overall_status"] == "degraded":
        return 1
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())
