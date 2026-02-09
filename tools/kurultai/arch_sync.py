"""
ARCHITECTURE.md Bidirectional Sync Tool

Synchronizes between ARCHITECTURE.md file and ArchitectureSection nodes in Neo4j.
Ensures file changes update Neo4j and Neo4j proposals can sync to file.
Includes guardrails to prevent unauthorized changes.

Author: Chagatai (Writer Agent)
Date: 2026-02-09
"""

import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import logging

from neo4j import GraphDatabase


logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    """Direction of sync operation."""
    FILE_TO_NEO4J = "file_to_neo4j"
    NEO4J_TO_FILE = "neo4j_to_file"
    BIDIRECTIONAL = "bidirectional"


class ChangeType(Enum):
    """Type of change detected."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


@dataclass
class ArchitectureSection:
    """Represents an architecture section."""
    id: str
    title: str
    category: str
    section_order: int
    content: str
    content_summary: str
    version: str
    last_updated: datetime
    source: str  # 'file' or 'neo4j'
    hash: str = ""
    proposal: bool = False
    proposal_author: Optional[str] = None
    proposal_approved: bool = False
    
    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute content hash for change detection."""
        content = f"{self.title}:{self.category}:{self.content}:{self.version}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'category': self.category,
            'section_order': self.section_order,
            'content_summary': self.content_summary,
            'version': self.version,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'hash': self.hash,
            'proposal': self.proposal,
            'proposal_author': self.proposal_author,
            'proposal_approved': self.proposal_approved,
        }


@dataclass
class SyncConflict:
    """Represents a sync conflict."""
    section_title: str
    file_version: Optional[ArchitectureSection]
    neo4j_version: Optional[ArchitectureSection]
    conflict_type: str  # 'both_modified', 'file_deleted_neo4j_modified', etc.
    resolution: Optional[str] = None


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    direction: SyncDirection
    sections_synced: int = 0
    conflicts: List[SyncConflict] = field(default_factory=list)
    changes: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    error_message: Optional[str] = None


class ArchitectureSync:
    """
    Bidirectional sync between ARCHITECTURE.md and Neo4j ArchitectureSection nodes.
    
    Key features:
    - Parse ARCHITECTURE.md into sections
    - Sync to/from Neo4j
    - Handle conflicts with configurable resolution
    - Guardrails for unauthorized changes
    """
    
    # Known authorized authors for proposals
    AUTHORIZED_AUTHORS = {'kublai', 'chagatai', 'temujin', 'system'}
    
    def __init__(self, 
                 architecture_file_path: Optional[str] = None,
                 neo4j_uri: Optional[str] = None,
                 neo4j_user: str = "neo4j",
                 neo4j_password: Optional[str] = None,
                 require_approval_for_proposals: bool = True):
        """
        Initialize ArchitectureSync.
        
        Args:
            architecture_file_path: Path to ARCHITECTURE.md
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            require_approval_for_proposals: Whether Neo4j proposals need approval
        """
        self.architecture_file_path = architecture_file_path or os.environ.get(
            'ARCHITECTURE_FILE_PATH',
            '/data/workspace/souls/main/ARCHITECTURE.md'
        )
        self.neo4j_uri = neo4j_uri or os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password or os.environ.get('NEO4J_PASSWORD')
        
        self.require_approval_for_proposals = require_approval_for_proposals
        
        self._driver = None
        self._sections_cache: Dict[str, ArchitectureSection] = {}
    
    def _get_driver(self) -> GraphDatabase.driver:
        """Get or create Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
        return self._driver
    
    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
    
    def parse_architecture_file(self) -> List[ArchitectureSection]:
        """
        Parse ARCHITECTURE.md into sections.
        
        Returns:
            List of ArchitectureSection objects
        """
        if not os.path.exists(self.architecture_file_path):
            raise FileNotFoundError(f"Architecture file not found: {self.architecture_file_path}")
        
        with open(self.architecture_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        sections = []
        section_order = 0
        
        # Parse YAML frontmatter if present
        frontmatter = self._parse_frontmatter(content)
        version = frontmatter.get('version', '1.0')
        
        # Split into sections (## headers)
        # Pattern: ## Section Title
        section_pattern = r'^##\s+(.+?)\n(.*?)(?=^##\s+|\Z)'
        matches = re.findall(section_pattern, content, re.MULTILINE | re.DOTALL)
        
        for title, section_content in matches:
            section_order += 1
            
            # Determine category from title or content
            category = self._determine_category(title, section_content)
            
            # Generate summary
            summary = self._generate_summary(section_content)
            
            section = ArchitectureSection(
                id=str(uuid.uuid4()),
                title=title.strip(),
                category=category,
                section_order=section_order,
                content=section_content.strip(),
                content_summary=summary,
                version=version,
                last_updated=datetime.utcnow(),
                source='file',
            )
            
            sections.append(section)
        
        logger.info(f"Parsed {len(sections)} sections from ARCHITECTURE.md")
        return sections
    
    def _parse_frontmatter(self, content: str) -> Dict[str, Any]:
        """Parse YAML frontmatter from content."""
        frontmatter = {}
        
        # Look for frontmatter between --- markers
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if match:
            fm_content = match.group(1)
            
            # Simple key: value parsing
            for line in fm_content.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    frontmatter[key.strip()] = value.strip()
        
        return frontmatter
    
    def _determine_category(self, title: str, content: str) -> str:
        """Determine section category from title and content."""
        title_lower = title.lower()
        content_lower = content.lower()
        
        # Check title keywords
        if any(kw in title_lower for kw in ['overview', 'architecture', 'system']):
            return 'architecture'
        elif any(kw in title_lower for kw in ['security', 'auth', 'encrypt']):
            return 'security'
        elif any(kw in title_lower for kw in ['deploy', 'config', 'setup']):
            return 'deployment'
        elif any(kw in title_lower for kw in ['monitor', 'observ', 'metric']):
            return 'operations'
        elif any(kw in title_lower for kw in ['component', 'service', 'module']):
            return 'technical'
        elif any(kw in title_lower for kw in ['memory', 'storage', 'cache']):
            return 'memory'
        elif any(kw in title_lower for kw in ['agent', 'task', 'workflow']):
            return 'operations'
        
        # Check content for clues
        if 'security' in content_lower[:500]:
            return 'security'
        elif 'deploy' in content_lower[:500]:
            return 'deployment'
        
        return 'general'
    
    def _generate_summary(self, content: str, max_length: int = 200) -> str:
        """Generate a summary of section content."""
        # Remove code blocks
        clean = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
        # Remove inline code
        clean = re.sub(r'`[^`]+`', '', clean)
        # Remove markdown links
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        # Get first paragraph
        paragraphs = clean.strip().split('\n\n')
        first_para = paragraphs[0] if paragraphs else clean
        
        # Truncate
        if len(first_para) > max_length:
            first_para = first_para[:max_length-3] + '...'
        
        return first_para.strip()
    
    def get_neo4j_sections(self, include_proposals: bool = True) -> List[ArchitectureSection]:
        """
        Get sections from Neo4j.
        
        Args:
            include_proposals: Whether to include unapproved proposals
            
        Returns:
            List of ArchitectureSection objects from Neo4j
        """
        driver = self._get_driver()
        sections = []
        
        with driver.session() as session:
            query = """
                MATCH (as:ArchitectureSection)
                WHERE as.proposal = false OR as.proposal IS NULL
            """
            
            if include_proposals:
                query = """
                    MATCH (as:ArchitectureSection)
                    WHERE as.proposal = false OR as.proposal IS NULL
                       OR (as.proposal = true AND as.proposal_approved = true)
                """
            
            query += " RETURN as ORDER BY as.section_order"
            
            result = session.run(query)
            
            for record in result:
                node = record['as']
                
                section = ArchitectureSection(
                    id=node['id'],
                    title=node['title'],
                    category=node.get('category', 'general'),
                    section_order=node.get('section_order', 0),
                    content=node.get('content', ''),
                    content_summary=node.get('content_summary', ''),
                    version=node.get('version', '1.0'),
                    last_updated=node.get('last_updated', datetime.utcnow()),
                    source='neo4j',
                    hash=node.get('hash', ''),
                    proposal=node.get('proposal', False),
                    proposal_author=node.get('proposal_author'),
                    proposal_approved=node.get('proposal_approved', False),
                )
                
                sections.append(section)
        
        return sections
    
    def detect_changes(self, 
                      file_sections: List[ArchitectureSection],
                      neo4j_sections: List[ArchitectureSection]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Detect changes between file and Neo4j sections.
        
        Args:
            file_sections: Sections from file
            neo4j_sections: Sections from Neo4j
            
        Returns:
            Dict with 'added', 'modified', 'deleted', 'unchanged' lists
        """
        changes = {
            'added': [],
            'modified': [],
            'deleted': [],
            'unchanged': [],
        }
        
        # Index by title
        file_by_title = {s.title: s for s in file_sections}
        neo4j_by_title = {s.title: s for s in neo4j_sections}
        
        file_titles = set(file_by_title.keys())
        neo4j_titles = set(neo4j_by_title.keys())
        
        # Added in file (not in Neo4j)
        for title in file_titles - neo4j_titles:
            changes['added'].append({
                'title': title,
                'section': file_by_title[title].to_dict(),
                'source': 'file',
            })
        
        # Deleted from file (in Neo4j but not file)
        for title in neo4j_titles - file_titles:
            changes['deleted'].append({
                'title': title,
                'section': neo4j_by_title[title].to_dict(),
                'source': 'neo4j',
            })
        
        # Potentially modified (in both)
        for title in file_titles & neo4j_titles:
            file_section = file_by_title[title]
            neo4j_section = neo4j_by_title[title]
            
            if file_section.hash != neo4j_section.hash:
                changes['modified'].append({
                    'title': title,
                    'file_section': file_section.to_dict(),
                    'neo4j_section': neo4j_section.to_dict(),
                    'file_hash': file_section.hash,
                    'neo4j_hash': neo4j_section.hash,
                })
            else:
                changes['unchanged'].append({
                    'title': title,
                    'section': file_section.to_dict(),
                })
        
        return changes
    
    def sync_file_to_neo4j(self, 
                          sections: Optional[List[ArchitectureSection]] = None,
                          dry_run: bool = False) -> SyncResult:
        """
        Sync sections from file to Neo4j.
        
        Args:
            sections: Sections to sync (default: parse from file)
            dry_run: If True, don't actually make changes
            
        Returns:
            SyncResult with details
        """
        if sections is None:
            sections = self.parse_architecture_file()
        
        result = SyncResult(
            success=True,
            direction=SyncDirection.FILE_TO_NEO4J,
            changes={'synced': []},
        )
        
        if dry_run:
            logger.info(f"[DRY RUN] Would sync {len(sections)} sections to Neo4j")
            result.sections_synced = len(sections)
            return result
        
        driver = self._get_driver()
        
        with driver.session() as session:
            for section in sections:
                try:
                    session.run("""
                        MERGE (as:ArchitectureSection {title: $title})
                        ON CREATE SET 
                            as.id = $id,
                            as.created_at = datetime()
                        SET as.category = $category,
                            as.section_order = $order,
                            as.content = $content,
                            as.content_summary = $summary,
                            as.version = $version,
                            as.last_updated = datetime(),
                            as.hash = $hash,
                            as.source = 'file',
                            as.proposal = false
                    """,
                        id=section.id,
                        title=section.title,
                        category=section.category,
                        order=section.section_order,
                        content=section.content,
                        summary=section.content_summary,
                        version=section.version,
                        hash=section.hash,
                    )
                    
                    result.sections_synced += 1
                    result.changes['synced'].append({
                        'title': section.title,
                        'category': section.category,
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to sync section {section.title}: {e}")
        
        logger.info(f"Synced {result.sections_synced} sections to Neo4j")
        return result
    
    def sync_neo4j_to_file(self,
                          approved_only: bool = True,
                          dry_run: bool = False) -> SyncResult:
        """
        Sync sections from Neo4j to file.
        
        Args:
            approved_only: Only sync approved proposals
            dry_run: If True, don't actually make changes
            
        Returns:
            SyncResult with details
        """
        neo4j_sections = self.get_neo4j_sections(include_proposals=not approved_only)
        file_sections = self.parse_architecture_file()
        
        # Detect changes
        changes = self.detect_changes(file_sections, neo4j_sections)
        
        result = SyncResult(
            success=True,
            direction=SyncDirection.NEO4J_TO_FILE,
            changes=changes,
        )
        
        # Check for conflicts
        if changes['modified']:
            for modified in changes['modified']:
                file_sec = next(s for s in file_sections if s.title == modified['title'])
                neo4j_sec = next(s for s in neo4j_sections if s.title == modified['title'])
                
                conflict = SyncConflict(
                    section_title=modified['title'],
                    file_version=file_sec,
                    neo4j_version=neo4j_sec,
                    conflict_type='both_modified',
                )
                result.conflicts.append(conflict)
        
        if dry_run:
            logger.info(f"[DRY RUN] Would sync {len(neo4j_sections)} sections to file")
            logger.info(f"  Added: {len(changes['added'])}, Modified: {len(changes['modified'])}")
            result.sections_synced = len(neo4j_sections)
            return result
        
        # Apply changes if no conflicts
        if result.conflicts:
            logger.warning(f"Found {len(result.conflicts)} conflicts, aborting sync")
            result.success = False
            result.error_message = f"{len(result.conflicts)} conflicts need resolution"
            return result
        
        # Rebuild file content
        new_content = self._rebuild_architecture_file(neo4j_sections)
        
        try:
            with open(self.architecture_file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            result.sections_synced = len(neo4j_sections)
            logger.info(f"Synced {result.sections_synced} sections to file")
            
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.error(f"Failed to write architecture file: {e}")
        
        return result
    
    def _rebuild_architecture_file(self, sections: List[ArchitectureSection]) -> str:
        """Rebuild ARCHITECTURE.md content from sections."""
        # Sort by order
        sorted_sections = sorted(sections, key=lambda s: s.section_order)
        
        lines = [
            "---",
            f"title: Kurultai Unified Architecture",
            f"version: {sorted_sections[0].version if sections else '1.0'}",
            f"last_updated: {datetime.utcnow().strftime('%Y-%m-%d')}",
            "---",
            "",
            "# Kurultai Unified Architecture",
            "",
        ]
        
        for section in sorted_sections:
            lines.extend([
                f"## {section.title}",
                "",
                section.content,
                "",
            ])
        
        return '\n'.join(lines)
    
    def create_proposal(self, 
                       title: str,
                       content: str,
                       category: str,
                       author: str,
                       section_order: Optional[int] = None) -> Optional[str]:
        """
        Create a proposal for architecture change.
        
        Args:
            title: Section title
            content: Section content
            category: Section category
            author: Proposal author
            section_order: Optional section order
            
        Returns:
            Proposal ID if successful, None otherwise
        """
        # Validate author
        if author not in self.AUTHORIZED_AUTHORS:
            logger.error(f"Unauthorized author: {author}")
            return None
        
        proposal_id = str(uuid.uuid4())
        
        driver = self._get_driver()
        
        with driver.session() as session:
            # Determine section order if not provided
            if section_order is None:
                result = session.run("""
                    MATCH (as:ArchitectureSection)
                    RETURN max(as.section_order) as max_order
                """)
                record = result.single()
                max_order = record['max_order'] if record else 0
                section_order = (max_order or 0) + 1
            
            # Create proposal
            session.run("""
                CREATE (as:ArchitectureSection {
                    id: $id,
                    title: $title,
                    category: $category,
                    section_order: $order,
                    content: $content,
                    content_summary: $summary,
                    version: $version,
                    created_at: datetime(),
                    last_updated: datetime(),
                    proposal: true,
                    proposal_author: $author,
                    proposal_approved: false,
                    proposal_created_at: datetime()
                })
            """,
                id=proposal_id,
                title=title,
                category=category,
                order=section_order,
                content=content,
                summary=self._generate_summary(content),
                version='proposed',
                author=author,
            )
        
        logger.info(f"Created proposal: {title} by {author}")
        return proposal_id
    
    def approve_proposal(self, proposal_id: str, approver: str) -> bool:
        """
        Approve a proposal.
        
        Args:
            proposal_id: ID of proposal to approve
            approver: Person approving (must be authorized)
            
        Returns:
            True if approved successfully
        """
        if approver not in self.AUTHORIZED_AUTHORS:
            logger.error(f"Unauthorized approver: {approver}")
            return False
        
        driver = self._get_driver()
        
        with driver.session() as session:
            result = session.run("""
                MATCH (as:ArchitectureSection {id: $id})
                WHERE as.proposal = true
                SET as.proposal_approved = true,
                    as.approved_by = $approver,
                    as.approved_at = datetime()
                RETURN as.id as id
            """, id=proposal_id, approver=approver)
            
            if result.single():
                logger.info(f"Approved proposal {proposal_id} by {approver}")
                return True
            else:
                logger.error(f"Proposal not found: {proposal_id}")
                return False
    
    def reject_proposal(self, proposal_id: str, 
                       rejector: str,
                       reason: str) -> bool:
        """
        Reject a proposal.
        
        Args:
            proposal_id: ID of proposal to reject
            rejector: Person rejecting
            reason: Rejection reason
            
        Returns:
            True if rejected successfully
        """
        driver = self._get_driver()
        
        with driver.session() as session:
            result = session.run("""
                MATCH (as:ArchitectureSection {id: $id})
                WHERE as.proposal = true
                SET as.proposal_rejected = true,
                    as.rejected_by = $rejector,
                    as.rejected_at = datetime(),
                    as.rejection_reason = $reason
                RETURN as.id as id
            """, id=proposal_id, rejector=rejector, reason=reason)
            
            if result.single():
                logger.info(f"Rejected proposal {proposal_id} by {rejector}")
                return True
            else:
                return False
    
    def sync_bidirectional(self, 
                          conflict_resolution: str = 'manual',
                          dry_run: bool = False) -> SyncResult:
        """
        Perform bidirectional sync with conflict resolution.
        
        Args:
            conflict_resolution: 'manual', 'file_wins', 'neo4j_wins', 'newer_wins'
            dry_run: If True, don't actually make changes
            
        Returns:
            SyncResult with details
        """
        file_sections = self.parse_architecture_file()
        neo4j_sections = self.get_neo4j_sections()
        
        changes = self.detect_changes(file_sections, neo4j_sections)
        
        result = SyncResult(
            success=True,
            direction=SyncDirection.BIDIRECTIONAL,
            changes=changes,
        )
        
        # Handle conflicts
        if changes['modified'] and conflict_resolution == 'manual':
            for modified in changes['modified']:
                file_sec = next((s for s in file_sections if s.title == modified['title']), None)
                neo4j_sec = next((s for s in neo4j_sections if s.title == modified['title']), None)
                
                result.conflicts.append(SyncConflict(
                    section_title=modified['title'],
                    file_version=file_sec,
                    neo4j_version=neo4j_sec,
                    conflict_type='both_modified',
                ))
            
            result.success = False
            result.error_message = f"{len(result.conflicts)} conflicts require manual resolution"
            return result
        
        if dry_run:
            logger.info("[DRY RUN] Bidirectional sync:")
            logger.info(f"  File sections: {len(file_sections)}")
            logger.info(f"  Neo4j sections: {len(neo4j_sections)}")
            logger.info(f"  Added: {len(changes['added'])}")
            logger.info(f"  Modified: {len(changes['modified'])}")
            logger.info(f"  Deleted: {len(changes['deleted'])}")
            return result
        
        # Apply file to Neo4j
        file_to_neo4j_result = self.sync_file_to_neo4j(file_sections)
        result.sections_synced += file_to_neo4j_result.sections_synced
        
        logger.info("Bidirectional sync complete")
        return result
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status between file and Neo4j."""
        try:
            file_sections = self.parse_architecture_file()
        except FileNotFoundError:
            return {
                'file_exists': False,
                'neo4j_sections': 0,
                'synced': False,
            }
        
        neo4j_sections = self.get_neo4j_sections()
        changes = self.detect_changes(file_sections, neo4j_sections)
        
        return {
            'file_exists': True,
            'file_sections': len(file_sections),
            'neo4j_sections': len(neo4j_sections),
            'synced': len(changes['added']) == 0 and len(changes['modified']) == 0 and len(changes['deleted']) == 0,
            'changes': {
                'added': len(changes['added']),
                'modified': len(changes['modified']),
                'deleted': len(changes['deleted']),
            },
            'pending_proposals': len([s for s in neo4j_sections if s.proposal and not s.proposal_approved]),
        }
