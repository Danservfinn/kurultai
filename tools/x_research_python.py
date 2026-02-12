#!/usr/bin/env python3
"""
X-Research via Composio API (Python implementation)
Alternative to the TypeScript/Bun version - works without Bun runtime
"""

import os
import sys
import json
import requests
from typing import Optional, List, Dict

class XResearchClient:
    """Python client for X/Twitter research via Composio API"""
    
    def __init__(self, api_key: Optional[str] = None, user_id: Optional[str] = None):
        self.api_key = api_key or os.environ.get('COMPOSIO_API_KEY')
        self.user_id = user_id or os.environ.get('COMPOSIO_USER_ID')
        self.base_url = "https://backend.composio.dev/api/v2"
        
        if not self.api_key:
            raise ValueError("COMPOSIO_API_KEY required")
    
    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request to Composio"""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "status": "failed"}
    
    def search_tweets(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search for tweets matching query"""
        print(f"🔍 Searching for: '{query}' (max {max_results} results)")
        
        # Use Composio's action execution
        data = {
            "app": "twitter",
            "action": "search_tweets",
            "params": {
                "query": query,
                "max_results": max_results
            }
        }
        
        result = self._request("POST", "/actions/execute", data)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return []
        
        tweets = result.get("data", [])
        print(f"✅ Found {len(tweets)} tweets")
        return tweets
    
    def get_user_timeline(self, username: str, max_results: int = 10) -> List[Dict]:
        """Get tweets from a specific user"""
        print(f"🔍 Getting timeline for @{username}")
        
        data = {
            "app": "twitter",
            "action": "get_user_tweets",
            "params": {
                "username": username,
                "max_results": max_results
            }
        }
        
        result = self._request("POST", "/actions/execute", data)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return []
        
        tweets = result.get("data", [])
        print(f"✅ Found {len(tweets)} tweets from @{username}")
        return tweets
    
    def test_connection(self) -> bool:
        """Test if Composio connection is working"""
        print("🧪 Testing Composio connection...")
        
        # Try to list connected apps
        result = self._request("GET", "/connected-apps")
        
        if "error" in result:
            print(f"❌ Connection failed: {result['error']}")
            return False
        
        apps = result.get("items", [])
        twitter_connected = any(
            app.get("appName", "").lower() in ["twitter", "x"]
            for app in apps
        )
        
        if twitter_connected:
            print("✅ Twitter/X connection verified!")
            return True
        else:
            print("⚠️  Twitter/X not found in connected apps")
            return False

def main():
    """CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='X-Research via Composio')
    parser.add_argument('command', choices=['search', 'timeline', 'test'])
    parser.add_argument('--query', '-q', help='Search query')
    parser.add_argument('--username', '-u', help='Twitter username')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Max results')
    
    args = parser.parse_args()
    
    try:
        client = XResearchClient()
        
        if args.command == 'test':
            success = client.test_connection()
            sys.exit(0 if success else 1)
            
        elif args.command == 'search':
            if not args.query:
                print("❌ --query required for search")
                sys.exit(1)
            tweets = client.search_tweets(args.query, args.limit)
            print(json.dumps(tweets, indent=2))
            
        elif args.command == 'timeline':
            if not args.username:
                print("❌ --username required for timeline")
                sys.exit(1)
            tweets = client.get_user_timeline(args.username, args.limit)
            print(json.dumps(tweets, indent=2))
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
