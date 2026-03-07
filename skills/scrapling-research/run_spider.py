#!/usr/bin/env python3
"""
Spider runner for cron jobs.
Usage: python3 run_spider.py <spider_name> <output_file> [max_items]

Spiders: competitor_monitor, openclaw_discovery, news_gatherer
"""
import sys
import json
import os

SPIDER_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SPIDER_DIR, "spiders"))

SPIDERS = {
    "competitor_monitor": ("competitor_monitor", "CompetitorMonitorSpider", {}),
    "openclaw_discovery": ("openclaw_discovery", "OpenClawDiscoverySpider", {"max_results": 30}),
    "news_gatherer": ("news_gatherer", "NewsGathererSpider", {"max_articles": 30}),
}

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <spider_name> <output_file> [max_items]")
        print(f"Spiders: {', '.join(SPIDERS.keys())}")
        sys.exit(1)

    spider_name = sys.argv[1]
    output_file = sys.argv[2]
    max_items = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if spider_name not in SPIDERS:
        print(f"Unknown spider: {spider_name}")
        sys.exit(1)

    module_name, class_name, defaults = SPIDERS[spider_name]
    module = __import__(module_name)
    SpiderClass = getattr(module, class_name)

    kwargs = {**defaults}
    if max_items is not None:
        if "max_results" in defaults:
            kwargs["max_results"] = max_items
        elif "max_articles" in defaults:
            kwargs["max_articles"] = max_items

    spider = SpiderClass(output_file=output_file, **kwargs)
    result = spider.start()

    items = [dict(item) if hasattr(item, '__iter__') else item for item in result.items]
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(items, f, indent=2, default=str)

    print(f"OK: {spider_name} scraped {len(items)} items -> {output_file}")

if __name__ == "__main__":
    main()
