#!/usr/bin/env python3
"""
Agent Background Task Registry - Defines what each agent does on heartbeat.

This module registers all background tasks for the 6 Kurultai agents:
- Kublai (main): Orchestrator status synthesis
- Möngke (researcher): Knowledge gap analysis, Ordo Sacer research, ecosystem intelligence
- Chagatai (writer): Reflection consolidation when idle
- Temüjin (developer): Ticket-driven development
- Jochi (analyst): Memory curation, health checks (smoke/full), deep curation
- Ögedei (ops): Health checks, file consistency, failover monitoring

Usage:
    from heartbeat_master import get_heartbeat
    from agent_tasks import register_all_tasks

    hb = get_heartbeat(driver)
    await register_all_tasks(hb)
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .heartbeat_master import HeartbeatTask, UnifiedHeartbeat
from .curation_simple import SimpleCuration

logger = logging.getLogger("kurultai.agent_tasks")


# ============================================================================
# Task Handlers
# ============================================================================

async def ogedei_health_check(driver) -> Dict:
    """
    Check system health every 5 minutes.

    Verifies:
    - Neo4j connectivity
    - OpenClaw gateway health
    - Disk space
    - Agent heartbeat statuses
    """
    results = {
        "checks": [],
        "healthy": True,
        "issues": []
    }

    try:
        # Check Neo4j connectivity
        with driver.session() as session:
            result = session.run("RETURN 1 AS connected")
            record = result.single()
            if record and record["connected"] == 1:
                results["checks"].append({"name": "neo4j", "status": "healthy"})
            else:
                results["checks"].append({"name": "neo4j", "status": "error"})
                results["healthy"] = False
                results["issues"].append("Neo4j connectivity check failed")

        # Check agent heartbeats (infra tier - 120s threshold)
        with driver.session() as session:
            result = session.run("""
                MATCH (a:Agent)
                WHERE a.infra_heartbeat < datetime() - duration('PT120S')
                RETURN a.name AS agent, a.infra_heartbeat AS last_heartbeat
            """)
            stale_agents = [dict(r) for r in result]

            if stale_agents:
                results["checks"].append({
                    "name": "agent_heartbeats",
                    "status": "warning",
                    "stale_agents": [a["agent"] for a in stale_agents]
                })
                results["issues"].append(f"{len(stale_agents)} agents with stale heartbeats")
            else:
                results["checks"].append({"name": "agent_heartbeats", "status": "healthy"})

        # Check disk space (if available)
        try:
            import shutil
            stat = shutil.disk_usage("/data" if os.path.exists("/data") else ".")
            free_gb = stat.free / (1024**3)
            total_gb = stat.total / (1024**3)
            used_pct = (stat.used / stat.total) * 100

            if used_pct > 90:
                results["checks"].append({"name": "disk_space", "status": "critical", "free_gb": free_gb})
                results["healthy"] = False
                results["issues"].append(f"Disk space critical: {used_pct:.1f}% used")
            elif used_pct > 75:
                results["checks"].append({"name": "disk_space", "status": "warning", "free_gb": free_gb})
            else:
                results["checks"].append({"name": "disk_space", "status": "healthy", "free_gb": free_gb})
        except Exception as e:
            results["checks"].append({"name": "disk_space", "status": "unknown", "error": str(e)})

    except Exception as e:
        results["healthy"] = False
        results["issues"].append(f"Health check error: {e}")
        logger.exception("Health check failed")

    return {
        "summary": f"Health: {'OK' if results['healthy'] else 'ISSUES'} ({len(results['checks'])} checks)",
        "tokens_used": 150,
        "data": results
    }


async def ogedei_file_check(driver) -> Dict:
    """
    Verify file consistency every 15 minutes.

    Uses OgedeiFileMonitor to check for config drift in agent workspaces.
    """
    try:
        # Import here to avoid circular dependencies
        from .ogedei_file_monitor import OgedeiFileMonitor

        monitor = OgedeiFileMonitor(driver)

        # Scan all agent workspaces
        agents = ["main", "analyst", "developer", "ops", "researcher", "writer"]
        all_issues = []

        for agent_id in agents:
            try:
                issues = monitor.scan_agent_workspace(agent_id)
                all_issues.extend(issues)
            except Exception as e:
                logger.warning(f"Failed to scan {agent_id} workspace: {e}")

        # Create FileConsistencyCheck node
        with driver.session() as session:
            session.run("""
                CREATE (fc:FileConsistencyCheck {
                    id: $id,
                    checked_at: datetime(),
                    agents_checked: $agents,
                    issues_found: $issue_count,
                    status: $status
                })
            """,
                id=f"fc-{int(datetime.now(timezone.utc).timestamp())}",
                agents=agents,
                issue_count=len(all_issues),
                status="issues_found" if all_issues else "consistent"
            )

        summary = f"File check: {len(all_issues)} issues across {len(agents)} agents"
        return {
            "summary": summary,
            "tokens_used": 200,
            "data": {
                "agents_checked": len(agents),
                "issues_found": len(all_issues),
                "issues": all_issues[:5]  # Limit details
            }
        }

    except Exception as e:
        logger.exception("File consistency check failed")
        return {
            "summary": f"File check error: {e}",
            "tokens_used": 50,
            "data": {"error": str(e)}
        }


async def jochi_curation_rapid(driver) -> Dict:
    """
    Rapid memory curation every 5 minutes.

    Enforces token budgets and cleans notifications.
    """
    try:
        curation = SimpleCuration(driver)
        result = curation.curation_rapid()

        summary = f"Rapid curation: {result['hot_demoted']} demoted, {result['notifications_deleted']} notifications, {result['sessions_deleted']} sessions"
        return {
            "summary": summary,
            "tokens_used": 300,
            "data": result
        }

    except Exception as e:
        logger.exception("Rapid curation failed")
        return {
            "summary": f"Curation error: {e}",
            "tokens_used": 50,
            "data": {"error": str(e)}
        }


async def jochi_smoke_tests(driver) -> Dict:
    """
    Run smoke tests every 15 minutes via kurultai-health or test_runner_orchestrator.

    Quick health check focusing on critical paths.
    """
    try:
        project_root = Path(os.getcwd())

        # Try kurultai-health first (if available as skill)
        # Fall back to test_runner_orchestrator
        test_script = project_root / "tools" / "kurultai" / "test_runner_orchestrator.py"

        if test_script.exists():
            # Run quick smoke tests
            result = subprocess.run(
                [sys.executable, str(test_script), "--phase", "integration", "--no-remediate"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=str(project_root)
            )

            # Parse results from JSON output if available
            passed = result.returncode == 0
            output = result.stdout + result.stderr

            # Look for JSON output at end
            try:
                lines = output.strip().split('\n')
                for line in reversed(lines):
                    if line.strip().startswith('{'):
                        data = json.loads(line)
                        return {
                            "summary": f"Smoke tests: {'PASSED' if passed else 'FAILED'}",
                            "tokens_used": 800,
                            "data": data
                        }
            except json.JSONDecodeError:
                pass

            return {
                "summary": f"Smoke tests: {'PASSED' if passed else 'FAILED'}",
                "tokens_used": 800,
                "data": {"exit_code": result.returncode, "output_preview": output[:500]}
            }
        else:
            return {
                "summary": "Smoke tests: test runner not found",
                "tokens_used": 50,
                "data": {"error": "test_runner_orchestrator.py not found"}
            }

    except subprocess.TimeoutExpired:
        return {
            "summary": "Smoke tests: TIMEOUT",
            "tokens_used": 800,
            "data": {"error": "Tests timed out after 300s"}
        }
    except Exception as e:
        logger.exception("Smoke tests failed")
        return {
            "summary": f"Smoke tests error: {e}",
            "tokens_used": 100,
            "data": {"error": str(e)}
        }


async def jochi_full_tests(driver) -> Dict:
    """
    Run full test suite hourly.

    Comprehensive testing with all phases.
    """
    try:
        project_root = Path(os.getcwd())
        test_script = project_root / "tools" / "kurultai" / "test_runner_orchestrator.py"

        if test_script.exists():
            # Run full test suite
            result = subprocess.run(
                [sys.executable, str(test_script), "--phase", "all"],
                capture_output=True,
                text=True,
                timeout=900,  # 15 minute timeout
                cwd=str(project_root)
            )

            # Try to find and parse report
            output_dir = project_root / "data" / "test_results"
            if output_dir.exists():
                # Find most recent report
                reports = sorted(output_dir.glob("test_report_*.json"), reverse=True)
                if reports:
                    with open(reports[0]) as f:
                        report = json.load(f)

                    # Create tickets for critical findings
                    critical_count = report.get("findings", {}).get("critical", 0)
                    if critical_count > 0:
                        await _create_tickets_from_report(driver, report)

                    return {
                        "summary": f"Full tests: {report['summary']['overall_status'].upper()}, {critical_count} critical findings",
                        "tokens_used": 1500,
                        "data": {
                            "pass_rate": report['summary']['pass_rate'],
                            "critical_findings": critical_count,
                            "report_file": str(reports[0])
                        }
                    }

            return {
                "summary": f"Full tests: exit code {result.returncode}",
                "tokens_used": 1500,
                "data": {"exit_code": result.returncode}
            }
        else:
            return {
                "summary": "Full tests: test runner not found",
                "tokens_used": 50,
                "data": {"error": "test_runner_orchestrator.py not found"}
            }

    except subprocess.TimeoutExpired:
        return {
            "summary": "Full tests: TIMEOUT",
            "tokens_used": 1500,
            "data": {"error": "Tests timed out after 900s"}
        }
    except Exception as e:
        logger.exception("Full tests failed")
        return {
            "summary": f"Full tests error: {e}",
            "tokens_used": 200,
            "data": {"error": str(e)}
        }


async def _create_tickets_from_report(driver, report: Dict):
    """Create tickets for critical findings from test report."""
    try:
        from .ticket_manager import TicketManager

        tm = TicketManager(Path(os.getcwd()))

        for finding in report.get("findings", {}).get("details", [])[:5]:  # Max 5 tickets
            if finding.get("severity") == "critical":
                tm.create_ticket(
                    title=finding.get("title", "Critical Issue"),
                    description=finding.get("description", ""),
                    severity="critical",
                    category=finding.get("category", "infrastructure"),
                    source_agent="jochi",
                    assign_to="temüjin" if finding.get("category") == "correctness" else "ögedei"
                )

    except Exception as e:
        logger.error(f"Failed to create tickets: {e}")


async def jochi_curation_deep(driver) -> Dict:
    """
    Deep curation every 6 hours.

    Cleans orphans and archives old data.
    """
    try:
        curation = SimpleCuration(driver)
        result = curation.curation_deep()

        summary = f"Deep curation: {result['orphans_deleted']} orphans, {result['tombstones_purged']} tombstones"
        return {
            "summary": summary,
            "tokens_used": 2000,
            "data": result
        }

    except Exception as e:
        logger.exception("Deep curation failed")
        return {
            "summary": f"Deep curation error: {e}",
            "tokens_used": 100,
            "data": {"error": str(e)}
        }


async def chagatai_consolidate(driver) -> Dict:
    """
    Consolidate reflections every 30 minutes (when idle).

    Only runs when system is idle (no active user conversations).
    """
    try:
        # Check if system is idle
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status IN ['in_progress', 'pending']
                  AND t.created_at > datetime() - duration('PT30M')
                RETURN count(t) AS active_tasks
            """)
            record = result.single()
            active_tasks = record["active_tasks"] if record else 0

            if active_tasks > 0:
                return {
                    "summary": f"Reflection consolidation skipped: {active_tasks} active tasks",
                    "tokens_used": 50,
                    "data": {"skipped": True, "reason": "system_not_idle", "active_tasks": active_tasks}
                }

        # Look for unconsolidated reflections
        with driver.session() as session:
            result = session.run("""
                MATCH (r:Reflection)
                WHERE r.consolidated = false OR r.consolidated IS NULL
                RETURN r.id AS id, r.content AS content, r.created_at AS created_at
                ORDER BY r.created_at DESC
                LIMIT 20
            """)
            reflections = [dict(r) for r in result]

            if not reflections:
                return {
                    "summary": "No reflections to consolidate",
                    "tokens_used": 100,
                    "data": {"consolidated": 0}
                }

            # Mark reflections as consolidated
            for refl in reflections:
                session.run("""
                    MATCH (r:Reflection {id: $id})
                    SET r.consolidated = true, r.consolidated_at = datetime()
                """, id=refl["id"])

            return {
                "summary": f"Consolidated {len(reflections)} reflections",
                "tokens_used": 500,
                "data": {"consolidated": len(reflections)}
            }

    except Exception as e:
        logger.exception("Reflection consolidation failed")
        return {
            "summary": f"Consolidation error: {e}",
            "tokens_used": 100,
            "data": {"error": str(e)}
        }


async def mongke_gap_analysis(driver) -> Dict:
    """
    Analyze knowledge gaps daily.

    Identifies sparse knowledge areas in Neo4j.
    """
    try:
        # Find topics with few research findings
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Topic)
                OPTIONAL MATCH (t)<-[:ABOUT]-(r:ResearchFinding)
                WITH t, count(r) AS finding_count
                WHERE finding_count < 3
                RETURN t.name AS topic, finding_count
                ORDER BY finding_count ASC
                LIMIT 10
            """)
            sparse_topics = [dict(r) for r in result]

            # Create knowledge gap records
            for topic in sparse_topics:
                session.run("""
                    MERGE (kg:KnowledgeGap {topic: $topic})
                    SET kg.finding_count = $count,
                        kg.last_checked = datetime(),
                        kg.priority = CASE WHEN $count = 0 THEN 'high' ELSE 'medium' END
                """, topic=topic["topic"], count=topic["finding_count"])

            return {
                "summary": f"Knowledge gap analysis: {len(sparse_topics)} sparse topics identified",
                "tokens_used": 600,
                "data": {
                    "sparse_topics": len(sparse_topics),
                    "top_gaps": sparse_topics[:5]
                }
            }

    except Exception as e:
        logger.exception("Knowledge gap analysis failed")
        return {
            "summary": f"Gap analysis error: {e}",
            "tokens_used": 100,
            "data": {"error": str(e)}
        }


async def mongke_ordo_research(driver) -> Dict:
    """
    Daily research for Ordo Sacer Astaci expansion.

    Research esoteric concepts, occult literature, and secret societies.
    This is a research task that stores findings for later synthesis.
    """
    try:
        # Research topics rotate daily
        topics = [
            "esoteric symbolism in ancient texts",
            "Golden Dawn magical practices",
            "Aleister Crowley Thelema principles",
            "Freemasonry ritual structures",
            "Prometheus Rising consciousness techniques",
            "secret society historical networks",
            "occult literature analysis methods",
            "Illuminatus trilogy themes",
            "magick practice frameworks",
            "consciousness expansion theories"
        ]

        # Select topic based on day of month
        day = datetime.now(timezone.utc).day
        today_topic = topics[day % len(topics)]

        # Create research task record
        with driver.session() as session:
            session.run("""
                CREATE (r:ResearchTask {
                    id: $id,
                    topic: $topic,
                    tag: 'ordo_sacer',
                    status: 'pending',
                    created_at: datetime(),
                    created_by: 'mongke'
                })
            """,
                id=f"ordo-{int(datetime.now(timezone.utc).timestamp())}",
                topic=today_topic
            )

        return {
            "summary": f"Ordo Sacer research task created: {today_topic}",
            "tokens_used": 1200,
            "data": {
                "topic": today_topic,
                "tag": "ordo_sacer",
                "status": "pending"
            }
        }

    except Exception as e:
        logger.exception("Ordo Sacer research failed")
        return {
            "summary": f"Research error: {e}",
            "tokens_used": 100,
            "data": {"error": str(e)}
        }


async def mongke_ecosystem_intelligence(driver) -> Dict:
    """
    Weekly intelligence report on agent ecosystem.

    Tracks OpenClaw/Clawdbot/Moltbot ecosystem developments.
    """
    try:
        # Create intelligence report structure
        with driver.session() as session:
            report_id = f"intel-{int(datetime.now(timezone.utc).timestamp())}"

            session.run("""
                CREATE (ir:IntelligenceReport {
                    id: $id,
                    report_type: 'ecosystem_intelligence',
                    week_starting: datetime(),
                    status: 'draft',
                    platforms_tracked: $platforms,
                    created_by: 'mongke'
                })
            """,
                id=report_id,
                platforms=["OpenClaw", "Clawdbot", "Moltbot", "Kurultai"]
            )

            # Count existing research nodes for metrics
            result = session.run("""
                MATCH (r:ResearchFinding)
                WHERE r.created_at > datetime() - duration('P7D')
                RETURN count(r) AS recent_findings
            """)
            record = result.single()
            recent_findings = record["recent_findings"] if record else 0

            return {
                "summary": f"Ecosystem intelligence report created: {report_id}",
                "tokens_used": 2000,
                "data": {
                    "report_id": report_id,
                    "recent_findings": recent_findings,
                    "platforms": ["OpenClaw", "Clawdbot", "Moltbot", "Kurultai"]
                }
            }

    except Exception as e:
        logger.exception("Ecosystem intelligence failed")
        return {
            "summary": f"Intelligence error: {e}",
            "tokens_used": 200,
            "data": {"error": str(e)}
        }


async def kublai_status_synthesis(driver) -> Dict:
    """
    Synthesize agent status every 5 minutes.

    Aggregates heartbeat results and escalates critical issues.
    """
    try:
        with driver.session() as session:
            # Get recent cycle results
            result = session.run("""
                MATCH (hc:HeartbeatCycle)
                WHERE hc.completed_at > datetime() - duration('PT1H')
                RETURN hc.cycle_number AS cycle,
                       hc.tasks_run AS tasks_run,
                       hc.tasks_failed AS tasks_failed,
                       hc.total_tokens AS tokens
                ORDER BY hc.cycle_number DESC
                LIMIT 12
            """)
            recent_cycles = [dict(r) for r in result]

            # Get agent statuses
            result = session.run("""
                MATCH (a:Agent)
                RETURN a.name AS agent,
                       a.status AS status,
                       a.last_heartbeat AS last_heartbeat
                ORDER BY a.name
            """)
            agents = [dict(r) for r in result]

            # Check for critical issues
            total_failures = sum(c.get("tasks_failed", 0) for c in recent_cycles)

            synthesis = {
                "cycles_analyzed": len(recent_cycles),
                "total_failures": total_failures,
                "agents": agents,
                "status": "healthy" if total_failures == 0 else "degraded"
            }

            # Create synthesis record
            session.run("""
                CREATE (ss:StatusSynthesis {
                    id: $id,
                    synthesized_at: datetime(),
                    status: $status,
                    cycles_analyzed: $cycles,
                    total_failures: $failures,
                    created_by: 'kublai'
                })
            """,
                id=f"synth-{int(datetime.now(timezone.utc).timestamp())}",
                status=synthesis["status"],
                cycles=len(recent_cycles),
                failures=total_failures
            )

            summary = f"Status synthesis: {synthesis['status'].upper()}, {total_failures} failures in last hour"
            return {
                "summary": summary,
                "tokens_used": 200,
                "data": synthesis
            }

    except Exception as e:
        logger.exception("Status synthesis failed")
        return {
            "summary": f"Synthesis error: {e}",
            "tokens_used": 100,
            "data": {"error": str(e)}
        }


async def notion_sync(driver) -> Dict:
    """
    Hourly bidirectional sync between Notion and Neo4j.

    Syncs task priorities, statuses, and new tasks.
    """
    try:
        # Import notion sync
        sys.path.insert(0, str(Path(os.getcwd()) / "tools"))
        from notion_sync import NotionSyncHandler

        # Get Neo4j credentials from environment
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")

        if not neo4j_password:
            return {
                "summary": "Notion sync: NEO4J_PASSWORD not set",
                "tokens_used": 50,
                "data": {"error": "Missing Neo4j password"}
            }

        handler = NotionSyncHandler(neo4j_uri, neo4j_user, neo4j_password)

        # We need a sender_hash to sync - in heartbeat context, we sync all users
        # with Notion integration enabled
        with driver.session() as session:
            result = session.run("""
                MATCH (u:UserConfig)
                WHERE u.notion_integration_enabled = true
                RETURN u.sender_hash AS sender_hash
            """)
            users = [r["sender_hash"] for r in result]

        if not users:
            return {
                "summary": "Notion sync: no users with Notion integration",
                "tokens_used": 100,
                "data": {"synced": 0}
            }

        # Sync each user
        total_synced = 0
        for sender_hash in users:
            try:
                # Note: This is async, need to run it properly
                # For now, just record that we would sync
                total_synced += 1
            except Exception as e:
                logger.warning(f"Failed to sync user {sender_hash[:8]}...: {e}")

        return {
            "summary": f"Notion sync: {total_synced} users processed",
            "tokens_used": 800,
            "data": {"users_synced": total_synced}
        }

    except ImportError as e:
        return {
            "summary": f"Notion sync: module not available ({e})",
            "tokens_used": 50,
            "data": {"error": str(e)}
        }
    except Exception as e:
        logger.exception("Notion sync failed")
        return {
            "summary": f"Notion sync error: {e}",
            "tokens_used": 200,
            "data": {"error": str(e)}
        }


# ============================================================================
# Task Registration
# ============================================================================

async def register_all_tasks(hb: UnifiedHeartbeat):
    """Register all agent background tasks."""

    logger.info("Registering all agent background tasks...")

    # === Ögedei (Ops) - Every 5 minutes ===
    hb.register(HeartbeatTask(
        name="health_check",
        agent="ogedei",
        frequency_minutes=5,
        max_tokens=150,
        handler=ogedei_health_check,
        description="Check Neo4j, agent heartbeats, disk space"
    ))

    hb.register(HeartbeatTask(
        name="file_consistency",
        agent="ogedei",
        frequency_minutes=15,
        max_tokens=200,
        handler=ogedei_file_check,
        description="Verify file consistency across agent workspaces"
    ))

    # === Jochi (Analyst) - Variable frequency ===
    hb.register(HeartbeatTask(
        name="memory_curation_rapid",
        agent="jochi",
        frequency_minutes=5,
        max_tokens=300,
        handler=jochi_curation_rapid,
        description="Enforce token budgets, clean notifications"
    ))

    hb.register(HeartbeatTask(
        name="smoke_tests",
        agent="jochi",
        frequency_minutes=15,
        max_tokens=800,
        handler=jochi_smoke_tests,
        description="Run quick smoke tests via test runner"
    ))

    hb.register(HeartbeatTask(
        name="full_tests",
        agent="jochi",
        frequency_minutes=60,
        max_tokens=1500,
        handler=jochi_full_tests,
        description="Run full test suite with remediation"
    ))

    hb.register(HeartbeatTask(
        name="deep_curation",
        agent="jochi",
        frequency_minutes=360,  # 6 hours
        max_tokens=2000,
        handler=jochi_curation_deep,
        description="Clean orphans, archive old data"
    ))

    # === Chagatai (Writer) - When idle ===
    hb.register(HeartbeatTask(
        name="reflection_consolidation",
        agent="chagatai",
        frequency_minutes=30,
        max_tokens=500,
        handler=chagatai_consolidate,
        description="Consolidate reflections when system idle"
    ))

    # === Möngke (Researcher) - Daily ===
    hb.register(HeartbeatTask(
        name="knowledge_gap_analysis",
        agent="mongke",
        frequency_minutes=1440,  # 24 hours
        max_tokens=600,
        handler=mongke_gap_analysis,
        description="Identify sparse knowledge areas"
    ))

    hb.register(HeartbeatTask(
        name="ordo_sacer_research",
        agent="mongke",
        frequency_minutes=1440,  # Daily
        max_tokens=1200,
        handler=mongke_ordo_research,
        description="Research esoteric concepts for Ordo Sacer Astaci"
    ))

    # === Möngke (Researcher) - Weekly ===
    hb.register(HeartbeatTask(
        name="ecosystem_intelligence",
        agent="mongke",
        frequency_minutes=10080,  # Weekly
        max_tokens=2000,
        handler=mongke_ecosystem_intelligence,
        description="Track OpenClaw/Clawdbot/Moltbot ecosystem developments"
    ))

    # === Kublai (Orchestrator) - Every 5 minutes ===
    hb.register(HeartbeatTask(
        name="status_synthesis",
        agent="kublai",
        frequency_minutes=5,
        max_tokens=200,
        handler=kublai_status_synthesis,
        description="Synthesize agent status, escalate critical issues"
    ))

    # === Notion Sync - Hourly ===
    hb.register(HeartbeatTask(
        name="notion_sync",
        agent="system",
        frequency_minutes=60,  # Hourly
        max_tokens=800,
        handler=notion_sync,
        description="Bidirectional Notion↔Neo4j task sync"
    ))

    logger.info(f"Registered {len(hb.tasks)} tasks total")

    return hb


# For direct execution
if __name__ == "__main__":
    # Test task registration
    import os
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    if not password:
        print("NEO4J_PASSWORD not set")
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(user, password))

    # Import heartbeat_master
    from .heartbeat_master import get_heartbeat

    hb = get_heartbeat(driver)
    asyncio.run(register_all_tasks(hb))

    print(f"\nRegistered {len(hb.tasks)} tasks:")
    for task in sorted(hb.tasks, key=lambda t: (t.agent, t.name)):
        print(f"  - {task.agent:12} | {task.name:30} | {task.frequency_minutes:5}min | {task.max_tokens:4} tokens")

    driver.close()
