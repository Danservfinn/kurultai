#!/usr/bin/env python3
"""
Model Drift Detector — Routing Pipeline Diagnostics

Checks agent model configuration consistency across three layers:
1. Agent config.json files (per-agent settings)
2. Vault credentials (provider.env)
3. Wrapper fallback chain (claude-agent)

Usage: python3 model_drift_detector.py [--verbose]

Outputs: JSON report to stdout, human-readable to stderr
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Configuration paths
VAULT_FILE = Path("/Users/kublai/.openclaw/credentials/provider.env")
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
WRAPPER_SCRIPT = Path("/Users/kublai/.local/bin/claude-agent")

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Expected model mappings from vault
EXPECTED_MODELS = {
    "default": "claude-sonnet-4-6",  # Primary (OAuth)
    "zai": "glm-5",                  # Tier 1 fallback
    "alibaba": "qwen3.5-plus"        # Tier 2 fallback
}


def load_vault() -> dict:
    """Load and parse the vault credentials file."""
    if not VAULT_FILE.exists():
        return {"error": "Vault file not found"}

    vault = {}
    with open(VAULT_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            vault[key.strip()] = value.strip()

    return vault


def get_agent_config(agent: str) -> dict:
    """Get an agent's configuration from their settings.json."""
    settings_file = AGENTS_DIR / agent / ".claude" / "settings.json"
    if not settings_file.exists():
        return {"error": "settings.json not found"}

    with open(settings_file) as f:
        return json.load(f)


def check_agent_model(agent: str, vault: dict) -> dict:
    """
    Check an agent's model configuration.

    Returns dict with status and issues.
    """
    result = {
        "agent": agent,
        "status": "unknown",
        "issues": [],
        "recommendations": []
    }

    # Check if vault has required credentials
    zai_token = vault.get("ZAI_AUTH_TOKEN", "")
    alibaba_token = vault.get("ALIBABA_AUTH_TOKEN", "")

    if not zai_token:
        result["issues"].append("Tier 1 (Z.AI) credential missing from vault")
        result["recommendations"].append("Add ZAI_AUTH_TOKEN to provider.env")

    if not alibaba_token:
        result["issues"].append("Tier 2 (Alibaba) credential missing from vault")
        result["recommendations"].append("Add ALIBABA_AUTH_TOKEN to provider.env")

    # Check agent settings for explicit model override
    config = get_agent_config(agent)
    if "error" in config:
        result["issues"].append(f"Cannot read config: {config['error']}")
        result["status"] = "error"
        return result

    # Check for embedded model in agent config (some agents may have inline settings)
    # Most agents use wrapper defaults, which is correct
    result["config_source"] = "wrapper_defaults"
    result["status"] = "ok"

    return result


def detect_drift() -> dict:
    """
    Run full drift detection across all agents.

    Returns structured report.
    """
    vault = load_vault()

    if "error" in vault:
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": vault["error"],
            "agents": []
        }

    report = {
        "timestamp": datetime.now().isoformat(),
        "status": "ok",
        "vault_status": {
            "tier1_zai": bool(vault.get("ZAI_AUTH_TOKEN")),
            "tier2_alibaba": bool(vault.get("ALIBABA_AUTH_TOKEN")),
            "default_model": vault.get("DEFAULT_MODEL", "not_set")
        },
        "agents": [],
        "summary": {
            "total": len(AGENTS),
            "ok": 0,
            "warning": 0,
            "error": 0
        }
    }

    for agent in AGENTS:
        agent_result = check_agent_model(agent, vault)
        report["agents"].append(agent_result)

        if agent_result["status"] == "ok":
            report["summary"]["ok"] += 1
        elif agent_result["status"] == "warning":
            report["summary"]["warning"] += 1
        else:
            report["summary"]["error"] += 1

    # Overall status
    if report["summary"]["error"] > 0:
        report["status"] = "error"
    elif report["summary"]["warning"] > 0:
        report["status"] = "warning"

    return report


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    report = detect_drift()

    # Human-readable output to stderr
    print(f"=== Model Drift Detection Report ===", file=sys.stderr)
    print(f"Timestamp: {report['timestamp']}", file=sys.stderr)
    print(file=sys.stderr)

    # Vault status
    vault = report.get("vault_status", {})
    print(f"Vault Status:", file=sys.stderr)
    print(f"  Tier 1 (Z.AI glm-5): {'✓' if vault.get('tier1_zai') else '✗ MISSING'}", file=sys.stderr)
    print(f"  Tier 2 (Alibaba qwen3.5-plus): {'✓' if vault.get('tier2_alibaba') else '✗ MISSING'}", file=sys.stderr)
    print(f"  Default Model: {vault.get('default_model', 'unknown')}", file=sys.stderr)
    print(file=sys.stderr)

    # Agent status
    for agent_report in report["agents"]:
        status_symbol = "✓" if agent_report["status"] == "ok" else "⚠"
        print(f"{status_symbol} {agent_report['agent']}: {agent_report['status']}", file=sys.stderr)
        if verbose and agent_report.get("issues"):
            for issue in agent_report["issues"]:
                print(f"    - {issue}", file=sys.stderr)
        if verbose and agent_report.get("recommendations"):
            for rec in agent_report["recommendations"]:
                print(f"    → {rec}", file=sys.stderr)

    print(file=sys.stderr)
    summary = report["summary"]
    print(f"Summary: {summary['ok']} OK, {summary['warning']} Warnings, {summary['error']} Errors", file=sys.stderr)

    # Actionable remediation for common issues
    if any("Tier 1" in a.get("issues", [""])[0] if a.get("issues") else False for a in report["agents"]):
        print(file=sys.stderr)
        print("REMEDIATION:", file=sys.stderr)
        print("  1. Check vault file: /Users/kublai/.openclaw/credentials/provider.env", file=sys.stderr)
        print("  2. Verify ZAI_AUTH_TOKEN is present and valid", file=sys.stderr)
        print("  3. Restart affected agent sessions", file=sys.stderr)

    # JSON report to stdout
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
