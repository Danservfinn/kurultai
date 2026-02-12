#!/usr/bin/env python3
"""
Test script for x-research skill.

Usage:
    python test_skill.py              # Run all tests
    python test_skill.py --mock       # Run with mock data
    python test_skill.py --live       # Run with live API (requires key)
"""

import sys
import os
import argparse

# Add workspace to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from skills.x_research import XResearchClient, test_skill


def run_mock_tests():
    """Run tests with mock data."""
    print("🧪 Running x-research tests with mock data...\n")
    
    client = XResearchClient(api_key=None)  # Force mock mode
    
    # Test search
    print("Testing search_tweets...")
    tweets = client.search_tweets("#AI", max_results=5)
    print(f"  Found {len(tweets)} tweets")
    for t in tweets[:2]:
        print(f"  - @{t.author_username}: {t.text[:50]}...")
    
    # Test timeline
    print("\nTesting get_user_timeline...")
    timeline = client.get_user_timeline("testuser", max_results=3)
    print(f"  Found {len(timeline)} tweets")
    
    # Test trends
    print("\nTesting get_trending_topics...")
    trends = client.get_trending_topics()
    print(f"  Found {len(trends)} trends")
    for t in trends[:3]:
        print(f"  - {t.name} ({t.tweet_volume or 'N/A'} tweets)")
    
    # Test analysis
    print("\nTesting analyze_engagement...")
    analysis = client.analyze_engagement(tweets)
    print(f"  Total engagement: {analysis['total_engagement']}")
    print(f"  Average: {analysis['average_engagement']}")
    
    # Test insights
    print("\nTesting extract_insights...")
    insights = client.extract_insights(tweets)
    print(f"  Total tweets: {insights['total_tweets']}")
    print(f"  Top hashtags: {insights['top_hashtags'][:3]}")
    
    # Test report
    print("\nTesting generate_report...")
    report = client.generate_report(insights, "Test Report")
    print(f"  Report length: {len(report)} characters")
    print("\n--- Report Preview ---")
    print(report[:500])
    print("...")
    
    print("\n✅ All mock tests passed!")
    return True


def run_live_tests():
    """Run tests with live API (requires API key)."""
    api_key = os.environ.get("COMPOSIO_API_KEY")
    
    if not api_key:
        print("❌ COMPOSIO_API_KEY not set. Cannot run live tests.")
        print("   Set it with: export COMPOSIO_API_KEY=your_key_here")
        return False
    
    print("🌐 Running x-research tests with live API...\n")
    
    client = XResearchClient(api_key=api_key)
    
    try:
        # Test search
        print("Testing live search...")
        tweets = client.search_tweets("OpenAI", max_results=10)
        print(f"  Found {len(tweets)} tweets")
        
        if tweets:
            print("\nSample tweets:")
            for t in tweets[:3]:
                print(f"  - {t.text[:60]}...")
        
        print("\n✅ Live tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Live test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test x-research skill")
    parser.add_argument("--mock", action="store_true", help="Run with mock data")
    parser.add_argument("--live", action="store_true", help="Run with live API")
    
    args = parser.parse_args()
    
    if args.live:
        success = run_live_tests()
    else:
        success = run_mock_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
