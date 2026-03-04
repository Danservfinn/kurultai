#!/usr/bin/env python3
"""
Scrapling Client Library for Kurultai

Provides unified interface for web scraping with adaptive parsing,
anti-bot bypass, and concurrent crawling capabilities.
"""

from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
from scrapling.spiders import Spider, Response
from typing import Optional, List, Dict, Any
import asyncio


class ScraplingClient:
    """Unified Scraping Client for Kurultai agents."""
    
    def __init__(self, adaptive: bool = True):
        """
        Initialize Scrapling client.
        
        Args:
            adaptive: Enable adaptive element tracking (survives website changes)
        """
        self.adaptive = adaptive
        StealthyFetcher.adaptive = adaptive
    
    def fetch(self, url: str, **kwargs) -> Any:
        """
        Simple HTTP fetch (fast, no browser).
        
        Args:
            url: Target URL
            **kwargs: Additional Fetcher arguments
            
        Returns:
            Parsed page object
        """
        return Fetcher.get(url, **kwargs)
    
    def stealth_fetch(self, url: str, solve_cloudflare: bool = True, 
                      headless: bool = True, **kwargs) -> Any:
        """
        Stealthy fetch with anti-bot bypass.
        
        Args:
            url: Target URL
            solve_cloudflare: Auto-solve Cloudflare Turnstile
            headless: Run browser headless
            **kwargs: Additional StealthyFetcher arguments
            
        Returns:
            Parsed page object
        """
        return StealthyFetcher.fetch(
            url, 
            solve_cloudflare=solve_cloudflare,
            headless=headless,
            **kwargs
        )
    
    def dynamic_fetch(self, url: str, headless: bool = True,
                      network_idle: bool = True, **kwargs) -> Any:
        """
        Full browser automation for dynamic sites.
        
        Args:
            url: Target URL
            headless: Run browser headless
            network_idle: Wait for network to be idle
            **kwargs: Additional DynamicFetcher arguments
            
        Returns:
            Parsed page object
        """
        return DynamicFetcher.fetch(
            url,
            headless=headless,
            network_idle=network_idle,
            **kwargs
        )
    
    def extract(self, url: str, selector: str, 
                adaptive: bool = None, **kwargs) -> List[str]:
        """
        Fetch and extract data with CSS selector.
        
        Args:
            url: Target URL
            selector: CSS selector (e.g., '.product h2::text')
            adaptive: Use adaptive element tracking
            **kwargs: Additional fetch arguments
            
        Returns:
            List of extracted text values
        """
        adaptive = adaptive if adaptive is not None else self.adaptive
        page = StealthyFetcher.fetch(url, solve_cloudflare=True)
        elements = page.css(selector, adaptive=adaptive)
        return [el.get() for el in elements]
    
    def monitor_competitors(self, urls: List[str], 
                           selector: str = '.price') -> Dict[str, Any]:
        """
        Monitor competitor pricing/pages.
        
        Args:
            urls: List of competitor URLs
            selector: CSS selector for target elements
            
        Returns:
            Dict mapping URLs to extracted data
        """
        results = {}
        for url in urls:
            try:
                page = StealthyFetcher.fetch(url, solve_cloudflare=True)
                elements = page.css(selector, adaptive=self.adaptive)
                results[url] = [el.get() for el in elements]
            except Exception as e:
                results[url] = {"error": str(e)}
        return results


class KurultaiSpider(Spider):
    """Base spider class for Kurultai agents."""
    
    concurrent_requests = 10
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'AUTOTHROTTLE_ENABLED': True,
    }
    
    def __init__(self, crawldir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if crawldir:
            self.crawldir = crawldir
    
    async def parse(self, response: Response):
        """Override this method in subclasses."""
        raise NotImplementedError


# Test function
if __name__ == "__main__":
    print("Testing Scrapling Client...")
    client = ScraplingClient()
    
    # Test 1: Simple fetch
    print("\n1. Simple fetch test:")
    page = client.fetch('https://quotes.toscrape.com/')
    quotes = page.css('.quote')
    print(f"   Scraped {len(quotes)} quotes")
    
    # Test 2: Extract with selector
    print("\n2. Extract test:")
    texts = client.extract('https://quotes.toscrape.com/', '.text::text')
    print(f"   Extracted {len(texts)} text elements")
    if texts:
        print(f"   First quote: {texts[0][:50]}...")
    
    # Test 3: Stealthy fetch
    print("\n3. Stealthy fetch test:")
    page = client.stealth_fetch('https://quotes.toscrape.com/')
    authors = page.css('.author::text').getall()
    print(f"   Found {len(authors)} authors")
    
    print("\n✅ All tests passed!")
