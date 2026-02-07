#!/usr/bin/env python3
"""
Test script for Parse API Client

Usage:
    python tools/test_parse_client.py
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.parse_api_client import (
    ParseClient,
    ParseAPIError,
    quick_score,
    analyze_article,
    rewrite_article,
    CredibilityLevel
)


async def test_quick_score():
    """Test quick scoring endpoint."""
    print("\n=== Test: Quick Score ===")

    try:
        result = await quick_score(
            "https://www.bbc.com/news/world-us-canada-68395288",
            api_key=os.getenv("PARSE_API_KEY")
        )
        print(f"✅ Quick Score: {result['score']}/100")
        print(f"   Title: {result.get('title', 'N/A')[:60]}...")
        return True
    except ParseAPIError as e:
        print(f"❌ ParseAPIError: {e.code} - {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_full_analysis():
    """Test full analysis endpoint."""
    print("\n=== Test: Full Analysis ===")

    try:
        async with ParseClient(api_key=os.getenv("PARSE_API_KEY")) as client:
            # Submit and wait for analysis
            print("Submitting article for analysis...")
            result = await client.full_analysis(
                "https://www.bbc.com/news/world-us-canada-68395288",
                agent="test_agent"
            )

            score = result.get("credibilityScore", result.get("score", 0))
            level = client.get_credibility_level(score)
            print(f"✅ Full Analysis Complete")
            print(f"   Score: {score}/100 ({level.value})")
            print(f"   Status: {result.get('status', 'unknown')}")
            return True
    except ParseAPIError as e:
        print(f"❌ ParseAPIError: {e.code} - {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_rewrite():
    """Test article rewrite endpoint."""
    print("\n=== Test: Article Rewrite ===")

    try:
        result = await rewrite_article(
            "https://www.bbc.com/news/world-us-canada-68395288",
            api_key=os.getenv("PARSE_API_KEY")
        )
        print(f"✅ Rewrite Complete")
        print(f"   Original: {result.get('originalTitle', 'N/A')[:60]}...")
        print(f"   Rewritten: {result.get('rewrittenTitle', 'N/A')[:60]}...")
        return True
    except ParseAPIError as e:
        print(f"❌ ParseAPIError: {e.code} - {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_usage_stats():
    """Test usage statistics."""
    print("\n=== Test: Usage Stats ===")

    try:
        stats = ParseClient.get_usage_stats()
        print(f"✅ Usage Stats:")
        print(f"   Daily Credits Used: {stats.daily_credits_used}/{stats.daily_limit}")
        print(f"   Total Credits Used: {stats.total_credits_used}")
        print(f"   Requests by Endpoint: {stats.requests_by_endpoint}")
        print(f"   Costs by Agent: {stats.costs_by_agent}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def main():
    """Run all tests."""
    if not os.getenv("PARSE_API_KEY"):
        print("❌ PARSE_API_KEY environment variable not set")
        print("\nSet it with:")
        print("  export PARSE_API_KEY='parse_pk_prod_...'")
        return

    print("=" * 60)
    print("Parse API Client Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(await test_quick_score())
    # Uncomment to test full analysis (costs 3 credits)
    # results.append(await test_full_analysis())
    # Uncomment to test rewrite (costs 1 credit)
    # results.append(await test_rewrite())
    results.append(await test_usage_stats())

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
