#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = Path.home() / ".hermes" / "cron" / "jobs.json"
out = root / "config" / "runtime-config" / "cron.manifest.json"

def load_jobs():
    if not source.exists():
        return []
    data = json.loads(source.read_text())
    if isinstance(data, dict):
        return data.get("jobs", [])
    if isinstance(data, list):
        return data
    return []

def public_delivery(value):
    if value in (None, "local", "origin"):
        return value
    text = str(value)
    if text.startswith("telegram:"):
        return "telegram:[REDACTED]"
    if text.startswith("discord:"):
        return "discord:[REDACTED]"
    return "external:[REDACTED]"


manifest = []
for job in load_jobs():
    manifest.append({
        "job_id": job.get("job_id") or job.get("id"),
        "name": job.get("name"),
        "schedule": job.get("schedule"),
        "repeat": job.get("repeat"),
        "deliver": public_delivery(job.get("deliver")),
        "enabled": job.get("enabled"),
        "state": job.get("state"),
        "skills": job.get("skills") or ([job.get("skill")] if job.get("skill") else []),
        "enabled_toolsets": job.get("enabled_toolsets"),
        "script": job.get("script"),
        "workdir": job.get("workdir"),
    })

out.write_text(json.dumps({"schema": "kurultai.cron-manifest.v1", "jobs": manifest}, indent=2, sort_keys=True) + "\n")
print(out)
