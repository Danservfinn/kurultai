#!/usr/bin/env python3
"""
Apply Standard Agent Configuration

Applies a standardized configuration to all agent .claude/settings.json files.
This ensures all agents use claude-opus-4-6 via the Anthropic API.

⚠️ DO NOT USE DashScope proxy or glm-5 model - they cause fleet-wide failures.

Usage:
    python3 apply-agent-backup-config.py [--dry-run]
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai", "tolui"]

BACKUP_CONFIG = {
    "permissions": {
        "defaultMode": "default"
    },
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "d6ff69bb5ad74bb29b297d1681cc648c.KtP5x1d8kkFXgM21",
        "ANTHROPIC_MODEL": "claude-opus-4-6",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-6",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6"
    },
    "enabledPlugins": {
        "claude-mem@thedotmack": True,
        "hookify@claude-plugins-official": True,
        "ralph-loop@claude-plugins-official": True,
        "feature-dev@claude-plugins-official": True,
        "playwright@claude-plugins-official": True,
        "supabase@claude-plugins-official": True,
        "vercel@claude-plugins-official": True,
        "code-simplifier@claude-plugins-official": True,
        "chrome-devtools-mcp@chrome-devtools-plugins": True,
        "agent-orchestration@claude-plugins-official": True,
        "beads@beads-marketplace": True,
        "backend-development@claude-code-workflows": True,
        "frontend-mobile-development@claude-code-workflows": True,
        "payment-processing@claude-code-workflows": True,
        "python-development@claude-code-workflows": True,
        "ralph-wiggum@claude-code-plugins": True,
        "frontend-design@claude-plugins-official": True,
        "agent-sdk-dev@claude-plugins-official": True,
        "code-review@claude-plugins-official": True,
        "database-migrations@claude-code-workflows": True,
        "stripe@claude-plugins-official": True,
        "commit-commands@claude-code-plugins": True,
        "superpowers@superpowers-marketplace": True,
        "code-documentation@claude-code-workflows": True
    },
    "alwaysThinkingEnabled": True,
    "skipDangerousModePermissionPrompt": True,
    "effortLevel": "high",
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Skill",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 /Users/kublai/.openclaw/agents/main/scripts/skill_tracker_hook.py",
                        "timeout": 5
                    }
                ]
            }
        ]
    }
}

def apply_config(agent, dry_run=False):
    """Apply backup config to an agent's settings.json"""
    settings_path = AGENTS_DIR / agent / ".claude" / "settings.json"
    backup_path = settings_path.with_suffix(".json.backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    
    if not settings_path.exists():
        print(f"  {agent}: SKIP - No settings.json found")
        return False
    
    if dry_run:
        print(f"  {agent}: DRY-RUN - Would backup to {backup_path.name} and apply new config")
        return True
    
    try:
        # Create backup
        shutil.copy2(settings_path, backup_path)
        print(f"  {agent}: Backed up to {backup_path.name}")
        
        # Apply new config
        with open(settings_path, 'w') as f:
            json.dump(BACKUP_CONFIG, f, indent=1)
        
        print(f"  {agent}: ✅ Applied Anthropic config (claude-opus-4-6)")
        return True
        
    except Exception as e:
        print(f"  {agent}: ERROR - {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Apply backup agent configuration')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    args = parser.parse_args()
    
    print(f"{'='*60}")
    print(f"BACKUP CONFIGURATION APPLICATOR")
    print(f"{'='*60}")
    print(f"\nTarget: All 6 Kurultai agents")
    print(f"Config: claude-opus-4-6 via Anthropic API (NOT DashScope)")
    print(f"{'='*60}\n")
    
    if args.dry_run:
        print("DRY-RUN MODE - No changes will be made\n")
    
    applied = 0
    for agent in AGENTS:
        if apply_config(agent, dry_run=args.dry_run):
            applied += 1
    
    print(f"\n{'='*60}")
    print(f"Complete: {applied}/{len(AGENTS)} agents {'would be' if args.dry_run else 'were'} updated")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
