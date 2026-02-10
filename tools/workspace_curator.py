#!/usr/bin/env python3
"""
Intelligent Workspace Curation - Kurultai v2.0

AI-powered workspace management:
- Auto-name untitled pages with contextual AI
- Suggest page consolidations
- Auto-archive inactive content
- Content quality scoring

Author: Kurultai v2.0
Date: 2026-02-10
"""

import os
import sys
import json
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@dataclass
class PageAnalysis:
    """Analysis of a workspace page/document."""
    path: str
    title: Optional[str] = None
    content_preview: str = ""
    word_count: int = 0
    created_at: Optional[datetime] = None
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    quality_score: float = 0.0
    suggested_title: Optional[str] = None
    suggested_action: Optional[str] = None
    related_pages: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)


@dataclass
class ConsolidationSuggestion:
    """Suggestion for consolidating multiple pages."""
    pages: List[str]
    reason: str
    suggested_title: str
    estimated_savings: int  # character count
    confidence: float


class WorkspaceCurator:
    """
    Intelligent workspace curation with AI-powered suggestions.
    
    Features:
    - Auto-generate meaningful titles for untitled content
    - Detect and suggest page consolidations
    - Auto-archive stale content
    - Content quality analysis
    """
    
    def __init__(self, driver, workspace_path: str = "/data/workspace/souls"):
        self.driver = driver
        self.workspace_path = Path(workspace_path)
        
        # Configuration
        self.archive_threshold_days = 90
        self.consolidation_similarity_threshold = 0.7
        self.min_content_length = 100
        self.untitled_patterns = [
            r'^untitled',
            r'^draft[_\-]?\d*',
            r'^new[_\-]?document',
            r'^page[_\-]?\d+',
            r'^temp[_\-]?',
            r'^note[_\-]?\d*',
            r'^doc[_\-]?\d*',
        ]
    
    def is_untitled(self, title: str) -> bool:
        """Check if a title matches untitled patterns."""
        title_lower = title.lower()
        for pattern in self.untitled_patterns:
            if re.match(pattern, title_lower):
                return True
        return False
    
    def analyze_content(self, content: str) -> Dict[str, Any]:
        """Analyze content to extract topics and generate title suggestions."""
        analysis = {
            "word_count": len(content.split()),
            "topics": [],
            "key_phrases": [],
            "suggested_title": None,
            "quality_score": 0.0
        }
        
        # Extract potential topics from headers
        headers = re.findall(r'^#+\s*(.+)$', content, re.MULTILINE)
        analysis["key_phrases"] = headers[:5]
        
        # Extract topics from common keywords
        topic_keywords = {
            "architecture": ["architecture", "design", "system", "component"],
            "api": ["api", "endpoint", "request", "response", "rest"],
            "database": ["database", "neo4j", "sql", "query", "schema"],
            "security": ["security", "auth", "authentication", "encryption"],
            "deployment": ["deploy", "deployment", "kubernetes", "docker", "infrastructure"],
            "testing": ["test", "testing", "pytest", "unit test", "integration"],
            "documentation": ["doc", "documentation", "readme", "guide"],
            "research": ["research", "analysis", "study", "investigation"],
            "planning": ["plan", "roadmap", "milestone", "schedule"],
            "bugfix": ["bug", "fix", "issue", "error", "problem"],
        }
        
        content_lower = content.lower()
        for topic, keywords in topic_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                analysis["topics"].append({"topic": topic, "score": score})
        
        # Sort by score
        analysis["topics"].sort(key=lambda x: x["score"], reverse=True)
        analysis["topics"] = analysis["topics"][:5]
        
        # Generate suggested title
        if analysis["key_phrases"]:
            # Use first header as base
            base_title = analysis["key_phrases"][0]
            # Clean up
            base_title = re.sub(r'[^\w\s\-]', '', base_title).strip()
            if len(base_title) > 5:
                analysis["suggested_title"] = base_title[:80]
        
        # If no header, use top topic + summary
        if not analysis["suggested_title"] and analysis["topics"]:
            top_topic = analysis["topics"][0]["topic"]
            # Extract first sentence
            sentences = re.split(r'[.!?]+', content)
            if sentences:
                first_sentence = sentences[0].strip()[:50]
                analysis["suggested_title"] = f"{top_topic.title()}: {first_sentence}..."
        
        # Calculate quality score
        quality = 0.0
        if analysis["word_count"] > 500:
            quality += 0.3
        if analysis["word_count"] > 1000:
            quality += 0.2
        if len(analysis["topics"]) >= 2:
            quality += 0.2
        if len(analysis["key_phrases"]) >= 2:
            quality += 0.2
        if analysis["suggested_title"]:
            quality += 0.1
        
        analysis["quality_score"] = round(min(1.0, quality), 2)
        
        return analysis
    
    def scan_workspace_files(self) -> List[PageAnalysis]:
        """Scan workspace for pages to analyze."""
        pages = []
        
        # Scan markdown files
        for md_file in self.workspace_path.rglob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8', errors='ignore')
                
                # Extract title from first header or filename
                title_match = re.search(r'^#\s*(.+)$', content, re.MULTILINE)
                title = title_match.group(1) if title_match else md_file.stem
                
                # Check if untitled
                is_untitled = self.is_untitled(title) or self.is_untitled(md_file.stem)
                
                analysis = self.analyze_content(content)
                
                page = PageAnalysis(
                    path=str(md_file.relative_to(self.workspace_path)),
                    title=title if not is_untitled else None,
                    content_preview=content[:500],
                    word_count=analysis["word_count"],
                    suggested_title=analysis["suggested_title"] if is_untitled else None,
                    topics=[t["topic"] for t in analysis["topics"]],
                    quality_score=analysis["quality_score"]
                )
                
                # Get metadata from Neo4j if available
                with self.driver.session() as session:
                    result = session.run('''
                        MATCH (n {file_path: $path})
                        RETURN n.created_at as created,
                               n.last_accessed as accessed,
                               n.access_count as count
                    ''', path=str(md_file))
                    
                    record = result.single()
                    if record:
                        page.created_at = record['created']
                        page.last_accessed = record['accessed']
                        page.access_count = record['count'] or 0
                
                pages.append(page)
                
            except Exception as e:
                print(f"Error reading {md_file}: {e}")
        
        return pages
    
    def find_untitled_pages(self, pages: Optional[List[PageAnalysis]] = None) -> List[PageAnalysis]:
        """Find pages that need title suggestions."""
        if pages is None:
            pages = self.scan_workspace_files()
        
        return [p for p in pages if p.title is None or self.is_untitled(p.title)]
    
    def find_consolidation_opportunities(self, pages: Optional[List[PageAnalysis]] = None) -> List[ConsolidationSuggestion]:
        """Find pages that could be consolidated."""
        if pages is None:
            pages = self.scan_workspace_files()
        
        suggestions = []
        
        # Group by topic
        topic_groups: Dict[str, List[PageAnalysis]] = {}
        for page in pages:
            for topic in page.topics:
                if topic not in topic_groups:
                    topic_groups[topic] = []
                topic_groups[topic].append(page)
        
        # Find groups with multiple small pages
        for topic, group in topic_groups.items():
            if len(group) >= 3:
                # Check if pages are small enough to consolidate
                total_words = sum(p.word_count for p in group)
                avg_quality = sum(p.quality_score for p in group) / len(group)
                
                if total_words < 5000 and avg_quality < 0.5:
                    suggestion = ConsolidationSuggestion(
                        pages=[p.path for p in group],
                        reason=f"Multiple small pages on '{topic}' topic with low individual quality",
                        suggested_title=f"{topic.title()} - Consolidated Documentation",
                        estimated_savings=sum(len(p.content_preview) for p in group) * 0.3,
                        confidence=0.7
                    )
                    suggestions.append(suggestion)
        
        # Find duplicate/similar titles
        title_groups: Dict[str, List[PageAnalysis]] = {}
        for page in pages:
            if page.title:
                key = page.title.lower()[:30]
                if key not in title_groups:
                    title_groups[key] = []
                title_groups[key].append(page)
        
        for key, group in title_groups.items():
            if len(group) >= 2:
                suggestion = ConsolidationSuggestion(
                    pages=[p.path for p in group],
                    reason=f"Similar/duplicate titles detected",
                    suggested_title=group[0].title or "Consolidated Content",
                    estimated_savings=sum(len(p.content_preview) for p in group) * 0.5,
                    confidence=0.8
                )
                suggestions.append(suggestion)
        
        return suggestions
    
    def find_archive_candidates(self, pages: Optional[List[PageAnalysis]] = None) -> List[PageAnalysis]:
        """Find pages that should be archived due to inactivity."""
        if pages is None:
            pages = self.scan_workspace_files()
        
        cutoff = datetime.now() - timedelta(days=self.archive_threshold_days)
        
        candidates = []
        for page in pages:
            # Archive if:
            # 1. Not accessed in 90 days
            # 2. Low access count
            # 3. Low quality score
            should_archive = False
            reason = []
            
            if page.last_accessed and page.last_accessed < cutoff:
                should_archive = True
                reason.append(f"not accessed since {page.last_accessed.date()}")
            
            if page.access_count < 2 and page.quality_score < 0.3:
                should_archive = True
                reason.append("low engagement and quality")
            
            if should_archive:
                page.suggested_action = f"Archive: {', '.join(reason)}"
                candidates.append(page)
        
        return candidates
    
    def apply_title_suggestion(self, page_path: str, new_title: str) -> bool:
        """Apply a suggested title to a page."""
        try:
            full_path = self.workspace_path / page_path
            content = full_path.read_text(encoding='utf-8')
            
            # Check if first line is a header
            lines = content.split('\n')
            if lines and lines[0].startswith('#'):
                # Replace existing header
                lines[0] = f"# {new_title}"
            else:
                # Add new header at top
                lines.insert(0, f"# {new_title}\n")
            
            full_path.write_text('\n'.join(lines), encoding='utf-8')
            
            # Update Neo4j
            with self.driver.session() as session:
                session.run('''
                    MATCH (n {file_path: $path})
                    SET n.title = $title,
                        n.auto_titled = true,
                        n.titled_at = datetime()
                ''', path=page_path, title=new_title)
            
            return True
        except Exception as e:
            print(f"Error applying title: {e}")
            return False
    
    def archive_page(self, page_path: str) -> bool:
        """Archive a page by moving to archive directory."""
        try:
            source = self.workspace_path / page_path
            archive_dir = self.workspace_path / "archive"
            archive_dir.mkdir(exist_ok=True)
            
            # Create dated subdirectory
            date_dir = archive_dir / datetime.now().strftime("%Y-%m")
            date_dir.mkdir(exist_ok=True)
            
            dest = date_dir / source.name
            
            # Move file
            source.rename(dest)
            
            # Update Neo4j
            with self.driver.session() as session:
                session.run('''
                    MATCH (n {file_path: $old_path})
                    SET n.archived = true,
                        n.file_path = $new_path,
                        n.archived_at = datetime()
                ''', old_path=page_path, new_path=str(dest.relative_to(self.workspace_path)))
            
            return True
        except Exception as e:
            print(f"Error archiving: {e}")
            return False
    
    def run_curation_cycle(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Run a full curation cycle.
        
        Returns actions taken or suggested.
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "mode": "dry_run" if dry_run else "applied",
            "untitled_pages": [],
            "consolidation_suggestions": [],
            "archive_candidates": [],
            "actions_taken": []
        }
        
        # Scan workspace
        pages = self.scan_workspace_files()
        
        # Find untitled pages
        untitled = self.find_untitled_pages(pages)
        for page in untitled:
            suggestion = {
                "path": page.path,
                "current": page.title or "(none)",
                "suggested": page.suggested_title,
                "confidence": page.quality_score
            }
            results["untitled_pages"].append(suggestion)
            
            if not dry_run and page.suggested_title:
                if self.apply_title_suggestion(page.path, page.suggested_title):
                    results["actions_taken"].append(f"Applied title '{page.suggested_title}' to {page.path}")
        
        # Find consolidation opportunities
        consolidations = self.find_consolidation_opportunities(pages)
        for suggestion in consolidations:
            results["consolidation_suggestions"].append({
                "pages": suggestion.pages,
                "reason": suggestion.reason,
                "suggested_title": suggestion.suggested_title,
                "confidence": suggestion.confidence
            })
        
        # Find archive candidates
        archive_candidates = self.find_archive_candidates(pages)
        for page in archive_candidates:
            candidate = {
                "path": page.path,
                "title": page.title,
                "last_accessed": page.last_accessed.isoformat() if page.last_accessed else None,
                "access_count": page.access_count,
                "reason": page.suggested_action
            }
            results["archive_candidates"].append(candidate)
            
            if not dry_run:
                if self.archive_page(page.path):
                    results["actions_taken"].append(f"Archived {page.path}")
        
        # Persist curation log
        self._persist_curation_log(results)
        
        return results
    
    def _persist_curation_log(self, results: Dict[str, Any]) -> None:
        """Persist curation results to Neo4j."""
        try:
            with self.driver.session() as session:
                session.run('''
                    CREATE (c:CurationCycle {
                        timestamp: datetime($timestamp),
                        mode: $mode,
                        untitled_count: $untitled,
                        consolidation_count: $consolidations,
                        archive_count: $archives,
                        actions_taken: $actions
                    })
                ''',
                    timestamp=results["timestamp"],
                    mode=results["mode"],
                    untitled=len(results["untitled_pages"]),
                    consolidations=len(results["consolidation_suggestions"]),
                    archives=len(results["archive_candidates"]),
                    actions=json.dumps(results["actions_taken"])
                )
        except Exception:
            pass
    
    def get_curation_stats(self) -> Dict[str, Any]:
        """Get statistics about workspace curation."""
        with self.driver.session() as session:
            # Count auto-titled pages
            result = session.run('''
                MATCH (n)
                WHERE n.auto_titled = true
                RETURN count(n) as auto_titled
            ''')
            auto_titled = result.single()['auto_titled']
            
            # Count archived pages
            result = session.run('''
                MATCH (n)
                WHERE n.archived = true
                RETURN count(n) as archived
            ''')
            archived = result.single()['archived']
            
            # Count curation cycles
            result = session.run('''
                MATCH (c:CurationCycle)
                RETURN count(c) as cycles
            ''')
            cycles = result.single()['cycles']
        
        return {
            "pages_auto_titled": auto_titled,
            "pages_archived": archived,
            "curation_cycles": cycles
        }


# Global instance
_curator: Optional[WorkspaceCurator] = None


def get_workspace_curator(driver) -> WorkspaceCurator:
    """Get or create global workspace curator instance."""
    global _curator
    if _curator is None:
        _curator = WorkspaceCurator(driver)
    return _curator


def reset_workspace_curator():
    """Reset global instance (for testing)."""
    global _curator
    _curator = None


# Standalone execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Workspace Curator")
    parser.add_argument("--scan", action="store_true", help="Scan workspace")
    parser.add_argument("--apply", action="store_true", help="Apply curation actions")
    parser.add_argument("--stats", action="store_true", help="Show curation statistics")
    
    args = parser.parse_args()
    
    from neo4j import GraphDatabase
    
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    
    if not password:
        print("NEO4J_PASSWORD not set")
        sys.exit(1)
    
    driver = GraphDatabase.driver(uri, auth=('neo4j', password))
    curator = get_workspace_curator(driver)
    
    if args.scan:
        results = curator.run_curation_cycle(dry_run=True)
        print(json.dumps(results, indent=2, default=str))
    elif args.apply:
        results = curator.run_curation_cycle(dry_run=False)
        print(json.dumps(results, indent=2, default=str))
    elif args.stats:
        print(json.dumps(curator.get_curation_stats(), indent=2))
    else:
        parser.print_help()
    
    driver.close()
