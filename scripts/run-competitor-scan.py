#!/usr/bin/env python3
"""
Run Competitor Intelligence Scan

Execute from: ~/.openclaw/agents/main/scripts/
"""

import sys
import os
from datetime import datetime

# Add skills directory to path
SKILLS_DIR = os.path.expanduser("~/.openclaw/agents/main/skills/scrapling-research")
sys.path.insert(0, SKILLS_DIR)

# Import spider
from spiders.competitor_monitor import CompetitorMonitorSpider

# Output directory
OUTPUT_DIR = os.path.expanduser("~/.openclaw/agents/main/agents/jochi/data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Run scan
timestamp = datetime.now().strftime('%Y%m%d_%H%M')
output_file = os.path.join(OUTPUT_DIR, f"competitor_scan_{timestamp}.json")

print(f"Starting competitor scan at {datetime.now().isoformat()}")
print(f"Output: {output_file}")

spider = CompetitorMonitorSpider(output_file=output_file)
result = spider.start()

print(f"\n✅ Scan complete!")
print(f"   Pages scraped: {len(result.items)}")
print(f"   Output file: {output_file}")
