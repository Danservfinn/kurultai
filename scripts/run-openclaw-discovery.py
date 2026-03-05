#!/usr/bin/env python3
"""
Run OpenClaw Discovery Task

Finds new tools, skills, and integrations for OpenClaw.
Execute from: ~/.openclaw/agents/main/scripts/
"""

import sys
import os
from datetime import datetime

# Add skills directory to path
SKILLS_DIR = os.path.expanduser("~/.openclaw/agents/main/skills/scrapling-research")
sys.path.insert(0, SKILLS_DIR)

# Import spider
from spiders.openclaw_discovery import OpenClawDiscoverySpider

# Output directory
OUTPUT_DIR = os.path.expanduser("~/.openclaw/agents/main/agents/mongke/data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Run discovery
timestamp = datetime.now().strftime('%Y%m%d_%H%M')
output_file = os.path.join(OUTPUT_DIR, f"openclaw_discovery_{timestamp}.json")

print(f"Starting OpenClaw discovery at {datetime.now().isoformat()}")
print(f"Output: {output_file}")
print(f"Searching: GitHub, NPM, PyPI, ClawHub, Dev.to, Medium...")

spider = OpenClawDiscoverySpider(max_results=50, output_file=output_file)
result = spider.start()

print(f"\n✅ Discovery complete!")
print(f"   Resources found: {len(result.items)}")
print(f"   Output file: {output_file}")

# Show summary
if result.items:
    categories = {}
    for item in result.items:
        cat = item.get('category', 'unknown')
        categories[cat] = categories.get(cat, 0) + 1
    
    print(f"\n   By category:")
    for cat, count in sorted(categories.items()):
        print(f"     - {cat}: {count}")
