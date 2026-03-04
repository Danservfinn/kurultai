#!/usr/bin/env python3
"""
OpenClaw Discovery Spider

Finds new tools, skills, tips, and tricks for OpenClaw.
Used by Mongke for ecosystem research.
"""

from scrapling.spiders import Spider, Response
from datetime import datetime
import json
import re


class OpenClawDiscoverySpider(Spider):
    """Discover OpenClaw-related resources."""
    
    name = "openclaw_discovery"
    concurrent_requests = 5
    
    # Search queries to run
    search_queries = [
        "openclaw skill",
        "openclaw integration",
        "claude code skill",
        "claude code plugin",
        "openclaw tutorial",
    ]
    
    # Target sources
    start_urls = [
        "https://github.com/search?q=openclaw+skill&type=repositories",
        "https://github.com/search?q=claude+code+skill&type=repositories",
        "https://www.npmjs.com/search?q=openclaw",
        "https://pypi.org/search/?q=openclaw",
        "https://clawhub.com/",
        "https://www.reddit.com/search/?q=openclaw",
        "https://dev.to/search?q=openclaw",
        "https://medium.com/search?q=openclaw",
    ]
    
    def __init__(self, crawldir: str = None, output_file: str = None,
                 max_results: int = 50, **kwargs):
        super().__init__(**kwargs)
        self.crawldir = crawldir
        self.output_file = output_file or f"openclaw_discovery_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        self.results = []
        self.max_results = max_results
    
    def categorize_url(self, url: str) -> str:
        """Categorize URL by source."""
        if "github" in url:
            return "skill" if "skill" in url.lower() else "plugin"
        elif "npm" in url:
            return "plugin"
        elif "pypi" in url:
            return "integration"
        elif "clawhub" in url:
            return "skill"
        elif "reddit" in url:
            return "discussion"
        elif "dev.to" in url:
            return "tutorial"
        elif "medium" in url:
            return "tutorial"
        elif "twitter" in url or "x.com" in url:
            return "announcement"
        return "tool"
    
    async def parse(self, response: Response):
        """Extract resource data."""
        
        url = response.url
        html = response.get()
        
        # GitHub repositories
        if "github.com" in url:
            # Try multiple selector patterns for GitHub
            repos = response.css('li.Box-row, [data-testid="results-list"] li, .repo-list-item')
            
            # Fallback: parse any links that look like repos
            if not repos:
                links = response.css('a[href*="/"][href*="/"]')
                for link in links[:20]:
                    href = link.css('::attr(href)').get() or ""
                    if href.count('/') >= 2 and not href.startswith('/search'):
                        title = link.css('::text').get() or ""
                        if title and len(title) < 100:
                            data = {
                                "title": title.strip()[:80],
                                "url": f"https://github.com{href}" if href.startswith('/') else href,
                                "source": "github.com",
                                "category": "skill",
                                "description": "GitHub repository",
                                "found_at": datetime.now().isoformat(),
                            }
                            self.results.append(data)
                            yield data
                return
            
            for repo in repos[:10]:
                title_elem = repo.css('h3 a, h2 a, a[data-hovercard-type="repository"]')
                if title_elem:
                    title = title_elem[0].css('::text').get().strip()
                    link = title_elem[0].css('::attr(href)').get()
                    if link and not link.startswith('http'):
                        link = f"https://github.com{link}"
                    
                    # Get stars if available
                    stars_text = repo.css('[aria-label*="stars"]::text').get() or "0"
                    stars = int(re.search(r'(\d+)', stars_text).group(1)) if stars_text else 0
                    
                    # Get description
                    desc = repo.css('.mb-1::text, .f6::text').get() or ""
                    
                    data = {
                        "title": title,
                        "url": link,
                        "source": "github.com",
                        "category": self.categorize_url(link),
                        "description": desc.strip()[:200],
                        "stars": stars,
                        "found_at": datetime.now().isoformat(),
                    }
                    
                    if data["url"] and data["title"]:
                        self.results.append(data)
                        yield data
        
        # NPM packages
        elif "npmjs.com" in url:
            packages = response.css('[data-testid="package-item"]')
            for pkg in packages[:10]:
                title = pkg.css('[data-testid="package-name"]::text').get()
                link = pkg.css('[data-testid="package-name"]::attr(href)').get()
                desc = pkg.css('[data-testid="package-description"]::text').get() or ""
                
                if title:
                    data = {
                        "title": title.strip(),
                        "url": f"https://www.npmjs.com{link}" if link else "",
                        "source": "npmjs.com",
                        "category": "plugin",
                        "description": desc.strip()[:200],
                        "found_at": datetime.now().isoformat(),
                    }
                    self.results.append(data)
                    yield data
        
        # PyPI packages
        elif "pypi.org" in url:
            packages = response.css('a.package-snippet')
            for pkg in packages[:10]:
                title = pkg.css('.package-snippet__name::text').get()
                desc = pkg.css('.package-snippet__description::text').get() or ""
                link = pkg.css('::attr(href)').get()
                
                if title:
                    data = {
                        "title": title.strip(),
                        "url": f"https://pypi.org{link}" if link else "",
                        "source": "pypi.org",
                        "category": "integration",
                        "description": desc.strip()[:200],
                        "found_at": datetime.now().isoformat(),
                    }
                    self.results.append(data)
                    yield data
        
        # Dev.to articles
        elif "dev.to" in url:
            articles = response.css('article')
            for article in articles[:10]:
                title = article.css('h2 a::text').get()
                link = article.css('h2 a::attr(href)').get()
                author = article.css('[itemprop="author"]::text').get() or ""
                
                if title:
                    data = {
                        "title": title.strip(),
                        "url": link if link and link.startswith('http') else f"https://dev.to{link}",
                        "source": "dev.to",
                        "category": "tutorial",
                        "description": f"By {author}" if author else "",
                        "found_at": datetime.now().isoformat(),
                    }
                    self.results.append(data)
                    yield data
        
        # Medium articles
        elif "medium.com" in url:
            articles = response.css('article, [data-testid="postPreviewCard"]')
            for article in articles[:10]:
                title = article.css('h2::text, [data-testid="postPreviewCard-title"]::text').get()
                link = article.css('a[href*="/p/"]::attr(href)').get()
                
                if title:
                    data = {
                        "title": title.strip()[:100],
                        "url": link if link and link.startswith('http') else "",
                        "source": "medium.com",
                        "category": "tutorial",
                        "description": "",
                        "found_at": datetime.now().isoformat(),
                    }
                    self.results.append(data)
                    yield data
        
        # ClawHub
        elif "clawhub.com" in url:
            skills = response.css('[data-testid="skill-card"], .skill-card, a[href*="/skills/"]')
            for skill in skills[:10]:
                title = skill.css('h3::text, h2::text, .title::text').get()
                link = skill.css('a::attr(href)').get() or skill.css('::attr(href)').get()
                
                if title:
                    data = {
                        "title": title.strip()[:100],
                        "url": link if link and link.startswith('http') else f"https://clawhub.com{link}" if link else "",
                        "source": "clawhub.com",
                        "category": "skill",
                        "description": "Community skill from ClawHub",
                        "found_at": datetime.now().isoformat(),
                    }
                    self.results.append(data)
                    yield data
    
    def closed(self, reason):
        """Save results and filter duplicates."""
        if self.results:
            # Remove duplicates by URL
            seen = set()
            unique_results = []
            for r in self.results:
                if r.get('url') not in seen:
                    seen.add(r.get('url'))
                    unique_results.append(r)
            
            with open(self.output_file, 'w') as f:
                json.dump(unique_results, f, indent=2)
            
            print(f"Saved {len(unique_results)} unique discoveries to {self.output_file}")
            
            # Count by category
            categories = {}
            for r in unique_results:
                cat = r.get('category', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1
            
            print(f"Categories: {categories}")


if __name__ == "__main__":
    # Test run
    spider = OpenClawDiscoverySpider(max_results=20)
    result = spider.start()
    print(f"Discovered {len(result.items)} resources")
