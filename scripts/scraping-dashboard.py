#!/usr/bin/env python3
"""
Scraping Dashboard for Kurultai

Shows recent scrapes, competitor monitoring status, and news feed health.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta

# Paths
BASE_DIR = Path.home() / ".openclaw" / "agents" / "main"
JOCHI_DATA = BASE_DIR / "agents" / "jochi" / "data"
MONGKE_DATA = BASE_DIR / "agents" / "mongke" / "data"


def get_recent_files(directory: Path, pattern: str = "*.json", limit: int = 5) -> list:
    """Get recent JSON files from directory."""
    if not directory.exists():
        return []
    
    files = list(directory.glob(pattern))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files[:limit]


def load_json(filepath: Path) -> dict:
    """Load JSON file safely."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def format_size(size_bytes: int) -> str:
    """Format file size."""
    for unit in ['B', 'KB', 'MB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"


def competitor_dashboard():
    """Display competitor monitoring status."""
    print("\n" + "="*60)
    print("🎯 COMPETITOR INTELLIGENCE (Jochi)")
    print("="*60)
    
    files = get_recent_files(JOCHI_DATA, "competitor_scan_*.json")
    
    if not files:
        print("⚠️  No competitor scans found")
        print(f"   Expected location: {JOCHI_DATA}")
        return
    
    for i, filepath in enumerate(files, 1):
        data = load_json(filepath)
        age = datetime.now() - datetime.fromtimestamp(filepath.stat().st_mtime)
        
        print(f"\n{i}. {filepath.name}")
        print(f"   Age: {age.seconds // 60} minutes ago")
        print(f"   Size: {format_size(filepath.stat().st_size)}")
        
        if isinstance(data, list):
            print(f"   Sites scanned: {len(data)}")
            for site in data[:3]:
                url = site.get('url', 'Unknown')[:50]
                prices = site.get('prices', [])
                features = site.get('features', [])
                print(f"     - {url}")
                print(f"       Prices: {len(prices)} found")
                print(f"       Features: {len(features)} found")
        elif isinstance(data, dict) and 'error' in data:
            print(f"   ❌ Error: {data['error']}")


def news_dashboard():
    """Display news feed status."""
    print("\n" + "="*60)
    print("📰 NEWS FEED (Mongke)")
    print("="*60)
    
    files = get_recent_files(MONGKE_DATA, "news_feed_*.json")
    
    if not files:
        print("⚠️  No news feeds found")
        print(f"   Expected location: {MONGKE_DATA}")
        return
    
    for i, filepath in enumerate(files, 1):
        data = load_json(filepath)
        age = datetime.now() - datetime.fromtimestamp(filepath.stat().st_mtime)
        
        print(f"\n{i}. {filepath.name}")
        print(f"   Age: {age.seconds // 60} minutes ago")
        print(f"   Size: {format_size(filepath.stat().st_size)}")
        
        if isinstance(data, list):
            print(f"   Articles collected: {len(data)}")
            
            # Show sources breakdown
            sources = {}
            for article in data:
                source = article.get('source', 'Unknown')
                sources[source] = sources.get(source, 0) + 1
            
            print(f"   Sources: {len(sources)}")
            for source, count in list(sources.items())[:3]:
                domain = source.replace('https://', '').replace('http://', '').split('/')[0]
                print(f"     - {domain}: {count} articles")
            
            # Show recent headlines
            print(f"   Recent headlines:")
            for article in data[:3]:
                title = article.get('title', 'No title')[:60]
                print(f"     • {title}...")
        elif isinstance(data, dict) and 'error' in data:
            print(f"   ❌ Error: {data['error']}")


def health_check():
    """Check overall scraping health."""
    print("\n" + "="*60)
    print("🏥 SCRAPING HEALTH CHECK")
    print("="*60)
    
    # Check Scrapling installation
    try:
        import scrapling
        print(f"✅ Scrapling: v{scrapling.__version__}")
    except ImportError:
        print("❌ Scrapling: Not installed")
    
    # Check Playwright
    try:
        import playwright
        print(f"✅ Playwright: Installed")
    except ImportError:
        print("❌ Playwright: Not installed")
    
    # Check data directories
    print(f"\n📁 Data Directories:")
    for directory in [JOCHI_DATA, MONGKE_DATA]:
        exists = directory.exists()
        status = "✅" if exists else "❌"
        print(f"   {status} {directory.relative_to(BASE_DIR)}")
        
        if exists:
            files = list(directory.glob("*.json"))
            total_size = sum(f.stat().st_size for f in files)
            print(f"       Files: {len(files)}, Total: {format_size(total_size)}")


def main():
    """Main dashboard display."""
    print("\n" + "="*60)
    print("   KURULTAI SCRAPING DASHBOARD")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("="*60)
    
    health_check()
    competitor_dashboard()
    news_dashboard()
    
    print("\n" + "="*60)
    print("Dashboard complete.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
