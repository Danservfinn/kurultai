#!/usr/bin/env python3
"""
News Gatherer Spider

Collects news articles for LLM Survivor events and Kurultai research.
Used by Mongke for market intelligence and Chagatai for content sourcing.
"""

from scrapling.spiders import Spider, Response
from datetime import datetime
import json


class NewsGathererSpider(Spider):
    """Gather news articles from multiple sources."""
    
    name = "news_gatherer"
    concurrent_requests = 10
    
    start_urls = [
        "https://techcrunch.com/",
        "https://venturebeat.com/",
        "https://www.theverge.com/",
    ]
    
    def __init__(self, crawldir: str = None, output_file: str = None,
                 max_articles: int = 50, **kwargs):
        super().__init__(**kwargs)
        self.crawldir = crawldir
        self.output_file = output_file or f"news_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        self.results = []
        self.max_articles = max_articles
    
    async def parse(self, response: Response):
        """Extract article data."""
        
        # Generic article selectors (works on most news sites)
        articles = response.css('article, .article, [class*="article"]')
        
        for article in articles[:self.max_articles]:
            data = {
                "source": response.url,
                "timestamp": datetime.now().isoformat(),
                "title": article.css('h1::text, h2::text, h3::text, .title::text').get(),
                "url": article.css('a::attr(href)').get(),
                "author": article.css('.author, [class*="author"]::text').get(),
                "date": article.css('time::attr(datetime), .date::text').get(),
                "summary": article.css('.summary, .excerpt, p::text').get(),
            }
            
            # Only yield if we have at least a title
            if data["title"]:
                self.results.append(data)
                yield data
        
        # Follow pagination (next page)
        next_page = response.css('a.next, a[rel="next"], .pagination a:last-child::attr(href)').get()
        if next_page and len(self.results) < self.max_articles:
            yield response.follow(next_page, callback=self.parse)
    
    def closed(self, reason):
        """Save results when spider closes."""
        if self.results:
            with open(self.output_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"Saved {len(self.results)} articles to {self.output_file}")


if __name__ == "__main__":
    # Test run (limited)
    spider = NewsGathererSpider(max_articles=5)
    result = spider.start()
    print(f"Scraped {len(result.items)} articles")
