#!/usr/bin/env python3
"""
Neo4j Research Storage - Continuous research tracking for the Kurultai

Schema:
- (:Research {researchId, topic, category, keywords, summary, content,
              sourceUrls, dateResearched, researchedBy, priority, status, tags})
- (:Source {url, title, author, publishedAt, domain})
- (:Content {contentId, slug, title, contentType, status})
- (:Agent {name})-[:EXECUTED]->(:Task)
- (:Research)-[:CITES]->(:Source)
- (:Research)-[:RELATED_TO]->(:Research)
- (:Research)-[:SUPPORTS]->(:Content)
- (:Research)-[:CREATED_BY]->(:Agent)

Usage:
    from research_storage import ResearchStorage

    storage = ResearchStorage()

    # Store research
    research_id = storage.create_research(
        topic="Neo4j index optimization",
        category="performance",
        keywords=["neo4j", "index", "query"],
        summary="Analysis of indexing strategies",
        content="# Full content...",
        source_urls=["https://neo4j.com/docs/..."],
        researched_by="temujin",
        priority="high",
        tags=["database", "graph"]
    )

    # Search research
    results = storage.search_by_keyword("index optimization")

    # Find related research
    related = storage.find_related_research(research_id)

    storage.close()
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import shared connection factory
from neo4j_task_tracker import get_driver as get_neo4j_driver, close_driver


# Valid categories for research
VALID_CATEGORIES = ["security", "performance", "ops", "dev", "content", "architecture", "other"]
VALID_PRIORITIES = ["high", "normal", "low"]
VALID_STATUSES = ["active", "archived"]


class ResearchStorage:
    """Neo4j-backed research storage with full CRUD and search capabilities."""

    def __init__(self):
        self.driver = get_neo4j_driver()

    def close(self):
        """Close the database connection."""
        close_driver()
        self.driver = None

    # =========================================================================
    # CREATE Operations
    # =========================================================================

    def create_research(
        self,
        topic: str,
        category: str,
        keywords: List[str],
        summary: str,
        content: str,
        researched_by: str,
        priority: str = "normal",
        source_urls: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        date_researched: Optional[datetime] = None
    ) -> str:
        """
        Create a new research item.

        Args:
            topic: Primary research subject
            category: One of security, performance, ops, dev, content, architecture, other
            keywords: List of searchable terms
            summary: 2-3 sentence summary
            content: Full research content (markdown-supported)
            researched_by: Agent name who conducted the research
            priority: high, normal, or low
            source_urls: Optional list of source URLs
            tags: Optional flexible tags
            date_researched: When research was conducted (default: now)

        Returns:
            research_id: The UUID of the created research item
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}. Must be one of {VALID_PRIORITIES}")

        research_id = f"res-{uuid.uuid4().hex[:12]}"
        now = datetime.now()

        with self.driver.session() as session:
            # Create research node
            session.run("""
                CREATE (r:Research {
                    researchId: $researchId,
                    topic: $topic,
                    category: $category,
                    keywords: $keywords,
                    summary: $summary,
                    content: $content,
                    sourceUrls: $sourceUrls,
                    dateResearched: $dateResearched,
                    researchedBy: $researchedBy,
                    priority: $priority,
                    status: 'active',
                    tags: $tags,
                    createdAt: $createdAt,
                    updatedAt: $updatedAt
                })
            """,
            researchId=research_id,
            topic=topic,
            category=category,
            keywords=keywords or [],
            summary=summary,
            content=content,
            sourceUrls=source_urls or [],
            dateResearched=date_researched or now,
            researchedBy=researched_by,
            priority=priority,
            tags=tags or [],
            createdAt=now,
            updatedAt=now)

            # Link to agent
            session.run("""
                MATCH (r:Research {researchId: $researchId})
                MERGE (a:Agent {name: $researchedBy})
                CREATE (r)-[:CREATED_BY {createdAt: datetime()}]->(a)
            """, researchId=research_id, researchedBy=researched_by)

            # Create source nodes if URLs provided
            if source_urls:
                for url in source_urls:
                    domain = url.split("://")[1].split("/")[0] if "://" in url else url.split("/")[0]
                    session.run("""
                        MATCH (r:Research {researchId: $researchId})
                        MERGE (s:Source {url: $url})
                        ON CREATE SET
                            s.domain = $domain,
                            s.accessedAt = datetime()
                        CREATE (r)-[:CITES {citedAt: datetime()}]->(s)
                    """, researchId=research_id, url=url, domain=domain)

        return research_id

    def create_source(
        self,
        url: str,
        title: str,
        author: Optional[str] = None,
        published_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create or get a source node."""
        with self.driver.session() as session:
            session.run("""
                MERGE (s:Source {url: $url})
                ON CREATE SET
                    s.title = $title,
                    s.author = $author,
                    s.publishedAt = $publishedAt,
                    s.accessedAt = datetime(),
                    s.metadata = $metadata
                ON MATCH SET
                    s.title = coalesce(s.title, $title),
                    s.accessedAt = datetime()
            """,
            url=url,
            title=title,
            author=author,
            publishedAt=published_at,
            metadata=json.dumps(metadata) if metadata else None)
        return url

    def create_content(
        self,
        title: str,
        slug: str,
        content_type: str,
        status: str = "draft"
    ) -> str:
        """Create a content node (blog post, doc, report)."""
        content_id = f"cnt-{uuid.uuid4().hex[:12]}"

        with self.driver.session() as session:
            session.run("""
                CREATE (c:Content {
                    contentId: $contentId,
                    slug: $slug,
                    title: $title,
                    contentType: $contentType,
                    status: $status,
                    createdAt: datetime(),
                    updatedAt: datetime()
                })
            """,
            contentId=content_id,
            slug=slug,
            title=title,
            contentType=content_type,
            status=status)

        return content_id

    # =========================================================================
    # READ Operations
    # =========================================================================

    def get_research(self, research_id: str) -> Optional[Dict[str, Any]]:
        """Get a research item by ID with sources and agent."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research {researchId: $researchId})
                OPTIONAL MATCH (r)-[:CITES]->(s:Source)
                OPTIONAL MATCH (r)-[:CREATED_BY]->(a:Agent)
                OPTIONAL MATCH (r)-[:RELATED_TO]->(related:Research)
                RETURN r,
                       collect(DISTINCT s) AS sources,
                       a,
                       collect(DISTINCT related) AS related_research
            """, researchId=research_id)

            record = result.single()
            if not record:
                return None

            research = dict(record['r'])
            research['sources'] = [dict(s) for s in record['sources']]
            research['agent'] = dict(record['a']) if record['a'] else None
            research['related'] = [dict(r) for r in record['related_research']]

            return research

    def search_by_keyword(
        self,
        query: str,
        category: Optional[str] = None,
        status: str = "active",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search research by keyword using fulltext index.

        Args:
            query: Search terms (supports boolean operators)
            category: Optional category filter
            status: Filter by status (default: active)
            limit: Max results

        Returns:
            List of research items with scores
        """
        with self.driver.session() as session:
            if category:
                result = session.run("""
                    CALL db.index.fulltext.queryNodes("research_search", $searchQuery)
                    YIELD node AS r, score
                    WHERE r.category = $category AND r.status = $status
                    RETURN r, score
                    ORDER BY score DESC
                    LIMIT $limit
                """, searchQuery=query, category=category, status=status, limit=limit)
            else:
                result = session.run("""
                    CALL db.index.fulltext.queryNodes("research_search", $searchQuery)
                    YIELD node AS r, score
                    WHERE r.status = $status
                    RETURN r, score
                    ORDER BY score DESC
                    LIMIT $limit
                """, searchQuery=query, status=status, limit=limit)

            return [dict(r['r']) for r in result]

    def search_by_topic(self, topic: str, status: str = "active") -> List[Dict[str, Any]]:
        """Find research by exact topic match."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research {topic: $topic})
                WHERE r.status = $status
                RETURN r ORDER BY r.dateResearched DESC
            """, topic=topic, status=status)
            return [dict(r['r']) for r in result]

    def search_by_category(
        self,
        category: str,
        priority: Optional[str] = None,
        status: str = "active",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Find research by category, optionally filtered by priority."""
        with self.driver.session() as session:
            if priority:
                result = session.run("""
                    MATCH (r:Research)
                    WHERE r.category = $category
                      AND r.priority = $priority
                      AND r.status = $status
                    RETURN r ORDER BY r.dateResearched DESC LIMIT $limit
                """, category=category, priority=priority, status=status, limit=limit)
            else:
                result = session.run("""
                    MATCH (r:Research)
                    WHERE r.category = $category AND r.status = $status
                    RETURN r ORDER BY r.priority DESC, r.dateResearched DESC LIMIT $limit
                """, category=category, status=status, limit=limit)
            return [dict(r['r']) for r in result]

    def search_by_tag(self, tag: str, status: str = "active") -> List[Dict[str, Any]]:
        """Find research by tag."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research)
                WHERE $tag IN r.tags AND r.status = $status
                RETURN r ORDER BY r.dateResearched DESC
            """, tag=tag, status=status)
            return [dict(r['r']) for r in result]

    def search_by_date_range(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        category: Optional[str] = None,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """Find research within a date range."""
        with self.driver.session() as session:
            if category:
                result = session.run("""
                    MATCH (r:Research)
                    WHERE r.dateResearched >= $startDate
                      AND r.status = $status
                      AND ($endDate IS NULL OR r.dateResearched <= $endDate)
                      AND r.category = $category
                    RETURN r ORDER BY r.dateResearched DESC
                """, startDate=start_date, endDate=end_date, category=category, status=status)
            else:
                result = session.run("""
                    MATCH (r:Research)
                    WHERE r.dateResearched >= $startDate
                      AND r.status = $status
                      AND ($endDate IS NULL OR r.dateResearched <= $endDate)
                    RETURN r ORDER BY r.dateResearched DESC
                """, startDate=start_date, endDate=end_date, status=status)
            return [dict(r['r']) for r in result]

    def search_by_agent(
        self,
        agent_name: str,
        status: str = "active",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Find research conducted by a specific agent."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research {researchedBy: $agentName})
                WHERE r.status = $status
                RETURN r ORDER BY r.dateResearched DESC LIMIT $limit
            """, agentName=agent_name, status=status, limit=limit)
            return [dict(r['r']) for r in result]

    def find_related_research(
        self,
        research_id: str,
        max_depth: int = 2
    ) -> List[Dict[str, Any]]:
        """Find research related to a given item."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research {researchId: $researchId})
                OPTIONAL MATCH (r)-[:RELATED_TO]->(related)
                OPTIONAL MATCH (r)<-[:RELATED_TO]-(related_back)
                WITH r, collect(DISTINCT related) + collect(DISTINCT related_back) AS all_related
                UNWIND all_related AS related_node
                WHERE related_node IS NOT NULL AND related_node <> r
                RETURN DISTINCT related_node AS related
                ORDER BY related_node.dateResearched DESC
                LIMIT $maxDepth
            """, researchId=research_id, maxDepth=max_depth * 10)
            return [dict(r['related']) for r in result]

    def find_research_for_content(self, content_slug: str) -> List[Dict[str, Any]]:
        """Find all research that supports a piece of content."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research)-[:SUPPORTS]->(c:Content {slug: $slug})
                RETURN r ORDER BY r.dateResearched DESC
            """, slug=content_slug)
            return [dict(r['r']) for r in result]

    def get_recent_research(
        self,
        category: Optional[str] = None,
        limit: int = 20,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """Get most recent research items."""
        with self.driver.session() as session:
            if category:
                result = session.run("""
                    MATCH (r:Research)
                    WHERE r.category = $category AND r.status = $status
                    RETURN r ORDER BY r.dateResearched DESC LIMIT $limit
                """, category=category, status=status, limit=limit)
            else:
                result = session.run("""
                    MATCH (r:Research)
                    WHERE r.status = $status
                    RETURN r ORDER BY r.dateResearched DESC LIMIT $limit
                """, status=status, limit=limit)
            return [dict(r['r']) for r in result]

    def count_research_by_category(
        self,
        status: str = "active"
    ) -> Dict[str, int]:
        """Get count of research items per category."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research)
                WHERE r.status = $status
                RETURN r.category AS category, count(r) AS count
                ORDER BY count DESC
            """, status=status)
            return {r['category']: r['count'] for r in result}

    def find_orphaned_research(self, status: str = "active") -> List[Dict[str, Any]]:
        """Find research with no relationships (no sources, no related items)."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research)
                WHERE r.status = $status
                  AND NOT EXISTS { (r)-[]-() }
                RETURN r ORDER BY r.dateResearched DESC
            """, status=status)
            return [dict(r['r']) for r in result]

    # =========================================================================
    # UPDATE Operations
    # =========================================================================

    def update_research(
        self,
        research_id: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Update research fields dynamically.

        Args:
            research_id: ID of research to update
            **kwargs: Fields to update (topic, summary, content, keywords, tags, priority)

        Returns:
            Updated research item or None if not found
        """
        allowed_fields = {'topic', 'summary', 'content', 'keywords', 'tags', 'priority', 'status'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return self.get_research(research_id)

        with self.driver.session() as session:
            # Build dynamic SET clause
            set_clauses = []
            params = {'researchId': research_id}

            for field, value in updates.items():
                set_clauses.append(f"r.{field} = ${field}")
                params[field] = value

            set_clauses.append("r.updatedAt = datetime()")

            result = session.run(f"""
                MATCH (r:Research {{researchId: $researchId}})
                SET {', '.join(set_clauses)}
                RETURN r
            """, **params)

            record = result.single()
            return dict(record['r']) if record else None

    def add_related_research(
        self,
        from_research_id: str,
        to_research_id: str,
        relationship_type: str = "supplements",
        relevance_score: float = 0.5
    ) -> bool:
        """Create a RELATED_TO relationship between two research items."""
        with self.driver.session() as session:
            session.run("""
                MATCH (r1:Research {researchId: $fromId})
                MATCH (r2:Research {researchId: $toId})
                MERGE (r1)-[rel:RELATED_TO]->(r2)
                SET rel.relationshipType = $relationshipType,
                    rel.relevanceScore = $relevanceScore,
                    rel.relatedAt = datetime()
            """,
            fromId=from_research_id,
            toId=to_research_id,
            relationshipType=relationship_type,
            relevanceScore=relevance_score)
        return True

    def link_research_to_content(
        self,
        research_id: str,
        content_slug: str,
        support_level: str = "reference"
    ) -> bool:
        """Link research to content it supports."""
        with self.driver.session() as session:
            session.run("""
                MATCH (r:Research {researchId: $researchId})
                MATCH (c:Content {slug: $slug})
                MERGE (r)-[:SUPPORTS {supportLevel: $level}]
                    ->(c)
                ON CREATE SET r.supportedAt = datetime()
            """,
            researchId=research_id,
            slug=content_slug,
            level=support_level)
        return True

    # =========================================================================
    # DELETE Operations
    # =========================================================================

    def archive_research(self, research_id: str) -> Optional[Dict[str, Any]]:
        """Soft delete by archiving."""
        return self.update_research(research_id, status="archived")

    def delete_research(self, research_id: str) -> int:
        """Hard delete research and its relationships."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research {researchId: $researchId})
                DETACH DELETE r
                RETURN count(r) AS deleted
            """, researchId=research_id)
            record = result.single()
            return record['deleted'] if record else 0

    def archive_old_research(
        self,
        older_than_days: int = 90
    ) -> int:
        """Archive research older than specified days."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Research)
                WHERE r.dateResearched < datetime() - duration({days: $days})
                  AND r.status = 'active'
                SET r.status = 'archived', r.updatedAt = datetime()
                RETURN count(r) AS archived
            """, days=older_than_days)
            record = result.single()
            return record['archived'] if record else 0

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get research storage statistics."""
        with self.driver.session() as session:
            total = session.run("MATCH (r:Research) RETURN count(r) AS count").single()['count']
            active = session.run("MATCH (r:Research WHERE r.status = 'active') RETURN count(r) AS count").single()['count']
            archived = session.run("MATCH (r:Research WHERE r.status = 'archived') RETURN count(r) AS count").single()['count']

            categories = session.run("""
                MATCH (r:Research)
                WHERE r.status = 'active'
                RETURN r.category AS category, count(r) AS count
                ORDER BY count DESC
            """)

            agents = session.run("""
                MATCH (r:Research)
                WHERE r.status = 'active'
                RETURN r.researchedBy AS agent, count(r) AS count
                ORDER BY count DESC
            """)

            return {
                'total': total,
                'active': active,
                'archived': archived,
                'by_category': {r['category']: r['count'] for r in categories},
                'by_agent': {r['agent']: r['count'] for r in agents}
            }

    def natural_language_search(
        self,
        query: str,
        llm_extracted_terms: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search using natural language with LLM-extracted terms.

        This method is designed to be called after an LLM processes a natural
        language query and extracts search terms and categories.

        Args:
            query: Original natural language query
            llm_extracted_terms: Keywords extracted by LLM
            categories: Category filters from LLM
            limit: Max results

        Returns:
            Matching research items
        """
        search_terms = llm_extracted_terms or [query]
        search_query = " OR ".join(search_terms)

        with self.driver.session() as session:
            if categories:
                result = session.run("""
                    CALL db.index.fulltext.queryNodes("research_search", $searchQuery)
                    YIELD node AS r, score
                    WHERE r.status = 'active'
                      AND r.category IN $categories
                    RETURN r, score
                    ORDER BY score DESC
                    LIMIT $limit
                """, searchQuery=search_query, categories=categories, limit=limit)
            else:
                result = session.run("""
                    CALL db.index.fulltext.queryNodes("research_search", $searchQuery)
                    YIELD node AS r, score
                    WHERE r.status = 'active'
                    RETURN r, score
                    ORDER BY score DESC
                    LIMIT $limit
                """, searchQuery=search_query, limit=limit)

            return [dict(r['r']) for r in result]


# Singleton instance
_storage = None

def get_storage():
    """Get or create storage instance."""
    global _storage
    if _storage is None:
        _storage = ResearchStorage()
    return _storage


if __name__ == "__main__":
    # Test
    storage = get_storage()
    print("Neo4j Research Storage initialized")
    print("Stats:", storage.get_stats())
    storage.close()
