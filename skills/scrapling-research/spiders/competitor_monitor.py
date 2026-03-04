#!/usr/bin/env python3
"""
Competitor Monitor Spider

Monitors competitor pricing, features, and job postings.
Used by Temujin for Parse competitive intelligence.
"""

from scrapling.spiders import Spider, Response
from datetime import datetime
import json


class CompetitorMonitorSpider(Spider):
    """Monitor competitor websites for changes."""
    
    name = "competitor_monitor"
    concurrent_requests = 5
    
    # Configure based on target
    start_urls = [
        "https://www.back4app.com/pricing",
        "https://www.parseplatform.org/",
    ]
    
    def __init__(self, crawldir: str = None, output_file: str = None, **kwargs):
        super().__init__(**kwargs)
        self.crawldir = crawldir
        self.output_file = output_file or f"competitor_data_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        self.results = []
    
    async def parse(self, response: Response):
        """Extract pricing and feature data."""
        
        data = {
            "url": response.url,
            "timestamp": datetime.now().isoformat(),
            "title": response.css("title::text").get(),
            "prices": [],
            "features": [],
            "jobs": [],
        }
        
        # Extract pricing (adapt selectors per site)
        prices = response.css('.price, .pricing, [class*="price"]::text').getall()
        data["prices"] = [p.strip() for p in prices if p.strip()][:10]
        
        # Extract features
        features = response.css('.feature, [class*="feature"]::text').getall()
        data["features"] = [f.strip() for f in features if f.strip()][:20]
        
        # Extract job postings (if careers page)
        jobs = response.css('a[href*="careers"], a[href*="jobs"]::text').getall()
        data["jobs"] = [j.strip() for j in jobs if j.strip()][:10]
        
        self.results.append(data)
        
        yield data
    
    def closed(self, reason):
        """Save results when spider closes."""
        if self.results:
            with open(self.output_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"Saved {len(self.results)} results to {self.output_file}")


if __name__ == "__main__":
    # Test run
    spider = CompetitorMonitorSpider()
    result = spider.start()
    print(f"Scraped {len(result.items)} items")
