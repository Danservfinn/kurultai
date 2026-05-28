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

def sanitize_string(value):
    if value is None:
        return None
    text = str(value)
    home = str(Path.home())
    text = text.replace(home + "/brain", "${BRAIN_ROOT}")
    text = text.replace(home, "${KURULTAI_HOME}")
    text = text.replace("Da" + "nny", "the operator").replace("da" + "nny", "operator").replace("Da" + "niel", "the operator")
    if text in ("local", "origin"):
        return text
    for prefix in ("telegram:", "discord:", "slack:", "sms:", "signal:"):
        if text.startswith(prefix):
            return prefix + "[REDACTED]"
    return text

manifest = []
for index, job in enumerate(load_jobs(), start=1):
    manifest.append({
        "job_id": f"job-{index:03d}",
        "name": sanitize_string(job.get("name")),
        "schedule": job.get("schedule"),
        "repeat": job.get("repeat"),
        "deliver": sanitize_string(job.get("deliver")),
        "enabled": job.get("enabled"),
        "state": job.get("state"),
        "skills": job.get("skills") or ([job.get("skill")] if job.get("skill") else []),
        "enabled_toolsets": job.get("enabled_toolsets"),
        "script": sanitize_string(job.get("script")),
        "workdir": sanitize_string(job.get("workdir")),
    })

out.write_text(json.dumps({"schema": "kurultai.cron-manifest.v1", "jobs": manifest}, indent=2, sort_keys=True) + "\n")
print(out)
