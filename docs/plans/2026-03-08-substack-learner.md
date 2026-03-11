# Substack Learner Skill - Implementation Plan

**Plan ID:** substack-learner-v1
**Created:** 2026-03-08
**Priority:** HIGH
**Target:** Hans Amato Substack (extendable to any Substack publication)

---

## Objective

Build a reusable skill that downloads all articles from a Substack publication, structures the content with LLM-assisted analysis, and stores it in Neo4j for knowledge retrieval and query. The system will extract articles, identify concepts/insights, and enable semantic querying across the entire corpus.

**Success Criteria:**
- All Hans Amato articles downloaded and stored in Neo4j
- Concepts, insights, and relationships extracted via LLM analysis
- Query interface responds to natural language questions about content
- Documentation enables adding new Substack sources in <5 minutes

---

## Phase -1: Prerequisites and Environment Setup

**Duration:** 15 minutes
**Dependencies:** None

Set up the Python environment, verify Neo4j connectivity, and create required directory structure.

### Task -1.1: Verify Neo4j Connection

Verify Neo4j is accessible and credentials are configured. The Kurultai system already uses Neo4j, so we should leverage existing configuration.

```bash
# Check if Neo4j connection details exist
cat ~/.openclaw/config/neo4j.json 2>/dev/null || echo "Config not found"
# Or check environment
env | grep NEO4J
```

Expected: Neo4j URI and credentials available via environment or config file.

### Task -1.2: Create Project Structure

Create the directory structure for the Substack Learner skill.

```bash
mkdir -p scripts/substack_learner
mkdir -p scripts/substack_learner/data
mkdir -p scripts/substack_learner/queries
mkdir -p docs/substack_learner
```

### Task -1.3: Install Python Dependencies

Install required packages for scraping, Neo4j, and LLM integration.

```bash
# Install dependencies
pip install requests beautifulsoup4 feedparser neo4j lxml
pip install python-dotenv tqdm tenacity
pip install anthropic  # For LLM-based content analysis
```

### Exit Criteria Phase -1

- [ ] Neo4j connection details verified (uri, user, password)
- [ ] Directory structure created: `scripts/substack_learner/`
- [ ] All Python packages installed without errors
- [ ] `import neo4j` succeeds in Python

---

## Phase 0: Neo4j Schema Design

**Duration:** 20 minutes
**Dependencies:** Phase -1

Design and implement the Neo4j graph schema for storing articles, concepts, insights, and relationships.

### Task 0.1: Define Node Types

Create Cypher queries to define constraints and indexes for all node types.

**Node Types:**

```cypher
// Article Node
CREATE CONSTRAINT article_url_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.url IS UNIQUE;
CREATE INDEX article_published_date IF NOT EXISTS FOR (a:Article) ON (a.published_date);

// Author Node
CREATE CONSTRAINT author_name_unique IF NOT EXISTS FOR (au:Author) REQUIRE au.name IS UNIQUE;

// Concept Node
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;
CREATE INDEX concept_category IF NOT EXISTS FOR (c:Concept) ON (c.category);

// Insight Node
CREATE CONSTRAINT insight_id_unique IF NOT EXISTS FOR (i:Insight) REQUIRE i.id IS UNIQUE;

// Tag/Topic Node
CREATE CONSTRAINT tag_name_unique IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE;
```

Create `scripts/substack_learner/queries/01_schema.cypher` with these definitions.

### Task 0.2: Define Relationship Types

Document the relationship types with their properties.

**Relationships:**

| Relationship | From | To | Properties |
|--------------|------|-----|------------|
| `ARTICLE_WRITTEN_BY` | Article | Author | - |
| `ARTICLE_HAS_TAG` | Article | Tag | confidence |
| `ARTICLE_CONTAINS_CONCEPT` | Article | Concept | mentions_count, relevance_score |
| `ARTICLE_PROVIDES_INSIGHT` | Article | Insight | position_in_article |
| `CONCEPT_RELATED_TO` | Concept | Concept | relationship_type, strength |
| `INSIGHT_ABOUT_CONCEPT` | Insight | Concept | - |
| `AUTHOR_EXPERTISE_IN` | Author | Concept | expertise_level |

### Task 0.3: Create Schema Initialization Script

Create `scripts/substack_learner/init_schema.py`:

```python
#!/usr/bin/env python3
"""Initialize Neo4j schema for Substack Learner."""

from neo4j import GraphDatabase
import os

def init_schema(driver):
    """Create all constraints and indexes."""
    queries = [
        # Article constraints
        "CREATE CONSTRAINT article_url_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.url IS UNIQUE",
        "CREATE INDEX article_published_date IF NOT EXISTS FOR (a:Article) ON (a.published_date)",

        # Author constraints
        "CREATE CONSTRAINT author_name_unique IF NOT EXISTS FOR (au:Author) REQUIRE au.name IS UNIQUE",

        # Concept constraints
        "CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
        "CREATE INDEX concept_category IF NOT EXISTS FOR (c:Concept) ON (c.category)",

        # Insight constraints
        "CREATE CONSTRAINT insight_id_unique IF NOT EXISTS FOR (i:Insight) REQUIRE i.id IS UNIQUE",

        # Tag constraints
        "CREATE CONSTRAINT tag_name_unique IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
    ]

    with driver.session() as session:
        for query in queries:
            try:
                session.run(query)
                print(f"✓ {query[:50]}...")
            except Exception as e:
                print(f"✗ {query[:50]}...: {e}")

if __name__ == "__main__":
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    init_schema(driver)
    driver.close()
```

### Exit Criteria Phase 0

- [ ] `scripts/substack_learner/queries/01_schema.cypher` created
- [ ] `scripts/substack_learner/init_schema.py` created
- [ ] Running `init_schema.py` creates all constraints and indexes
- [ ] Cypher query `SHOW CONSTRAINTS` shows all Substack constraints

---

## Phase 1: Substack Scraper Implementation

**Duration:** 45 minutes
**Dependencies:** Phase 0

Build the scraper that fetches articles from Substack via multiple methods (RSS, archive page, direct article fetch).

### Task 1.1: Implement RSS Feed Parser

Create `scripts/substack_learner/rss_fetcher.py`:

```python
#!/usr/bin/env python3
"""Fetch articles from Substack RSS feed."""

import feedparser
from datetime import datetime
from typing import List, Dict
import requests

def fetch_rss(substack_url: str) -> List[Dict]:
    """
    Fetch articles from Substack RSS feed.

    Args:
        substack_url: Base URL (e.g., https://hansamato.substack.com)

    Returns:
        List of article dictionaries with metadata
    """
    rss_url = f"{substack_url.rstrip('/')}/feed"

    feed = feedparser.parse(rss_url)
    articles = []

    for entry in feed.entries:
        article = {
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published_date": entry.get("published", ""),
            "summary": entry.get("summary", ""),
            "author": entry.get("author", ""),
            "tags": [tag.term for tag in entry.get("tags", [])],
            "content": entry.get("content", [{}])[0].get("value", ""),
        }
        articles.append(article)

    return articles

if __name__ == "__main__":
    articles = fetch_rss("https://hansamato.substack.com")
    print(f"Found {len(articles)} articles")
```

### Task 1.2: Implement Full Content Fetcher

RSS feeds contain truncated content. Create `scripts/substack_learner/content_fetcher.py` to fetch full article HTML:

```python
#!/usr/bin/env python3
"""Fetch full article content from Substack."""

from bs4 import BeautifulSoup
import requests
from typing import Dict
import time

def fetch_full_article(url: str, rate_limit: float = 1.0) -> Dict:
    """
    Fetch full article content from Substack URL.

    Args:
        url: Article URL
        rate_limit: Seconds to wait between requests

    Returns:
        Article dict with full content
    """
    time.sleep(rate_limit)  # Respect rate limiting

    headers = {
        "User-Agent": "SubstackLearer/1.0 (Knowledge Archive Bot)"
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    # Extract article body (Substack specific selectors)
    body_selectors = [
        "div.post-content",
        "div.available-content",
        "article",
        "[data-testid='post-content']"
    ]

    content = ""
    for selector in body_selectors:
        elem = soup.select_one(selector)
        if elem:
            content = elem.get_text(separator="\n", strip=True)
            break

    # Extract metadata
    title = soup.find("meta", property="og:title")
    author = soup.find("meta", property="article:author")
    published = soup.find("meta", property="article:published_time")

    return {
        "url": url,
        "title": title["content"] if title else "",
        "author": author["content"] if author else "",
        "published_date": published["content"] if published else "",
        "content": content,
        "word_count": len(content.split()),
    }
```

### Task 1.3: Implement Main Scraper Orchestration

Create `scripts/substack_learner/substack_scraper.py`:

```python
#!/usr/bin/env python3
"""Main Substack scraper orchestrator."""

from rss_fetcher import fetch_rss
from content_fetcher import fetch_full_article
from typing import List, Dict
import json
from pathlib import Path
from tqdm import tqdm

def scrape_publication(
    substack_url: str,
    output_path: str = "data/articles.json",
    rate_limit: float = 1.0
) -> List[Dict]:
    """
    Scrape all articles from a Substack publication.

    Args:
        substack_url: Base URL of the Substack
        output_path: Where to save the JSON output
        rate_limit: Seconds between requests

    Returns:
        List of complete article dictionaries
    """
    # First, fetch metadata from RSS
    print(f"Fetching article list from {substack_url}...")
    articles = fetch_rss(substack_url)
    print(f"Found {len(articles)} articles in RSS feed")

    # Then fetch full content for each
    complete_articles = []
    for article in tqdm(articles, desc="Fetching full content"):
        full = fetch_full_article(article["url"], rate_limit)
        complete_articles.append(full)

    # Save to file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(complete_articles, indent=2))

    print(f"Saved {len(complete_articles)} articles to {output_path}")
    return complete_articles

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://hansamato.substack.com"
    scrape_publication(url)
```

### Task 1.4: Add Error Handling and Retry Logic

Enhance the scraper with tenacity for resilience:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_full_article_with_retry(url: str) -> Dict:
    """Fetch article with exponential backoff retry."""
    return fetch_full_article(url)
```

### Exit Criteria Phase 1

- [ ] `scripts/substack_learner/rss_fetcher.py` created
- [ ] `scripts/substack_learner/content_fetcher.py` created
- [ ] `scripts/substack_learner/substack_scraper.py` created
- [ ] Running `python substack_scraper.py https://hansamato.substack.com` produces `data/articles.json`
- [ ] JSON contains at least 10 articles with full content
- [ ] Each article has: url, title, author, published_date, content, word_count

---

## Phase 1.5: Content Analysis and Structuring

**Duration:** 60 minutes
**Dependencies:** Phase 1

Use LLM to analyze article content and extract structured concepts, insights, and relationships.

### Task 1.5.1: Design Content Analysis Schema

Define the output structure for LLM analysis:

```python
# Content analysis result schema
{
    "article_url": "https://...",
    "concepts": [
        {
            "name": "Mental Model",
            "definition": "A cognitive framework for understanding decisions.",
            "category": "framework",
            "confidence": 0.95
        }
    ],
    "insights": [
        {
            "text": "Compounding applies to knowledge, not just capital.",
            "type": "principle",
            "applicability": "general",
            "confidence": 0.9
        }
    ],
    "quotes": [
        {
            "text": "The best time to plant a tree was 20 years ago.",
            "context": "Discussed in relation to skill acquisition."
        }
    ],
    "topics": ["learning", "compounding", "skills"],
    "summary": "3 sentence overview of key themes."
}
```

### Task 1.5.2: Implement LLM Content Analyzer

Create `scripts/substack_learner/content_analyzer.py`:

```python
#!/usr/bin/env python3
"""Analyze article content using LLM to extract concepts and insights."""

import os
from anthropic import Anthropic
from typing import Dict, List
import json

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ANALYSIS_PROMPT = """Analyze this article and extract structured knowledge.

Article Title: {title}
Author: {author}
Content:
{content}

Extract and return JSON with this structure:
{{
    "concepts": [{{"name": "...", "definition": "...", "category": "..."}}],
    "insights": [{{"text": "...", "type": "principle|framework|actionable", "applicability": "..."}}],
    "quotes": [{{"text": "...", "context": "..."}}],
    "topics": ["topic1", "topic2"],
    "summary": "2-3 sentence overview"
}}

Focus on: mental models, frameworks, actionable advice, unique insights.
Only include significant concepts (not generic terms)."""

def analyze_article(article: Dict) -> Dict:
    """
    Use Claude to analyze article content.

    Args:
        article: Article dict with content

    Returns:
        Analysis dict with concepts, insights, quotes, topics
    """
    prompt = ANALYSIS_PROMPT.format(
        title=article["title"],
        author=article["author"],
        content=article["content"][:15000]  # Token limit
    )

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text
    # Extract JSON from response
    try:
        # Handle markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"concepts": [], "insights": [], "quotes": [], "topics": [], "summary": ""}

def analyze_batch(articles: List[Dict]) -> List[Dict]:
    """Analyze multiple articles with progress tracking."""
    from tqdm import tqdm

    results = []
    for article in tqdm(articles, desc="Analyzing content"):
        analysis = analyze_article(article)
        results.append({
            "article_url": article["url"],
            **analysis
        })
    return results
```

### Task 1.5.3: Create Batch Processing Script

Create `scripts/substack_learner/analyze_content.py`:

```python
#!/usr/bin/env python3
"""Batch analyze all scraped articles."""

import json
from pathlib import Path
from content_analyzer import analyze_batch

def main():
    # Load scraped articles
    articles_path = Path("data/articles.json")
    articles = json.loads(articles_path.read_text())

    print(f"Analyzing {len(articles)} articles...")

    # Analyze
    analyses = analyze_batch(articles)

    # Save
    output = Path("data/analyses.json")
    output.write_text(json.dumps(analyses, indent=2))

    print(f"Saved analyses to {output}")

if __name__ == "__main__":
    main()
```

### Exit Criteria Phase 1.5

- [ ] `scripts/substack_learner/content_analyzer.py` created
- [ ] `scripts/substack_learner/analyze_content.py` created
- [ ] Analysis schema documented in code
- [ ] Running analyzer produces `data/analyses.json`
- [ ] Each analysis contains: concepts, insights, quotes, topics, summary

---

## Phase 2: Neo4j Storage Implementation

**Duration:** 45 minutes
**Dependencies:** Phase 0, Phase 1, Phase 1.5

Implement the storage layer that writes articles and analyses to Neo4j.

### Task 2.1: Create Article Storage Module

Create `scripts/substack_learner/neo4j_store.py`:

```python
#!/usr/bin/env python3
"""Store articles and analyses in Neo4j."""

from neo4j import GraphDatabase
import os
from typing import Dict, List
from datetime import datetime

class SubstackKnowledgeStore:
    """Neo4j storage for Substack articles and analyses."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
        )

    def close(self):
        self.driver.close()

    def store_author(self, author_data: Dict) -> str:
        """Store or update author node."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (a:Author {name: $name})
                SET a.bio = $bio,
                    a.substack_url = $substack_url,
                    a.last_updated = datetime()
                RETURN a.name as name
            """, **author_data)
            return result.single()["name"]

    def store_article(self, article: Dict) -> str:
        """Store article node and link to author."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (a:Article {url: $url})
                SET a.title = $title,
                    a.published_date = date($published_date),
                    a.word_count = $word_count,
                    a.summary = $summary,
                    a.content_preview = $content_preview,
                    a.scraped_at = datetime()
                RETURN a.url as url
            """, {
                "url": article["url"],
                "title": article["title"],
                "published_date": article.get("published_date", ""),
                "word_count": article.get("word_count", 0),
                "summary": article.get("summary", ""),
                "content_preview": article.get("content", "")[:500]
            })
            return result.single()["url"]

    def link_article_to_author(self, article_url: str, author_name: str):
        """Create ARTICLE_WRITTEN_BY relationship."""
        with self.driver.session() as session:
            session.run("""
                MATCH (a:Article {url: $article_url})
                MATCH (au:Author {name: $author_name})
                MERGE (a)-[:ARTICLE_WRITTEN_BY]->(au)
            """, article_url=article_url, author_name=author_name)

    def store_concept(self, concept: Dict) -> str:
        """Store or update concept node."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (c:Concept {name: $name})
                SET c.definition = $definition,
                    c.category = $category
                RETURN c.name as name
            """, concept)
            return result.single()["name"]

    def link_article_to_concept(self, article_url: str, concept_name: str, score: float = 1.0):
        """Create ARTICLE_CONTAINS_CONCEPT relationship."""
        with self.driver.session() as session:
            session.run("""
                MATCH (a:Article {url: $article_url})
                MATCH (c:Concept {name: $concept_name})
                MERGE (a)-[r:ARTICLE_CONTAINS_CONCEPT]->(c)
                SET r.relevance_score = $score,
                    r.discovered_at = datetime()
            """, article_url=article_url, concept_name=concept_name, score=score)

    def store_insight(self, insight: Dict, article_url: str) -> str:
        """Store insight node and link to article."""
        insight_id = f"{article_url}#{hash(insight['text'])}"
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Article {url: $article_url})
                CREATE (i:Insight {
                    id: $id,
                    text: $text,
                    type: $type,
                    applicability: $applicability,
                    created_at: datetime()
                })
                CREATE (a)-[:ARTICLE_PROVIDES_INSIGHT]->(i)
                RETURN i.id as id
            """, {
                "article_url": article_url,
                "id": insight_id,
                "text": insight["text"],
                "type": insight.get("type", "general"),
                "applicability": insight.get("applicability", "general")
            })
            return result.single()["id"]

    def store_tag(self, tag_name: str) -> str:
        """Store or update tag node."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (t:Tag {name: $name})
                RETURN t.name as name
            """, name=tag_name)
            return result.single()["name"]

    def link_article_to_tag(self, article_url: str, tag_name: str):
        """Create ARTICLE_HAS_TAG relationship."""
        with self.driver.session() as session:
            session.run("""
                MATCH (a:Article {url: $article_url})
                MERGE (t:Tag {name: $tag_name})
                MERGE (a)-[:ARTICLE_HAS_TAG]->(t)
            """, article_url=article_url, tag_name=tag_name)
```

### Task 2.2: Create Import Orchestrator

Create `scripts/substack_learner/import_to_neo4j.py`:

```python
#!/usr/bin/env python3
"""Import scraped articles and analyses to Neo4j."""

import json
from pathlib import Path
from neo4j_store import SubstackKnowledgeStore
from tqdm import tqdm

def import_data():
    """Import all scraped and analyzed data to Neo4j."""

    store = SubstackKnowledgeStore()

    try:
        # Load data
        articles = json.loads(Path("data/articles.json").read_text())
        analyses = json.loads(Path("data/analyses.json").read_text())

        # Create lookup
        analysis_by_url = {a["article_url"]: a for a in analyses}

        print(f"Importing {len(articles)} articles...")

        for article in tqdm(articles):
            url = article["url"]
            analysis = analysis_by_url.get(url, {})

            # Store author
            author_name = article.get("author", "Unknown")
            store.store_author({
                "name": author_name,
                "bio": "",
                "substack_url": ""
            })

            # Store article
            store.store_article(article)
            store.link_article_to_author(url, author_name)

            # Store concepts
            for concept in analysis.get("concepts", []):
                store.store_concept(concept)
                store.link_article_to_concept(url, concept["name"], concept.get("confidence", 1.0))

            # Store insights
            for insight in analysis.get("insights", []):
                store.store_insight(insight, url)

            # Store tags/topics
            for topic in analysis.get("topics", []):
                store.store_tag(topic)
                store.link_article_to_tag(url, topic)

        print("Import complete!")

    finally:
        store.close()

if __name__ == "__main__":
    import_data()
```

### Task 2.3: Create Utility Script to Clear Data

Create `scripts/substack_learner/clear_data.py`:

```python
#!/usr/bin/env python3
"""Clear all Substack data from Neo4j (use with caution!)."""

from neo4j import GraphDatabase
import os

def clear_substack_data():
    """Delete all nodes and relationships created by Substack Learner."""
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
    )

    with driver.session() as session:
        # Delete relationships first
        session.run("MATCH ()-[r:ARTICLE_WRITTEN_BY]->() DELETE r")
        session.run("MATCH ()-[r:ARTICLE_HAS_TAG]->() DELETE r")
        session.run("MATCH ()-[r:ARTICLE_CONTAINS_CONCEPT]->() DELETE r")
        session.run("MATCH ()-[r:ARTICLE_PROVIDES_INSIGHT]->() DELETE r")
        session.run("MATCH ()-[r:CONCEPT_RELATED_TO]->() DELETE r")

        # Delete nodes
        session.run("MATCH (i:Insight) DELETE i")
        session.run("MATCH (a:Article) DELETE a")
        session.run("MATCH (t:Tag) DELETE t")
        # Don't delete concepts if they might be shared
        # session.run("MATCH (c:Concept) DELETE c")
        # session.run("MATCH (au:Author) DELETE au")

    print("Cleared all Substack Learner data")
    driver.close()

if __name__ == "__main__":
    confirm = input("This will delete all Substack data. Type 'yes' to confirm: ")
    if confirm.lower() == "yes":
        clear_substack_data()
```

### Exit Criteria Phase 2

- [ ] `scripts/substack_learner/neo4j_store.py` created
- [ ] `scripts/substack_learner/import_to_neo4j.py` created
- [ ] `scripts/substack_learner/clear_data.py` created
- [ ] Running import script populates Neo4j with articles
- [ ] Cypher query `MATCH (a:Article) RETURN count(a) as count` shows >0 articles
- [ ] Cypher query `MATCH (c:Concept) RETURN count(c) as count` shows >0 concepts

---

## Phase 3: Query Interface

**Duration:** 45 minutes
**Dependencies:** Phase 2

Build a query interface for natural language queries against the knowledge graph.

### Task 3.1: Create Query Module

Create `scripts/substack_learner/queries/query_interface.py`:

```python
#!/usr/bin/env python3
"""Query interface for Substack knowledge graph."""

from neo4j import GraphDatabase
import os
from typing import List, Dict

class SubstackQuery:
    """Query interface for Substack knowledge."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
        )

    def close(self):
        self.driver.close()

    def what_did_author_say_about(self, topic: str, author: str = None) -> List[Dict]:
        """
        Find what the author said about a topic.

        Returns: Articles and insights related to the topic.
        """
        with self.driver.session() as session:
            if author:
                result = session.run("""
                    MATCH (au:Author {name: $author})<-[:ARTICLE_WRITTEN_BY]-(a:Article)
                    MATCH (a)-[:ARTICLE_HAS_TAG]->(t:Tag)
                    WHERE t.name CONTAINS $topic OR a.title CONTAINS $topic
                    RETURN a.title as title, a.url as url, a.summary as summary
                    ORDER BY a.published_date DESC
                """, topic=topic, author=author)
            else:
                result = session.run("""
                    MATCH (a:Article)-[:ARTICLE_HAS_TAG]->(t:Tag)
                    WHERE t.name CONTAINS $topic OR a.title CONTAINS $topic
                    RETURN a.title as title, a.url as url, a.summary as summary
                    ORDER BY a.published_date DESC
                """, topic=topic)

            return [dict(record) for record in result]

    def articles_about_concept(self, concept: str) -> List[Dict]:
        """Find all articles about a specific concept."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Concept {name: $concept})<-[:ARTICLE_CONTAINS_CONCEPT]-(a:Article)
                RETURN a.title as title, a.url as url, a.summary as summary,
                       r.relevance_score as score
                ORDER BY score DESC
            """, concept=concept)

            return [dict(record) for record in result]

    def summarize_insights_on_theme(self, theme: str) -> Dict:
        """Summarize all insights on a theme."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (i:Insight)<-[:ARTICLE_PROVIDES_INSIGHT]-(a:Article)-[:ARTICLE_HAS_TAG]->(t:Tag)
                WHERE t.name CONTAINS $theme OR i.text CONTAINS $theme
                RETURN i.text as insight, i.type as type, a.title as source_article
                ORDER BY i.type, insight
            """, theme=theme)

            insights = [dict(record) for record in result]

            # Group by type
            grouped = {}
            for insight in insights:
                itype = insight["type"]
                if itype not in grouped:
                    grouped[itype] = []
                grouped[itype].append(insight)

            return {"theme": theme, "insights_by_type": grouped, "total": len(insights)}

    def get_concept_graph(self, concept: str) -> Dict:
        """Get related concepts and their relationships."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Concept {name: $concept})-[r:CONCEPT_RELATED_TO]-(related:Concept)
                RETURN related.name as related_concept, r.relationship_type as relationship,
                       r.strength as strength
                ORDER BY strength DESC
            """, concept=concept)

            return {"concept": concept, "related": [dict(r) for r in result]}

    def search_all_content(self, query: str) -> List[Dict]:
        """Full-text search across articles and insights."""
        with self.driver.session() as session:
            result = session.run("""
                CALL db.index.fulltext.queryNodes('articleContentIndex', $query)
                YIELD node, score
                RETURN node.title as title, node.url as url, score
                ORDER BY score DESC LIMIT 20
            """, query=query)

            return [dict(record) for record in result]
```

### Task 3.2: Create CLI Interface

Create `scripts/substack_learner/query_cli.py`:

```python
#!/usr/bin/env python3
"""CLI for querying Substack knowledge."""

import sys
from query_interface import SubstackQuery

def main():
    query = SubstackQuery()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python query_cli.py what <topic>         -- What did author say about X?")
        print("  python query_cli.py concept <concept>    -- Articles about concept")
        print("  python query_cli.py insights <theme>     -- Summarize insights on theme")
        print("  python query_cli.py search <query>       -- Full-text search")
        return

    command = sys.argv[1]

    if command == "what" and len(sys.argv) > 2:
        topic = " ".join(sys.argv[2:])
        results = query.what_did_author_say_about(topic)
        for r in results:
            print(f"- {r['title']}")
            print(f"  {r['url']}")

    elif command == "concept" and len(sys.argv) > 2:
        concept = " ".join(sys.argv[2:])
        results = query.articles_about_concept(concept)
        for r in results:
            print(f"- {r['title']} (relevance: {r.get('score', 'N/A')})")

    elif command == "insights" and len(sys.argv) > 2:
        theme = " ".join(sys.argv[2:])
        result = query.summarize_insights_on_theme(theme)
        print(f"Insights on '{result['theme']}' ({result['total']} total):")
        for itype, insights in result['insights_by_type'].items():
            print(f"\n{itype.upper()}:")
            for i in insights[:5]:
                print(f"  - {i['insight']}")

    elif command == "search" and len(sys.argv) > 2:
        search_query = " ".join(sys.argv[2:])
        results = query.search_all_content(search_query)
        for r in results:
            print(f"- {r['title']} (score: {r['score']:.2f})")

    query.close()

if __name__ == "__main__":
    main()
```

### Exit Criteria Phase 3

- [ ] `scripts/substack_learner/queries/query_interface.py` created
- [ ] `scripts/substack_learner/query_cli.py` created
- [ ] `python query_cli.py what <topic>` returns relevant articles
- [ ] `python query_cli.py insights <theme>` returns grouped insights
- [ ] `python query_cli.py concept <concept>` returns concept-related articles

---

## Phase 4: Documentation

**Duration:** 30 minutes
**Dependencies:** Phase 3

Create comprehensive documentation for using and extending the system.

### Task 4.1: Create README

Create `docs/substack_learner/README.md`:

```markdown
# Substack Learner

Automated knowledge extraction and storage system for Substack publications.

## Features

- Scrape all articles from any Substack publication
- Extract concepts, insights, and quotes using LLM analysis
- Store in Neo4j knowledge graph with semantic relationships
- Query articles by topic, concept, or theme

## Quick Start

### 1. Install Dependencies

\`\`\`bash
pip install requests beautifulsoup4 feedparser neo4j lxml anthropic python-dotenv tqdm tenacity
\`\`\`

### 2. Configure Environment

\`\`\`bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"
export ANTHROPIC_API_KEY="your_key"
\`\`\`

### 3. Initialize Schema

\`\`\`bash
cd scripts/substack_learner
python init_schema.py
\`\`\`

### 4. Scrape Articles

\`\`\`bash
python substack_scraper.py https://hansamato.substack.com
\`\`\`

### 5. Analyze Content

\`\`\`bash
python analyze_content.py
\`\`\`

### 6. Import to Neo4j

\`\`\`bash
python import_to_neo4j.py
\`\`\`

### 7. Query

\`\`\`bash
python query_cli.py what "investing"
python query_cli.py insights "decision making"
\`\`\`

## Adding New Substack Sources

Simply run the scraper with the new URL:

\`\`\`bash
python substack_scraper.py https://newauthor.substack.com
\`\`\`

The system will automatically:
- Detect the author from article metadata
- Create new author node if needed
- Link articles to existing concepts where applicable

## Neo4j Schema Reference

### Nodes

- **Article**: Individual posts
  - Properties: url, title, published_date, word_count, summary

- **Author**: Content creators
  - Properties: name, bio, substack_url

- **Concept**: Ideas, frameworks, mental models
  - Properties: name, definition, category

- **Insight**: Actionable wisdom extracted from articles
  - Properties: id, text, type, applicability

- **Tag**: Topic labels
  - Properties: name

### Relationships

- `:ARTICLE_WRITTEN_BY` (Article)->Author
- `:ARTICLE_CONTAINS_CONCEPT` (Article)->Concept
- `:ARTICLE_PROVIDES_INSIGHT` (Article)->Insight
- `:ARTICLE_HAS_TAG` (Article)->Tag
- `:CONCEPT_RELATED_TO` (Concept)->Concept
```

### Task 4.2: Create Query Examples

Create `docs/substack_learner/query_examples.md`:

```markdown
# Query Examples

## Natural Language Queries

### "What did Hans say about compounding?"

\`\`\`cypher
MATCH (a:Article)-[:ARTICLE_WRITTEN_BY]->(au:Author {name: "Hans Amato"})
WHERE a.title CONTAINS "compound" OR a.summary CONTAINS "compound"
RETURN a.title, a.url, a.published_date
ORDER BY a.published_date DESC
\`\`\`

Or via CLI:
\`\`\`bash
python query_cli.py what compounding
\`\`\`

### "Show me all articles about mental models"

\`\`\`cypher
MATCH (c:Concept {name: "Mental Model"})<-[:ARTICLE_CONTAINS_CONCEPT]-(a:Article)
RETURN a.title, a.url
ORDER BY a.published_date DESC
\`\`\`

### "What are the key insights on decision making?"

\`\`\`bash
python query_cli.py insights "decision making"
\`\`\`

### "Find all concepts related to investing"

\`\`\`cypher
MATCH (c:Concept)-[:ARTICLE_CONTAINS_CONCEPT]-(a:Article)
WHERE a.title CONTAINS "invest" OR (a)-[:ARTICLE_HAS_TAG]->(:Tag {name: "investing"})
RETURN DISTINCT c.name, c.definition
\`\`\`

## Advanced Queries

### Find most interconnected concepts

\`\`\`cypher
MATCH (c:Concept)<-[r:ARTICLE_CONTAINS_CONCEPT]-(a:Article)
RETURN c.name, count(a) as article_count
ORDER BY article_count DESC
LIMIT 20
\`\`\`

### Trace concept evolution across author's work

\`\`\`cypher
MATCH path = (au:Author)-[:ARTICLE_WRITTEN_BY]->(a:Article)-[:ARTICLE_CONTAINS_CONCEPT]->(c:Concept {name: "Mental Model"})
RETURN a.title, a.published_date, c.name
ORDER BY a.published_date ASC
\`\`\`

### Get insights with source context

\`\`\`cypher
MATCH (i:Insight)<-[:ARTICLE_PROVIDES_INSIGHT]-(a:Article)
WHERE i.type = "actionable"
RETURN i.text, a.title as source, a.url
ORDER BY a.published_date DESC
LIMIT 50
\`\`\`
```

### Task 4.3: Create Troubleshooting Guide

Create `docs/substack_learner/troubleshooting.md`:

```markdown
# Troubleshooting

## Common Issues

### "No articles found in RSS feed"

**Cause**: RSS URL may be incorrect or feed may be empty.

**Solution**:
1. Verify the Substack URL format: `https://author.substack.com`
2. Check `https://author.substack.com/feed` directly in browser
3. Some Substacks may not have public RSS feeds

### "LLM analysis returns empty results"

**Cause**: ANTHROPIC_API_KEY not set or invalid.

**Solution**:
\`\`\`bash
export ANTHROPIC_API_KEY="sk-ant-..."
echo $ANTHROPIC_API_KEY  # Verify
\`\`\`

### "Neo4j connection refused"

**Cause**: Neo4j not running or wrong URI.

**Solution**:
\`\`\`bash
# Check Neo4j is running
ps aux | grep neo4j

# Test connection
cypher-shell -a bolt://localhost:7687 -u neo4j -p password
\`\`\`

### "Rate limiting errors from Substack"

**Cause**: Too many requests too quickly.

**Solution**: Increase rate_limit in scraper:
\`\`\`bash
python substack_scraper.py https://hansamato.substack.com --rate-limit 2.0
\`\`\`

## Debug Mode

Enable verbose logging:
\`\`\`bash
export DEBUG=1
python substack_scraper.py https://hansamato.substack.com
\`\`\`
```

### Exit Criteria Phase 4

- [ ] `docs/substack_learner/README.md` created
- [ ] `docs/substack_learner/query_examples.md` created
- [ ] `docs/substack_learner/troubleshooting.md` created
- [ ] README includes quick start guide
- [ ] Query examples cover all 4 required query types
- [ ] Troubleshooting covers common failure modes

---

## Appendix A: Hans Amato Substack Details

Target publication: https://hansamato.substack.com

Known themes:
- Mental models
- Decision making
- Learning systems
- Compounding (knowledge, skills, relationships)

Expected article count: 100+ (as of 2026-03)

---

## Appendix B: File Structure

```
scripts/substack_learner/
├── __init__.py
├── init_schema.py              # Neo4j schema initialization
├── rss_fetcher.py              # RSS feed parser
├── content_fetcher.py          # Full article HTML fetcher
├── substack_scraper.py         # Main scraper orchestrator
├── content_analyzer.py         # LLM content analysis
├── analyze_content.py          # Batch analysis runner
├── neo4j_store.py              # Neo4j storage layer
├── import_to_neo4j.py          # Import orchestrator
├── clear_data.py               # Data cleanup utility
├── query_cli.py                # CLI query interface
├── queries/
│   ├── 01_schema.cypher        # Schema definitions
│   └── query_interface.py      # Query module
├── data/
│   ├── articles.json           # Scraped articles
│   └── analyses.json           # LLM analyses
docs/substack_learner/
├── README.md                   # Main documentation
├── query_examples.md           # Query examples
└── troubleshooting.md          # Troubleshooting guide
```

---

## Success Criteria Verification

After completing all phases, verify:

- [ ] All Hans Amato articles downloaded (>50 articles in `data/articles.json`)
- [ ] Each article has full content (>200 words)
- [ ] LLM analysis completed for all articles (concepts, insights, quotes extracted)
- [ ] Neo4j contains all nodes: Articles, Concepts, Insights, Author, Tags
- [ ] Query interface responds to "What did Hans say about [topic]"
- [ ] Query interface responds to "Show articles about [concept]"
- [ ] Query interface responds to "Summarize insights on [theme]"
- [ ] Documentation complete and tested
- [ ] New Substack source can be added in <5 minutes
