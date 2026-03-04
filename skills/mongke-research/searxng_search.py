#!/usr/bin/env python3
"""
SearXNG Search Module for Mongke Research Skill

Provides web search capabilities via SearXNG (self-hosted or public instances).

Usage:
    from searxng_search import SearXNGSearch
    search = SearXNGSearch()
    results = search.search("your query")
"""

import requests
import random
from typing import List, Dict, Optional


class SearXNGSearch:
    """SearXNG search client with fallback to public instances."""
    
    # Public SearXNG instances (fallback if local not available)
    # Note: Many public instances block automated requests
    PUBLIC_INSTANCES = [
        "https://search.sapti.me",
        "https://searx.priv.pw",
        "https://searxng.nicfab.eu",
    ]
    
    # Alternative: Jina AI Reader API (free tier available)
    JINA_SEARCH_URL = "https://s.jina.ai/{query}"
    
    def __init__(self, base_url: str = "http://localhost:8080", use_public: bool = False):
        """
        Initialize SearXNG search client.
        
        Args:
            base_url: Local SearXNG instance URL
            use_public: If True, use public instances instead of local
        """
        self.base_url = base_url.rstrip('/')
        self.use_public = use_public
        self.current_instance = base_url if not use_public else random.choice(self.PUBLIC_INSTANCES)
    
    def search(self, query: str, categories: List[str] = None, limit: int = 10) -> List[Dict]:
        """
        Search using SearXNG API.
        
        Args:
            query: Search query
            categories: List of categories (general, news, social, etc.)
            limit: Max results to return
        
        Returns:
            List of search results with title, url, content, engine
        """
        params = {
            'q': query,
            'format': 'json',
            'pageno': 1,
        }
        
        if categories:
            params['categories'] = ','.join(categories)
        
        # Try local instance first (if not using public)
        if not self.use_public:
            try:
                results = self._make_request(params)
                if results:
                    return results[:limit]
            except Exception as e:
                print(f"  Local SearXNG unavailable, falling back to public instance: {e}")
                self.use_public = True
                self.current_instance = random.choice(self.PUBLIC_INSTANCES)
        
        # Try public instances
        if self.use_public:
            for instance in self.PUBLIC_INSTANCES:
                self.current_instance = instance
                try:
                    results = self._make_request(params, instance)
                    if results:
                        print(f"  ✓ Using public instance: {instance}")
                        return results[:limit]
                except Exception as e:
                    continue
        
        # Fallback to Jina AI search
        print("  Trying Jina AI search as fallback...")
        jina_results = self.search_jina(query, limit)
        if jina_results:
            print(f"  ✓ Jina search found {len(jina_results)} results")
            return jina_results
        
        return []
    
    def _make_request(self, params: Dict, instance: str = None) -> List[Dict]:
        """Make API request to SearXNG instance."""
        url = instance or self.base_url
        endpoint = f"{url}/search"
        
        resp = requests.get(endpoint, params=params, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        results = data.get('results', [])
        
        # Normalize results
        normalized = []
        for r in results:
            normalized.append({
                'title': r.get('title', ''),
                'url': r.get('url', ''),
                'content': r.get('content', ''),
                'engine': r.get('engine', 'unknown'),
                'category': r.get('category', 'general'),
                'score': r.get('score', 0),
            })
        
        return normalized
    
    def search_news(self, query: str, limit: int = 10) -> List[Dict]:
        """Search news articles."""
        return self.search(query, categories=['news'], limit=limit)
    
    def search_social(self, query: str, limit: int = 10) -> List[Dict]:
        """Search social media."""
        return self.search(query, categories=['social_media'], limit=limit)
    
    def search_it(self, query: str, limit: int = 10) -> List[Dict]:
        """Search IT/technical content."""
        return self.search(query, categories=['it'], limit=limit)
    
    def test_instance(self, url: str = None) -> bool:
        """Test if a SearXNG instance is accessible."""
        test_url = url or self.base_url
        try:
            resp = requests.get(f"{test_url}/healthz", timeout=10)
            return resp.status_code == 200
        except:
            return False
    
    def get_engines(self) -> List[Dict]:
        """Get list of enabled search engines."""
        try:
            resp = requests.get(f"{self.current_instance}/engines", timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return []
    
    def search_jina(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Alternative search using Jina AI Reader API.
        
        Jina AI provides a free search API that returns LLM-ready results.
        https://jina.ai/reader
        
        Args:
            query: Search query
            limit: Max results
        
        Returns:
            List of search results
        """
        url = self.JINA_SEARCH_URL.format(query=query.replace(' ', '+'))
        
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get('data', [])[:limit]:
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'content': item.get('description', ''),
                        'engine': 'jina',
                        'category': 'general',
                        'score': 1.0,
                    })
                return results
        except Exception as e:
            print(f"  Jina search error: {e}")
        
        return []


def test_search():
    """Test SearXNG search functionality."""
    search = SearXNGSearch()
    
    print("Testing SearXNG search...")
    results = search.search("OpenClaw AI agent framework", limit=5)
    
    if results:
        print(f"✓ Found {len(results)} results")
        for i, r in enumerate(results[:3], 1):
            print(f"\n{i}. {r['title'][:60]}...")
            print(f"   URL: {r['url'][:60]}...")
            print(f"   Engine: {r['engine']}")
    else:
        print("✗ No results found")
    
    return len(results) > 0


if __name__ == "__main__":
    test_search()
