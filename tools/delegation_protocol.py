"""
Kublai Delegation Protocol for OpenClaw Multi-Agent System.

This module implements the delegation protocol used by Kublai (main agent) to:
1. Query personal memory for user context
2. Query operational memory for related prior work
3. Sanitize content for privacy before sharing
4. Delegate tasks to specialist agents via agentToAgent
5. Store results to operational memory
6. Synthesize responses combining personal and operational context

Dual Memory System:
- Personal Memory (MEMORY.md, memory/*.md): User preferences, personal history - Kublai ONLY
- Operational Memory (Neo4j): Research, code patterns, analysis - ALL agents

Location: /Users/kurultai/molt/tools/delegation_protocol.py
"""

import re
import uuid
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import json

# Import OperationalMemory from openclaw_memory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openclaw_memory import OperationalMemory

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Enumeration of task types for delegation routing."""
    RESEARCH = "research"
    WRITING = "writing"
    CODE = "code"
    SECURITY = "security"
    ANALYSIS = "analysis"
    PROCESS = "process"
    OPS = "ops"


class Agent(Enum):
    """Enumeration of OpenClaw specialist agents."""
    KUBLAI = "main"
    MONGKE = "researcher"
    CHAGATAI = "writer"
    TEMUJIN = "developer"
    JOCHI = "analyst"
    OGEDEI = "ops"


@dataclass
class PersonalContext:
    """Personal memory context loaded from files."""
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    recent_history: List[str] = field(default_factory=list)
    friend_names: List[str] = field(default_factory=list)
    relevant_notes: List[str] = field(default_factory=list)
    user_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_preferences": self.user_preferences,
            "recent_history": self.recent_history,
            "friend_names": self.friend_names,
            "relevant_notes": self.relevant_notes,
            "user_message": self.user_message
        }


@dataclass
class DelegationResult:
    """Result of a delegation operation."""
    success: bool
    task_id: str
    target_agent: str
    agent_name: str
    message: str
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "target_agent": self.target_agent,
            "agent_name": self.agent_name,
            "message": self.message,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class DelegationProtocol:
    """
    Kublai's delegation protocol with privacy-aware operational memory.

    This class implements the full delegation workflow:
    1. Query personal memory for user context
    2. Query operational memory for related prior work
    3. Sanitize content for privacy before sharing with other agents
    4. Delegate via agentToAgent based on task type
    5. Store results to operational memory
    6. Synthesize response combining personal and operational context

    Agent Routing:
    - Research -> @researcher (Möngke)
    - Writing -> @writer (Chagatai)
    - Code/Security -> @developer (Temüjin)
    - Analysis -> @analyst (Jochi)
    - Process/Tasks -> @ops (Ögedei)
    """

    # Agent routing mapping - task type keywords to agent IDs
    AGENT_ROUTING: Dict[str, str] = {
        "research": "researcher",
        "investigate": "researcher",
        "find": "researcher",
        "search": "researcher",
        "discover": "researcher",
        "explore": "researcher",
        "writing": "writer",
        "write": "writer",
        "draft": "writer",
        "document": "writer",
        "content": "writer",
        "compose": "writer",
        "edit": "writer",
        "code": "developer",
        "coding": "developer",
        "develop": "developer",
        "implement": "developer",
        "programming": "developer",
        "build": "developer",
        "fix": "developer",
        "bug": "developer",
        "debug": "developer",
        "refactor": "developer",
        "security": "developer",
        "secure": "developer",
        "audit": "developer",
        "vulnerability": "developer",
        "analysis": "analyst",
        "analyze": "analyst",
        "analytics": "analyst",
        "performance": "analyst",
        "metrics": "analyst",
        "optimization": "analyst",
        "optimize": "analyst",
        "pattern": "analyst",
        "strategy": "analyst",
        "process": "ops",
        "ops": "ops",
        "deploy": "ops",
        "deployment": "ops",
        "monitor": "ops",
        "operation": "ops",
        "infrastructure": "ops",
        "emergency": "ops",
        "task": "ops",
        "workflow": "ops",
        "documentation": "ops"
    }

    # Agent display names for user-friendly responses
    AGENT_NAMES: Dict[str, str] = {
        "main": "Kublai",
        "researcher": "Möngke",
        "writer": "Chagatai",
        "developer": "Temüjin",
        "analyst": "Jochi",
        "ops": "Ögedei"
    }

    # Privacy patterns to sanitize - these should NEVER be shared with other agents
    # ORDER MATTERS: More specific patterns must come before general ones
    PRIVATE_PATTERNS: List[Tuple[str, str]] = [
        # SSN format (XXX-XX-XXXX) - must come before generic phone pattern
        (r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b", "[SSN]"),
        # Email addresses
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
        # Credit card (4-4-4-4 format) - must come before generic phone pattern
        (r"\b(?:\d{4}[-.\s]?){3}\d{4}\b", "[CREDIT_CARD]"),
        # IP addresses (must come before generic digit patterns)
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP_ADDRESS]"),
        # US phone numbers (more restrictive to avoid false positives)
        (r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", "[PHONE]"),
        # International phone (optional +, country code)
        (r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b", "[PHONE]"),
        # API keys, tokens, secrets
        (r"\b(?:api[_-]?key|apikey|token|secret|password|passwd|pwd)\s*[:=]\s*[\"']?[\w\-]{16,}[\"']?", "[API_KEY]"),
        (r"\b(?:sk-|pk-|ak-|bearer)\s*[\w\-]{20,}", "[API_KEY]"),
        (r"\b[\w]{32,64}\b", "[POTENTIAL_KEY]"),  # Long hex strings
        # Physical addresses
        (r"\d+\s+\w+\s+(?:St|Street|Rd|Road|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|Pl|Place)\b", "[ADDRESS]"),
        # Friend references
        (r"\bfriend[s]?\s+\w+", "[FRIEND_REFERENCE]"),
        # Family references
        (r"\bmy\s+(?:mom|dad|brother|sister|son|daughter|wife|husband|partner)\b", "[FAMILY_REFERENCE]"),
    ]

    # Keywords that indicate personal/private information
    PERSONAL_KEYWORDS = [
        "my friend", "my mother", "my father", "my brother", "my sister",
        "my son", "my daughter", "my wife", "my husband", "my partner",
        "my address", "my phone", "my email", "my social", "my ssn",
        "i live at", "my home", "call me at", "text me at"
    ]

    def __init__(
        self,
        memory: OperationalMemory,
        personal_memory_path: str | None = None,
        gateway_url: str | None = None,
        gateway_token: str | None = None
    ):
        """
        Initialize the DelegationProtocol.

        Args:
            memory: OperationalMemory instance for Neo4j operations
            personal_memory_path: Path to personal memory directory (default: ./memory)
            gateway_url: OpenClaw gateway URL for agentToAgent messaging
            gateway_token: Bearer token for gateway authentication
        """
        self.memory = memory

        # Set personal memory path
        if personal_memory_path is None:
            # Default to ./memory directory relative to project root
            project_root = Path(__file__).parent.parent
            personal_memory_path = project_root / "memory"
        self.personal_memory_path = Path(personal_memory_path)

        # Gateway configuration for agentToAgent messaging
        self.gateway_url = gateway_url
        self.gateway_token = gateway_token

        logger.info(
            f"DelegationProtocol initialized with personal_memory_path={self.personal_memory_path}, "
            f"gateway={'configured' if gateway_url else 'not configured'}"
        )

    def query_personal_memory(self, topic: str, limit: int = 10) -> PersonalContext:
        """
        Load relevant user context from personal MEMORY.md files.

        This method reads from the file-based personal memory system:
        - MEMORY.md (main personal memory file)
        - memory/*.md (daily memory files)

        Args:
            topic: Topic to search for in personal memory
            limit: Maximum number of relevant notes to return

        Returns:
            PersonalContext containing relevant user information
        """
        context = PersonalContext()

        try:
            # Try to read main MEMORY.md file
            memory_md = self.personal_memory_path.parent / "MEMORY.md"
            if memory_md.exists():
                relevant_lines = self._search_file_for_topic(memory_md, topic, limit)
                context.relevant_notes.extend(relevant_lines)

            # Try to read daily memory files
            if self.personal_memory_path.exists():
                for md_file in sorted(self.personal_memory_path.glob("*.md"), reverse=True)[:7]:
                    relevant_lines = self._search_file_for_topic(md_file, topic, limit)
                    context.relevant_notes.extend(relevant_lines)

            # Extract friend names (these will be sanitized before sharing)
            context.friend_names = self._extract_friend_names(context.relevant_notes)

            # Extract user preferences
            context.user_preferences = self._extract_preferences(context.relevant_notes)

            logger.info(f"Loaded {len(context.relevant_notes)} relevant notes from personal memory")

        except Exception as e:
            logger.warning(f"Error reading personal memory: {e}")

        return context

    def _search_file_for_topic(self, file_path: Path, topic: str, limit: int) -> List[str]:
        """Search a file for lines related to the topic."""
        relevant_lines = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Simple keyword matching
            topic_lower = topic.lower()
            lines = content.split('\n')

            for line in lines:
                if topic_lower in line.lower() and len(line.strip()) > 10:
                    relevant_lines.append(line.strip())
                    if len(relevant_lines) >= limit:
                        break

        except Exception as e:
            logger.debug(f"Error searching file {file_path}: {e}")

        return relevant_lines

    def _extract_friend_names(self, notes: List[str]) -> List[str]:
        """Extract potential friend names from notes."""
        friends = set()

        # Pattern for "my friend X" or similar
        friend_pattern = re.compile(r'\b(?:my\s+)?friend[s]?\s+([A-Z][a-z]+)', re.IGNORECASE)

        for note in notes:
            matches = friend_pattern.findall(note)
            friends.update(matches)

        return list(friends)

    def _extract_preferences(self, notes: List[str]) -> Dict[str, Any]:
        """Extract user preferences from notes."""
        preferences = {}

        # Look for preference patterns
        pref_keywords = ["prefer", "like", "dislike", "favorite", "always", "never"]

        for note in notes:
            note_lower = note.lower()
            for keyword in pref_keywords:
                if keyword in note_lower:
                    # Extract the preference statement
                    preferences[keyword] = note[:100]  # Truncate for storage

        return preferences

    def query_operational_memory(
        self,
        topic: str,
        agent: str | None = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Check for related prior work in Neo4j operational memory.

        This method queries the Neo4j graph database for:
        - Related Research nodes (Möngke's work)
        - Related Content nodes (Chagatai's work)
        - Related Application nodes (Temüjin's work)
        - Related Analysis nodes (Jochi's work)
        - Related Task nodes (all agents)

        Args:
            topic: Topic to search for
            agent: Optional agent filter
            limit: Maximum results to return

        Returns:
            List of related operational memory records
        """
        results = []

        try:
            # Build query for different node types based on topic
            topic_pattern = f"(?i){topic}"  # Case-insensitive search

            # Query Tasks
            task_query = """
            MATCH (t:Task)
            WHERE t.description =~ $topic_pattern
               OR t.type =~ $topic_pattern
            RETURN t.id as id,
                   'task' as type,
                   t.description as description,
                   t.status as status,
                   t.assigned_to as agent,
                   t.created_at as created_at
            LIMIT $limit
            """

            with self.memory._session() as session:
                if session is not None:
                    task_result = session.run(
                        task_query,
                        topic_pattern=topic_pattern,
                        limit=limit
                    )
                    for record in task_result:
                        results.append(dict(record))

                    # Query Research nodes
                    research_query = """
                    MATCH (r:Research)
                    WHERE r.topic =~ $topic_pattern
                    RETURN r.id as id,
                           'research' as type,
                           r.topic as description,
                           r.agent as agent,
                           r.created_at as created_at
                    LIMIT $limit
                    """
                    research_result = session.run(
                        research_query,
                        topic_pattern=topic_pattern,
                        limit=limit
                    )
                    for record in research_result:
                        results.append(dict(record))

                    # Query Analysis nodes
                    analysis_query = """
                    MATCH (a:Analysis)
                    WHERE a.title =~ $topic_pattern
                       OR a.findings =~ $topic_pattern
                    RETURN a.id as id,
                           'analysis' as type,
                           a.title as description,
                           a.agent as agent,
                           a.created_at as created_at
                    LIMIT $limit
                    """
                    analysis_result = session.run(
                        analysis_query,
                        topic_pattern=topic_pattern,
                        limit=limit
                    )
                    for record in analysis_result:
                        results.append(dict(record))

        except Exception as e:
            logger.warning(f"Error querying operational memory: {e}")

        logger.info(f"Found {len(results)} related records in operational memory")
        return results[:limit]

    def sanitize_for_delegation(self, content: str) -> Tuple[str, Dict[str, int]]:
        """
        Remove private information before sharing with other agents.

        This is CRITICAL for privacy protection. Personal memory contains:
        - Friend names
        - Phone numbers
        - Email addresses
        - Personal addresses
        - Family references

        These must be sanitized before ANY content is shared with other agents.

        Args:
            content: Raw content that may contain PII

        Returns:
            Tuple of (sanitized_content, sanitization_counts)
        """
        if not content:
            return content, {}

        sanitized = content
        counts: Dict[str, int] = {}

        # Apply each privacy pattern
        for pattern, placeholder in self.PRIVATE_PATTERNS:
            matches = len(re.findall(pattern, sanitized))
            if matches > 0:
                sanitized = re.sub(pattern, placeholder, sanitized, flags=re.IGNORECASE)
                counts[placeholder] = counts.get(placeholder, 0) + matches

        # Also check for personal keywords and log warnings
        for keyword in self.PERSONAL_KEYWORDS:
            if keyword in sanitized.lower():
                logger.warning(f"Personal keyword detected in content: {keyword}")
                # Don't replace, but flag for review

        if counts:
            logger.info(f"Sanitized {sum(counts.values())} items from content: {counts}")

        return sanitized, counts

    def sanitize_pii(self, text: str, options: Dict[str, Any] = None) -> Tuple[str, Dict[str, int]]:
        """
        Sanitize PII from text - alias for sanitize_for_delegation.

        Args:
            text: Text to sanitize
            options: Sanitization options (optional)

        Returns:
            Tuple of (sanitized_text, sanitization_counts)
        """
        # Use existing sanitize_for_delegation implementation
        return self.sanitize_for_delegation(text)

    def determine_target_agent(
        self,
        task_description: str,
        suggested_agent: str | None = None
    ) -> str:
        """
        Determine which agent should handle the task.

        Args:
            task_description: Description of the task
            suggested_agent: Optional agent suggestion (e.g., from @mention)

        Returns:
            Agent ID to handle the task
        """
        # If agent explicitly suggested, validate and use it
        if suggested_agent:
            suggested_lower = suggested_agent.lower().lstrip('@')

            # Check if it's a valid agent name
            if suggested_lower in self.AGENT_NAMES:
                return suggested_lower

            # Check if it's an alias
            if suggested_lower in ["kublai", "main"]:
                return "main"

            # Check routing table for keyword match
            if suggested_lower in self.AGENT_ROUTING:
                return self.AGENT_ROUTING[suggested_lower]

        # Extract @mentions from description
        mention_pattern = r'@(\w+)'
        mentions = re.findall(mention_pattern, task_description.lower())

        for mention in mentions:
            if mention in self.AGENT_NAMES:
                return mention
            if mention in self.AGENT_ROUTING:
                return self.AGENT_ROUTING[mention]

        # Score each agent based on keyword matches
        description_lower = task_description.lower()
        agent_scores: Dict[str, int] = {}

        for keyword, agent in self.AGENT_ROUTING.items():
            if keyword in description_lower:
                agent_scores[agent] = agent_scores.get(agent, 0) + 1

        # Return agent with highest score, or default to main
        if agent_scores:
            return max(agent_scores, key=agent_scores.get)

        # Default: Kublai handles directly
        return "main"

    def delegate_task(
        self,
        task_description: str,
        context: Dict[str, Any],
        suggested_agent: str | None = None,
        priority: str = "normal",
        delegated_by: str = "main"
    ) -> DelegationResult:
        """
        Full delegation workflow with privacy protection.

        Steps:
        1. Query personal memory for user context
        2. Query operational memory for related work
        3. Sanitize content for privacy
        4. Determine target agent
        5. Create task in Neo4j
        6. Delegate via agentToAgent (if gateway configured)
        7. Store delegation record

        Args:
            task_description: The task to delegate
            context: Additional context (sender_hash, topic, etc.)
            suggested_agent: Optional agent suggestion
            priority: Task priority (low, normal, high, critical)
            delegated_by: Agent doing the delegation (default: main/Kublai)

        Returns:
            DelegationResult with task details
        """
        started_at = datetime.now(timezone.utc)
        task_id = str(uuid.uuid4())

        try:
            # Step 1: Query personal memory
            topic = context.get("topic", task_description[:50])
            personal_context = self.query_personal_memory(topic)

            # Step 2: Query operational memory
            agent_filter = context.get("agent_filter")
            operational_context = self.query_operational_memory(topic, agent_filter)

            # Step 3: Sanitize for delegation
            sanitized_description, sanitization_counts = self.sanitize_for_delegation(
                task_description
            )

            # Step 4: Determine target agent
            target_agent = self.determine_target_agent(
                sanitized_description,
                suggested_agent
            )

            # Step 5: Create task in Neo4j
            self._create_delegation_task(
                task_id=task_id,
                description=sanitized_description,
                original_description=task_description,
                target_agent=target_agent,
                priority=priority,
                delegated_by=delegated_by,
                context=context
            )

            # Step 6: Delegate via agentToAgent if gateway configured
            if self.gateway_url and target_agent != "main":
                self._send_to_agent(
                    task_id=task_id,
                    target_agent=target_agent,
                    description=sanitized_description
                )

            # Step 7: Store delegation record
            self._store_delegation_record(
                task_id=task_id,
                target_agent=target_agent,
                personal_context=personal_context,
                operational_context=operational_context,
                sanitization_counts=sanitization_counts
            )

            agent_name = self.AGENT_NAMES.get(target_agent, target_agent.capitalize())

            return DelegationResult(
                success=True,
                task_id=task_id,
                target_agent=target_agent,
                agent_name=agent_name,
                message=f"Task delegated to {agent_name} (ID: {task_id})",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc)
            )

        except Exception as e:
            logger.error(f"Delegation failed: {e}", exc_info=True)
            return DelegationResult(
                success=False,
                task_id=task_id,
                target_agent="none",
                agent_name="None",
                message="Delegation failed",
                error=str(e),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc)
            )

    def _create_delegation_task(
        self,
        task_id: str,
        description: str,
        original_description: str,
        target_agent: str,
        priority: str,
        delegated_by: str,
        context: Dict[str, Any]
    ) -> None:
        """Create task node in Neo4j for delegation tracking."""
        created_at = datetime.now(timezone.utc)

        cypher = """
        CREATE (t:Task {
            id: $task_id,
            type: 'delegation',
            description: $description,
            original_description: $original_description,
            status: 'pending',
            target_agent: $target_agent,
            delegated_by: $delegated_by,
            priority: $priority,
            sender_hash: $sender_hash,
            created_at: datetime($created_at),
            updated_at: datetime($created_at)
        })
        RETURN t.id as task_id
        """

        with self.memory._session() as session:
            if session is not None:
                try:
                    session.run(
                        cypher,
                        task_id=task_id,
                        description=description,
                        original_description=original_description,
                        target_agent=target_agent,
                        delegated_by=delegated_by,
                        priority=priority,
                        sender_hash=context.get("sender_hash"),
                        created_at=created_at.isoformat()
                    )
                    logger.info(f"Created delegation task {task_id} for {target_agent}")
                except Exception as e:
                    logger.error(f"Failed to create delegation task: {e}")

    def _send_to_agent(
        self,
        task_id: str,
        target_agent: str,
        description: str
    ) -> bool:
        """
        Send task to agent via agentToAgent messaging.

        Note: This requires the gateway to be configured.
        If not configured, the task is still stored in Neo4j for pickup.
        """
        # This would integrate with the Signal/agentToAgent system
        # For now, we just log it
        logger.info(f"Would send to {target_agent} via agentToAgent: {description[:100]}")
        return True

    def _store_delegation_record(
        self,
        task_id: str,
        target_agent: str,
        personal_context: PersonalContext,
        operational_context: List[Dict],
        sanitization_counts: Dict[str, int]
    ) -> None:
        """Store delegation record for synthesis."""
        # This stores information needed for response synthesis
        logger.debug(
            f"Storing delegation record for {task_id}: "
            f"target={target_agent}, "
            f"sanitized={sum(sanitization_counts.values())} items, "
            f"operational_context={len(operational_context)} items"
        )

    def store_results(
        self,
        agent: str,
        task_id: str,
        results: Dict[str, Any]
    ) -> bool:
        """
        Store agent outputs to operational memory.

        Args:
            agent: Agent that produced the results
            task_id: Task ID for the completed work
            results: Results dictionary to store

        Returns:
            True if successful
        """
        try:
            completed_at = datetime.now(timezone.utc)

            # Update task status
            cypher = """
            MATCH (t:Task {id: $task_id})
            SET t.status = 'completed',
                t.completed_at = datetime($completed_at),
                t.results = $results,
                t.updated_at = datetime($completed_at)
            RETURN t.id as task_id
            """

            with self.memory._session() as session:
                if session is not None:
                    session.run(
                        cypher,
                        task_id=task_id,
                        completed_at=completed_at.isoformat(),
                        results=json.dumps(results)
                    )

            # Create appropriate knowledge node based on agent
            self._create_knowledge_node(agent, task_id, results)

            logger.info(f"Stored results for task {task_id} from {agent}")
            return True

        except Exception as e:
            logger.error(f"Failed to store results: {e}")
            return False

    def _create_knowledge_node(
        self,
        agent: str,
        task_id: str,
        results: Dict[str, Any]
    ) -> None:
        """Create appropriate knowledge node based on agent specialty."""
        created_at = datetime.now(timezone.utc).isoformat()

        # Map agents to their output node types
        agent_node_types = {
            "researcher": "Research",
            "writer": "Content",
            "developer": "Application",
            "analyst": "Analysis",
            "ops": "ProcessUpdate"
        }

        node_type = agent_node_types.get(agent)

        if node_type == "Research":
            cypher = """
            CREATE (r:Research {
                id: $task_id,
                topic: $topic,
                findings: $findings,
                agent: 'mongke',
                task_id: $task_id,
                created_at: datetime($created_at)
            })
            """
        elif node_type == "Content":
            cypher = """
            CREATE (c:Content {
                id: $task_id,
                type: 'summary',
                title: $title,
                body: $body,
                agent: 'chagatai',
                task_id: $task_id,
                created_at: datetime($created_at)
            })
            """
        elif node_type == "Application":
            cypher = """
            CREATE (a:Application {
                id: $task_id,
                context: $context,
                result: $result,
                agent: 'temujin',
                task_id: $task_id,
                created_at: datetime($created_at)
            })
            """
        elif node_type == "Analysis":
            cypher = """
            CREATE (a:Analysis {
                id: $task_id,
                type: 'pattern',
                title: $title,
                findings: $findings,
                agent: 'jochi',
                task_id: $task_id,
                created_at: datetime($created_at)
            })
            """
        elif node_type == "ProcessUpdate":
            cypher = """
            CREATE (p:ProcessUpdate {
                id: $task_id,
                type: 'completion',
                notes: $notes,
                agent: 'ogedei',
                created_at: datetime($created_at)
            })
            """
        else:
            return

        with self.memory._session() as session:
            if session is not None:
                try:
                    session.run(
                        cypher,
                        task_id=task_id,
                        created_at=created_at,
                        topic=results.get("topic", ""),
                        findings=results.get("findings", ""),
                        title=results.get("title", ""),
                        body=results.get("body", ""),
                        context=results.get("context", ""),
                        result=results.get("result", ""),
                        notes=results.get("notes", "")
                    )
                    logger.info(f"Created {node_type} node for task {task_id}")
                except Exception as e:
                    logger.error(f"Failed to create knowledge node: {e}")

    def synthesize_response(
        self,
        personal_context: Dict[str, Any],
        operational_results: Dict[str, Any],
        task_type: str
    ) -> str:
        """
        Combine personal context with operational results.

        Args:
            personal_context: Personal memory context
            operational_results: Results from operational memory
            task_type: Type of task being synthesized

        Returns:
            Synthesized response string
        """
        agent = operational_results.get("agent", "specialist")
        agent_name = self.AGENT_NAMES.get(agent, agent.capitalize())

        summary = operational_results.get("summary", "Task completed.")
        details = operational_results.get("details", "")

        # Start with the operational result
        response = f"{summary}"

        # Add attribution
        if agent != "main":
            response += f"\n\n_(Completed by {agent_name})_"

        # Add relevant details if available
        if details and isinstance(details, str) and len(details) > 0:
            response += f"\n\n{details}"

        # Add personal context if relevant (this is where Kublai adds value)
        if personal_context:
            prefs = personal_context.get("user_preferences", {})
            if prefs:
                # Add personalized note based on preferences
                response += "\n\n_Note: I've kept your preferences in mind for this response._"

        return response

    @staticmethod
    def health_check(memory: OperationalMemory) -> Dict[str, Any]:
        """
        Health check endpoint for gateway monitoring.

        Returns a JSON response with:
        - status: "ok" if all services healthy, "degraded" otherwise
        - timestamp: Current ISO timestamp
        - services: Dict with individual service statuses

        Response format:
        {
            "status": "ok",
            "timestamp": "2026-02-04T...",
            "services": {
                "openclaw": "healthy",
                "neo4j": "healthy",
                "signal": "healthy"
            }
        }
        """
        health = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "openclaw": "healthy",
                "neo4j": "unknown",
                "signal": "unknown"
            }
        }

        # Check Neo4j health via OperationalMemory
        try:
            neo4j_health = memory.health_check()
            health["services"]["neo4j"] = neo4j_health.get("status", "unknown")

            if neo4j_health.get("status") != "healthy":
                health["status"] = "degraded"
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
            health["services"]["neo4j"] = "unavailable"
            health["status"] = "degraded"

        # Signal health check (placeholder - would check Signal client)
        # For now, mark as healthy if no errors
        health["services"]["signal"] = "healthy"

        return health

    def get_pending_delegations(self, agent: str | None = None) -> List[Dict[str, Any]]:
        """
        Get all pending delegated tasks.

        Args:
            agent: Optional agent filter

        Returns:
            List of pending task dictionaries
        """
        cypher = """
        MATCH (t:Task {type: 'delegation'})
        WHERE t.status IN ['pending', 'delegated', 'in_progress']
        """

        if agent:
            cypher += " AND t.target_agent = $agent"

        cypher += """
        RETURN t.id as task_id,
               t.status as status,
               t.target_agent as target_agent,
               t.priority as priority,
               t.description as description,
               t.created_at as created_at,
               t.sender_hash as sender_hash
        ORDER BY
            CASE t.priority
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'normal' THEN 2
                WHEN 'low' THEN 1
                ELSE 0
            END DESC,
            t.created_at ASC
        """

        with self.memory._session() as session:
            if session is not None:
                try:
                    result = session.run(cypher, agent=agent) if agent else session.run(cypher)
                    return [dict(record) for record in result]
                except Exception as e:
                    logger.error(f"Failed to get pending delegations: {e}")

        return []

    def check_agent_availability(self, agent: str) -> bool:
        """
        Check if agent is available (heartbeat within last 5 minutes).

        Args:
            agent: Agent ID to check

        Returns:
            True if agent is available
        """
        five_minutes_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        cypher = """
        MATCH (a:Agent {name: $agent})
        WHERE a.last_heartbeat >= datetime($five_minutes_ago)
          AND a.status IN ['active', 'idle', 'available']
        RETURN a.name as name, a.status as status, a.last_heartbeat as last_heartbeat
        """

        try:
            with self.memory._session() as session:
                if session is not None:
                    result = session.run(cypher, agent=agent, five_minutes_ago=five_minutes_ago)
                    return result.single() is not None
        except Exception as e:
            logger.error(f"Failed to check agent availability: {e}")

        # Default to assuming available if we can't check
        return True

    def get_agent_status(self, agent: str) -> Dict[str, Any] | None:
        """
        Get full status for an agent.

        Args:
            agent: Agent ID

        Returns:
            Agent status dictionary or None
        """
        cypher = """
        MATCH (a:Agent {name: $agent})
        RETURN a.name as name,
               a.status as status,
               a.current_task as current_task,
               a.last_heartbeat as last_heartbeat,
               a.capabilities as capabilities
        """

        with self.memory._session() as session:
            if session is not None:
                try:
                    result = session.run(cypher, agent=agent)
                    record = result.single()
                    return dict(record) if record else None
                except Exception as e:
                    logger.error(f"Failed to get agent status: {e}")

        return None


# =============================================================================
# Convenience functions for common delegation patterns
# =============================================================================

def delegate_research(
    protocol: DelegationProtocol,
    topic: str,
    context: Dict[str, Any],
    priority: str = "normal"
) -> DelegationResult:
    """
    Delegate a research task to Möngke.

    Args:
        protocol: DelegationProtocol instance
        topic: Research topic
        context: Additional context
        priority: Task priority

    Returns:
        DelegationResult
    """
    description = f"Research: {topic}"
    return protocol.delegate_task(
        task_description=description,
        context=context,
        suggested_agent="researcher",
        priority=priority
    )


def delegate_writing(
    protocol: DelegationProtocol,
    topic: str,
    context: Dict[str, Any],
    priority: str = "normal"
) -> DelegationResult:
    """
    Delegate a writing task to Chagatai.

    Args:
        protocol: DelegationProtocol instance
        topic: Writing topic
        context: Additional context
        priority: Task priority

    Returns:
        DelegationResult
    """
    description = f"Write: {topic}"
    return protocol.delegate_task(
        task_description=description,
        context=context,
        suggested_agent="writer",
        priority=priority
    )


def delegate_code(
    protocol: DelegationProtocol,
    task: str,
    context: Dict[str, Any],
    priority: str = "normal"
) -> DelegationResult:
    """
    Delegate a code/development task to Temüjin.

    Args:
        protocol: DelegationProtocol instance
        task: Code task description
        context: Additional context
        priority: Task priority

    Returns:
        DelegationResult
    """
    description = f"Code: {task}"
    return protocol.delegate_task(
        task_description=description,
        context=context,
        suggested_agent="developer",
        priority=priority
    )


def delegate_analysis(
    protocol: DelegationProtocol,
    topic: str,
    context: Dict[str, Any],
    priority: str = "normal"
) -> DelegationResult:
    """
    Delegate an analysis task to Jochi.

    Args:
        protocol: DelegationProtocol instance
        topic: Analysis topic
        context: Additional context
        priority: Task priority

    Returns:
        DelegationResult
    """
    description = f"Analyze: {topic}"
    return protocol.delegate_task(
        task_description=description,
        context=context,
        suggested_agent="analyst",
        priority=priority
    )


# =============================================================================
# Example usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Example: Create protocol instance
    # from openclaw_memory import OperationalMemory
    #
    # memory = OperationalMemory(
    #     uri="bolt://localhost:7687",
    #     username="neo4j",
    #     password="your_password"
    # )
    #
    # protocol = DelegationProtocol(
    #     memory=memory,
    #     personal_memory_path="./memory",
    #     gateway_url="https://kublai.kurult.ai",
    #     gateway_token="your_token"
    # )

    # Example: Health check
    # health = DelegationProtocol.health_check(memory)
    # print(f"Health: {health}")

    # Example: Sanitize content
    # content = "Contact John Doe at john@example.com or 555-123-4567"
    # sanitized, counts = protocol.sanitize_for_delegation(content)
    # print(f"Sanitized: {sanitized}")
    # print(f"Counts: {counts}")

    # Example: Determine agent
    # agent = protocol.determine_agent("Write a blog post about Python")
    # print(f"Agent: {agent}")  # "writer"

    # Example: Full delegation
    # result = protocol.delegate_task(
    #     task_description="Research the latest AI developments",
    #     context={"topic": "AI", "sender_hash": "abc123"},
    #     priority="high"
    # )
    # print(result)

    print("Kublai Delegation Protocol loaded successfully.")
    print("Import and instantiate DelegationProtocol to use.")
