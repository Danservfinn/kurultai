#!/usr/bin/env python3
"""
Run News Gathering Task

Execute from: ~/.openclaw/agents/main/scripts/
"""

import sys
import os
from datetime import datetime

# Add skills directory to path
SKILLS_DIR = os.path.expanduser("~/.openclaw/agents/main/skills/scrapling-research")
sys.path.insert(0, SKILLS_DIR)

# Import spider
from spiders.news_gatherer import NewsGathererSpider

# Output directory
OUTPUT_DIR = os.path.expanduser("~/.openclaw/agents/main/agents/mongke/data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Run gathering
timestamp = datetime.now().strftime('%Y%m%d_%H%M')
output_file = os.path.join(OUTPUT_DIR, f"news_feed_{timestamp}.json")

print(f"Starting news gather at {datetime.now().isoformat()}")
print(f"Output: {output_file}")

spider = NewsGathererSpider(max_articles=20, output_file=output_file)
result = spider.start()

print(f"\n✅ News gather complete!")
print(f"   Articles collected: {len(result.items)}")
print(f"   Output file: {output_file}")
