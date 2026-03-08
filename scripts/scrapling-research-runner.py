#!/usr/bin/env python3
"""
Scrapling Research Runner
Consolidates: competitor-monitor, openclaw-discovery, news-gatherer

Config-driven spider scheduler that runs spiders based on cron schedules.
Replaces 3 separate cron jobs with a single unified runner.

Usage:
    python3 scrapling-research-runner.py [--dry-run] [--force JOB]

Options:
    --dry-run    Show which jobs would run without executing
    --force JOB  Force a specific job to run (bypasses schedule check)
"""

import subprocess
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from croniter import croniter

# Paths
SCRIPT_DIR = Path(__file__).parent
RUN_SPIDER = SCRIPT_DIR.parent / "skills" / "scrapling-research" / "run_spider.py"

# Spider job configurations
RESEARCH_JOBS = [
    {
        "name": "competitor-monitor",
        "schedule": "0 */6 * * *",  # Every 6 hours (00:00, 06:00, 12:00, 18:00)
        "spider": "competitor_monitor",
        "output": "/Users/kublai/.openclaw/agents/jochi/data/competitor_scan_scrapling_latest.json"
    },
    {
        "name": "openclaw-discovery",
        "schedule": "0 6 * * *",  # Daily at 6 AM
        "spider": "openclaw_discovery",
        "output": "/Users/kublai/.openclaw/agents/mongke/data/openclaw_discovery_latest.json"
    },
    {
        "name": "news-gatherer",
        "schedule": "0 7 * * *",  # Daily at 7 AM
        "spider": "news_gatherer",
        "output": "/Users/kublai/.openclaw/agents/mongke/data/news_latest.json"
    },
]


def should_run_now(job, now=None):
    """Check if job should run based on schedule.

    Uses croniter to determine if the current time matches the scheduled time.
    Returns True if we're at the exact scheduled minute (within 1 minute window).
    """
    if now is None:
        now = datetime.now()

    cron = croniter(job["schedule"], now)

    # Get previous scheduled time
    prev_sched = cron.get_prev(datetime)

    # Get next scheduled time
    cron = croniter(job["schedule"], now)
    next_sched = cron.get_next(datetime)

    # Check if we're within 1 minute of the scheduled time
    # This handles cron being called at :00 or :01
    diff_to_prev = abs((now - prev_sched).total_seconds())
    diff_to_next = abs((next_sched - now).total_seconds())

    # We should run if we're within 59 seconds of a scheduled time
    return diff_to_prev < 59 or diff_to_next < 59


def run_spider(job, dry_run=False):
    """Execute a single spider job.

    Returns dict with job status, output, and error info.
    """
    if dry_run:
        return {
            "job": job["name"],
            "success": True,
            "dry_run": True,
            "output": f"Would run {job['spider']} -> {job['output']}",
            "error": None
        }

    cmd = [
        "python3",
        str(RUN_SPIDER),
        job["spider"],
        job["output"]
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    return {
        "job": job["name"],
        "spider": job["spider"],
        "success": result.returncode == 0,
        "output": result.stdout.strip(),
        "error": result.stderr.strip() if result.stderr else None,
        "returncode": result.returncode
    }


def main():
    parser = argparse.ArgumentParser(
        description="Unified Scrapling Research Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Normal run (respects schedules)
    python3 scrapling-research-runner.py

    # Show what would run without executing
    python3 scrapling-research-runner.py --dry-run

    # Force a specific job to run
    python3 scrapling-research-runner.py --force competitor-monitor

Available jobs: %s
""" % ", ".join(j["name"] for j in RESEARCH_JOBS)
    )
    parser.add_argument("--dry-run", action="store_true",
                       help="Show which jobs would run without executing")
    parser.add_argument("--force", metavar="JOB",
                       help="Force a specific job to run (bypasses schedule)")
    parser.add_argument("--list", action="store_true",
                       help="List all jobs and their schedules")

    args = parser.parse_args()

    if args.list:
        print("Scrapling Research Jobs:")
        print("-" * 60)
        for job in RESEARCH_JOBS:
            print(f"  {job['name']:20} {job['schedule']:15} -> {job['spider']}")
        return 0

    now = datetime.now()
    results = []
    jobs_to_run = []

    # Determine which jobs to run
    if args.force:
        # Find the requested job
        forced_job = None
        for job in RESEARCH_JOBS:
            if job["name"] == args.force:
                forced_job = job
                break
        if not forced_job:
            print(f"ERROR: Unknown job '{args.force}'", file=sys.stderr)
            print(f"Available jobs: {', '.join(j['name'] for j in RESEARCH_JOBS)}", file=sys.stderr)
            return 1
        jobs_to_run = [forced_job]
    else:
        # Check all jobs against schedule
        for job in RESEARCH_JOBS:
            if should_run_now(job, now):
                jobs_to_run.append(job)

    if not jobs_to_run:
        # Nothing to run (normal behavior most of the time)
        if not args.dry_run:
            # Silent exit when nothing scheduled (cron runs this every 30m)
            return 0
        print("No jobs scheduled for this time.")

    # Run the jobs
    all_success = True
    for job in jobs_to_run:
        result = run_spider(job, dry_run=args.dry_run)
        results.append(result)

        if args.dry_run:
            print(f"[DRY-RUN] {result['output']}")
        else:
            if result["success"]:
                print(f"OK: {result['job']}")
                if result.get("output"):
                    print(f"  {result['output']}")
            else:
                print(f"ERROR: {result['job']}: {result.get('error', 'Unknown error')}")
                all_success = False

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
