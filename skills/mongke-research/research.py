#!/usr/bin/env python3
"""
Mongke Research Skill — Main Orchestrator

Combines Scrapling (web scraping), Ollama (local LLM), and Neo4j (knowledge graph)
for automated research tasks.

Usage:
    python3 research.py --query "Your research question" --sources "url1,url2"
    python3 research.py --topic "Topic name" --subtopics "sub1,sub2,sub3"
    python3 research.py --query "..." --output neo4j,json,markdown
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapling.fetchers import StealthyFetcher, Fetcher

# Optional SearXNG integration
try:
    from .searxng_search import SearXNGSearch
    SEARXNG_AVAILABLE = True
except ImportError:
    SEARXNG_AVAILABLE = False
    SearXNGSearch = None


class MongkeResearchSkill:
    """Research skill for Mongke agent."""
    
    def __init__(self, ollama_model="qwen3.5:9b", ollama_timeout=90):
        self.ollama_model = ollama_model
        self.ollama_timeout = ollama_timeout
        self.ollama_url = "http://localhost:11434/api/chat"
        
        # Initialize Scrapling
        StealthyFetcher.adaptive = True
        
        # Initialize SearXNG if available
        self.searxng = SearXNGSearch() if SEARXNG_AVAILABLE else None
        
    def search_web(self, query: str, num_results: int = 10) -> list:
        """
        Search the web using SearXNG and return URLs.
        
        Args:
            query: Search query
            num_results: Number of results to return
        
        Returns:
            List of URLs from search results
        """
        if not self.searxng:
            print("  ⚠ SearXNG not available, provide URLs manually")
            return []
        
        print(f"  🔍 Searching web: {query}")
        results = self.searxng.search(query, limit=num_results)
        
        if results:
            urls = [r['url'] for r in results if r.get('url')]
            print(f"    ✓ Found {len(urls)} sources")
            return urls
        else:
            print("    ✗ No search results")
            return []
    
    def scrape_url(self, url, stealthy=True, depth=1):
        """Scrape a single URL using Scrapling."""
        print(f"  📄 Scraping: {url}")
        
        try:
            if stealthy:
                page = StealthyFetcher.fetch(url, solve_cloudflare=True, headless=True)
            else:
                page = Fetcher.get(url)
            
            # Extract main content
            content = {
                "url": url,
                "title": page.css("title::text").get() or "Untitled",
                "text": page.css("body").get() or "",
                "links": page.css("a::attr(href)").getall()[:20],
            }
            
            print(f"    ✓ Title: {content['title'][:60]}...")
            return content
            
        except Exception as e:
            print(f"    ✗ Error: {str(e)[:80]}")
            return {"url": url, "error": str(e)}
    
    def analyze_with_ollama(self, content, query):
        """Analyze scraped content with Ollama LLM."""
        import requests
        
        prompt = f"""You are a research analyst. Analyze this content for the query: "{query}"

CONTENT:
{content['text'][:8000]}  # Truncate to avoid token limits

Extract:
1. KEY ENTITIES (organizations, people, places) - max 10
2. KEY CONCEPTS (ideas, theories, themes) - max 10
3. RELATIONSHIPS between entities/concepts
4. RELEVANCE to query (0-1 score)

Respond in JSON format:
{{
  "entities": [{{"name": "...", "type": "organization|person|place|symbol", "description": "..."}}],
  "concepts": [{{"name": "...", "description": "..."}}],
  "relationships": [{{"from": "...", "to": "...", "type": "..."}}],
  "relevance": 0.0,
  "summary": "..."
}}"""

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {"role": "system", "content": "You are a concise research analyst. Respond in valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                },
                timeout=self.ollama_timeout
            )
            
            if resp.status_code == 200:
                text = resp.json()["message"]["content"].strip()
                # Clean up any markdown code blocks
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                return json.loads(text)
            else:
                return {"error": f"HTTP {resp.status_code}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def save_to_neo4j(self, analysis, query, tags=None):
        """Save analysis results to Neo4j knowledge graph."""
        try:
            from neo4j import GraphDatabase
            
            driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))
            timestamp = datetime.now().isoformat()
            tags = tags or ["research", query.lower().replace(" ", "-")]
            
            with driver.session() as session:
                # Save entities
                for entity in analysis.get("entities", []):
                    session.run("""
                        MERGE (e:ResearchEntity {name: $name})
                        SET e.type = $type,
                            e.description = $description,
                            e.query = $query,
                            e.tags = $tags,
                            e.confidence = $relevance,
                            e.updated = $timestamp
                    """, 
                    name=entity["name"],
                    type=entity.get("type", "unknown"),
                    description=entity.get("description", ""),
                    query=query,
                    tags=tags,
                    relevance=analysis.get("relevance", 0.5),
                    timestamp=timestamp
                    )
                
                # Save concepts
                for concept in analysis.get("concepts", []):
                    session.run("""
                        MERGE (c:ResearchConcept {name: $name})
                        SET c.description = $description,
                            c.query = $query,
                            c.tags = $tags,
                            c.updated = $timestamp
                    """,
                    name=concept["name"],
                    description=concept.get("description", ""),
                    query=query,
                    tags=tags,
                    timestamp=timestamp
                    )
                
                # Save relationships
                for rel in analysis.get("relationships", []):
                    session.run("""
                        MATCH (a:ResearchEntity {name: $from})
                        MATCH (b:ResearchEntity {name: $to})
                        MERGE (a)-[r:RELATED_TO {type: $rel_type}]->(b)
                        SET r.updated = $timestamp
                    """,
                    from_=rel["from"],
                    to=rel["to"],
                    rel_type=rel.get("type", "related"),
                    timestamp=timestamp
                    )
            
            driver.close()
            print(f"  ✓ Saved to Neo4j: {len(analysis.get('entities', []))} entities, {len(analysis.get('concepts', []))} concepts")
            return True
            
        except Exception as e:
            print(f"  ✗ Neo4j error: {str(e)[:80]}")
            return False
    
    def research(self, query, sources=None, depth=1, stealthy=True, output="neo4j", tags=None):
        """
        Main research method.
        
        Args:
            query: Research question or topic
            sources: List of URLs to scrape
            depth: Crawl depth (1 = only provided URLs)
            stealthy: Use StealthyFetcher for anti-bot
            output: Output format(s) - neo4j, json, markdown
            tags: Tags for categorization
        
        Returns:
            dict with analysis results
        """
        print(f"\n🔍 Mongke Research: {query}")
        
        # Auto-find sources via SearXNG if none provided
        if not sources:
            if self.searxng:
                print("   Finding sources via SearXNG...")
                sources = self.search_web(query, num_results=10)
            else:
                print("  ✗ No sources provided and SearXNG unavailable")
                return {"error": "No sources"}
        
        print(f"   Sources: {len(sources)} URLs")
        print(f"   Depth: {depth}")
        print()
        
        if not sources:
            print("  ✗ No sources found")
            return {"error": "No sources found"}
        
        all_analysis = {
            "query": query,
            "sources": sources,
            "timestamp": datetime.now().isoformat(),
            "entities": [],
            "concepts": [],
            "relationships": [],
            "summary": ""
        }
        
        # Scrape and analyze each source
        for url in sources:
            content = self.scrape_url(url, stealthy=stealthy, depth=depth)
            
            if "error" not in content:
                analysis = self.analyze_with_ollama(content, query)
                
                if "error" not in analysis:
                    all_analysis["entities"].extend(analysis.get("entities", []))
                    all_analysis["concepts"].extend(analysis.get("concepts", []))
                    all_analysis["relationships"].extend(analysis.get("relationships", []))
                    
                    # Deduplicate
                    all_analysis["entities"] = list({e["name"]: e for e in all_analysis["entities"]}.values())
                    all_analysis["concepts"] = list({c["name"]: c for c in all_analysis["concepts"]}.values())
        
        # Generate summary
        summary_prompt = f"""Summarize this research on "{query}" in 3-5 sentences.

ENTITIES: {len(all_analysis['entities'])}
CONCEPTS: {len(all_analysis['concepts'])}

KEY FINDINGS:
{json.dumps(all_analysis, indent=2)[:2000]}

SUMMARY:"""
        
        import requests
        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {"role": "system", "content": "You are a concise research summarizer."},
                        {"role": "user", "content": summary_prompt}
                    ],
                    "stream": False
                },
                timeout=60
            )
            if resp.status_code == 200:
                all_analysis["summary"] = resp.json()["message"]["content"].strip()
        except:
            all_analysis["summary"] = f"Research on {query} found {len(all_analysis['entities'])} entities and {len(all_analysis['concepts'])} concepts."
        
        # Output results
        if "neo4j" in output:
            self.save_to_neo4j(all_analysis, query, tags)
        
        if "json" in output:
            output_file = f"research_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            with open(output_file, "w") as f:
                json.dump(all_analysis, f, indent=2)
            print(f"  ✓ JSON saved: {output_file}")
        
        if "markdown" in output:
            md = f"# Research: {query}\n\n"
            md += f"**Sources:** {len(sources)} URLs\n"
            md += f"**Entities:** {len(all_analysis['entities'])}\n"
            md += f"**Concepts:** {len(all_analysis['concepts'])}\n\n"
            md += f"## Summary\n\n{all_analysis['summary']}\n\n"
            md += "## Entities\n\n"
            for e in all_analysis['entities'][:10]:
                md += f"- **{e['name']}** ({e.get('type', '?')}): {e.get('description', '')[:100]}\n"
            md += "\n## Concepts\n\n"
            for c in all_analysis['concepts'][:10]:
                md += f"- **{c['name']}**: {c.get('description', '')[:100]}\n"
            
            output_file = f"research_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
            with open(output_file, "w") as f:
                f.write(md)
            print(f"  ✓ Markdown saved: {output_file}")
        
        return all_analysis


def main():
    parser = argparse.ArgumentParser(description="Mongke Research Skill")
    parser.add_argument("--query", help="Research question or topic")
    parser.add_argument("--topic", help="Topic name (alternative to query)")
    parser.add_argument("--sources", help="Comma-separated URLs to scrape")
    parser.add_argument("--subtopics", help="Comma-separated subtopics")
    parser.add_argument("--depth", type=int, default=1, help="Crawl depth")
    parser.add_argument("--stealthy", action="store_true", default=True, help="Use stealth mode")
    parser.add_argument("--no-stealthy", action="store_false", dest="stealthy", help="Disable stealth mode")
    parser.add_argument("--output", default="neo4j", help="Output format: neo4l,json,markdown (comma-separated)")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--ollama-model", default="qwen3.5:9b", help="Ollama model")
    parser.add_argument("--ollama-timeout", type=int, default=90, help="Ollama timeout (seconds)")
    
    args = parser.parse_args()
    
    query = args.query or args.topic
    if not query:
        print("Error: --query or --topic required")
        sys.exit(1)
    
    sources = args.sources.split(",") if args.sources else []
    tags = args.tags.split(",") if args.tags else None
    
    skill = MongkeResearchSkill(
        ollama_model=args.ollama_model,
        ollama_timeout=args.ollama_timeout
    )
    
    result = skill.research(
        query=query,
        sources=sources,
        depth=args.depth,
        stealthy=args.stealthy,
        output=args.output,
        tags=tags
    )
    
    print(f"\n✅ Research complete!")
    print(f"   Entities: {len(result.get('entities', []))}")
    print(f"   Concepts: {len(result.get('concepts', []))}")
    print(f"   Summary: {result.get('summary', '')[:100]}...")


if __name__ == "__main__":
    main()
