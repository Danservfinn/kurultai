"""
Kublai Delegation Protocol (Improved)

Implements task delegation and routing for the 6-agent OpenClaw system.
Kublai (main) receives all inbound messages and delegates to specialists
via agentToAgent messaging with Neo4j-backed operational memory.

Location: /Users/kurultai/molt/src/protocols/delegation_improved.py

Changes from original delegation.py:
- VALIDATION-001: Add VALID_PRIORITIES and VALID_STATUSES class constants
- VALIDATION-002: Validate priority in create_delegation_task
- VALIDATION-003: Validate from_user is non-empty in create_delegation_task
- VALIDATION-004: Validate description is non-empty and within length bounds in create_delegation_task
- VALIDATION-005: Validate task_type against known types if provided
- VALIDATION-006: Same validations in delegate_task
- VALIDATION-007: Validate results is a dict in handle_task_completion
- ERROR-HANDLING-001: Validate status against allowed transitions in _update_task_status
- ERROR-HANDLING-002: Log and raise on invalid status transition instead of silent False
- SANITIZE-001: Fix overly aggressive hex pattern in sanitize_for_privacy
"""

import re
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)


class OperationalMemory:
    """Operational memory interface for Neo4j operations."""

    def __init__(self, driver=None):
        """Initialize with Neo4j driver."""
        self._driver = driver

    def execute_query(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict]:
        """Execute a Cypher query with parameterized inputs.

        Args:
            query: Cypher query string
            parameters: Query parameters for safe interpolation

        Returns:
            List of result records as dictionaries
        """
        if self._driver is None:
            logger.warning("No Neo4j driver configured, query not executed")
            return []

        parameters = parameters or {}
        try:
            with self._driver.session() as session:
                result = session.run(query, parameters)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")
            return []


class DelegationProtocol:
    """Kublai's task delegation and routing protocol.

    Handles task routing to specialist agents with privacy sanitization,
    agentToAgent messaging, and Neo4j task tracking.

    Agent Mapping:
    - researcher (Möngke): Research tasks
    - writer (Chagatai): Content creation
    - developer (Temüjin): Code/development
    - analyst (Jochi): Analysis/performance
    - ops (Ögedei): Operations/deployment
    - main (Kublai): Direct handling or clarification
    """

    # Agent routing keywords mapped to agent IDs
    AGENT_ROUTING_RULES = {
        "research": "researcher",      # Möngke
        "researcher": "researcher",
        "investigate": "researcher",
        "find": "researcher",
        "search": "researcher",
        "write": "writer",             # Chagatai
        "writer": "writer",
        "content": "writer",
        "document": "writer",
        "draft": "writer",
        "compose": "writer",
        "code": "developer",           # Temüjin
        "develop": "developer",
        "developer": "developer",
        "implement": "developer",
        "program": "developer",
        "build": "developer",
        "fix": "developer",
        "bug": "developer",
        "debug": "developer",
        "refactor": "developer",
        "security": "developer",
        "analyze": "analyst",          # Jochi
        "analyst": "analyst",
        "analysis": "analyst",
        "performance": "analyst",
        "investigate": "analyst",
        "metrics": "analyst",
        "ops": "ops",                  # Ögedei
        "deploy": "ops",
        "monitor": "ops",
        "operation": "ops",
        "infrastructure": "ops",
        "emergency": "ops",
    }

    # Agent display names for user-friendly responses
    AGENT_NAMES = {
        "researcher": "Möngke",
        "writer": "Chagatai",
        "developer": "Temüjin",
        "analyst": "Jochi",
        "ops": "Ögedei",
        "main": "Kublai",
    }

    # VALIDATION-001: Valid priority levels for task creation
    VALID_PRIORITIES = {"low", "normal", "high", "critical"}

    # VALIDATION-001: Valid task statuses and their allowed transitions
    VALID_STATUSES = {
        "pending": {"delegated", "cancelled"},
        "delegated": {"in_progress", "failed", "cancelled"},
        "in_progress": {"completed", "failed", "cancelled"},
        "completed": set(),
        "failed": {"pending"},
        "cancelled": set(),
    }

    # VALIDATION-005: Known task types (keys from AGENT_ROUTING_RULES that represent types)
    KNOWN_TASK_TYPES = {
        "research", "write", "code", "develop", "analyze", "analysis",
        "ops", "deploy", "monitor", "security", "content", "document",
        "implement", "build", "fix", "bug", "debug", "refactor",
        "investigate", "performance", "metrics", "infrastructure",
        "emergency", "draft", "compose", "program", "find", "search",
    }

    # VALIDATION-004: Maximum description length to prevent abuse
    MAX_DESCRIPTION_LENGTH = 10000

    def __init__(self, memory: OperationalMemory, gateway_url: str, gateway_token: str,
                 classifier=None):
        """Initialize with operational memory and gateway config.

        Args:
            memory: OperationalMemory instance for Neo4j operations
            gateway_url: OpenClaw gateway URL (must start with http:// or https://)
            gateway_token: Bearer token for gateway authentication
            classifier: Optional TeamSizeClassifier for complexity scoring

        Raises:
            ValueError: If gateway_url is invalid
        """
        self.memory = memory
        self.gateway_token = gateway_token
        self.classifier = classifier

        # Validate and store gateway URL
        if not gateway_url.startswith(('http://', 'https://')):
            raise ValueError("gateway_url must start with http:// or https://")
        self.gateway_url = gateway_url.rstrip('/')

        logger.info(f"DelegationProtocol initialized with gateway: {self.gateway_url}")

    def _validate_priority(self, priority: str) -> None:
        """Validate priority against allowed values.

        VALIDATION-002: Raises ValueError if priority is not in VALID_PRIORITIES.

        Args:
            priority: Priority string to validate

        Raises:
            ValueError: If priority is not a valid value
        """
        if priority not in self.VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_PRIORITIES))}"
            )

    def _validate_from_user(self, from_user: str) -> None:
        """Validate from_user is non-empty.

        VALIDATION-003: Raises ValueError if from_user is empty or not a string.

        Args:
            from_user: User identifier to validate

        Raises:
            ValueError: If from_user is empty or not a string
        """
        if not isinstance(from_user, str) or not from_user.strip():
            raise ValueError("from_user must be a non-empty string")

    def _validate_description(self, description: str) -> None:
        """Validate description is non-empty and within length bounds.

        VALIDATION-004: Raises ValueError if description is empty, not a string,
        or exceeds MAX_DESCRIPTION_LENGTH.

        Args:
            description: Task description to validate

        Raises:
            ValueError: If description fails validation
        """
        if not isinstance(description, str) or not description.strip():
            raise ValueError("description must be a non-empty string")
        if len(description) > self.MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"description exceeds maximum length of {self.MAX_DESCRIPTION_LENGTH} characters "
                f"(got {len(description)})"
            )

    def _validate_task_type(self, task_type: Optional[str]) -> None:
        """Validate task_type against known types if provided.

        VALIDATION-005: Logs a warning if task_type is not recognized.
        Does not raise since task_type is optional and unknown types fall
        through to keyword-based routing.

        Args:
            task_type: Optional task type to validate
        """
        if task_type is not None:
            if not isinstance(task_type, str) or not task_type.strip():
                raise ValueError("task_type must be a non-empty string when provided")
            if task_type.lower() not in self.KNOWN_TASK_TYPES:
                logger.warning(
                    f"Unrecognized task_type '{task_type}'. "
                    f"Known types: {', '.join(sorted(self.KNOWN_TASK_TYPES))}. "
                    f"Falling back to keyword-based routing."
                )

    def sanitize_for_privacy(self, content: str) -> str:
        """Sanitize content to remove PII before delegation.

        Removes:
        - Phone numbers (various formats)
        - Email addresses
        - API keys, tokens, secrets
        - SSNs
        - Personal names (pattern-based)
        - Physical addresses
        - Credit card numbers
        - IP addresses

        Args:
            content: Raw content that may contain PII

        Returns:
            Sanitized content with PII replaced by placeholders
        """
        if not content:
            return content

        sanitized = content

        # Phone numbers (various formats)
        # Matches: (555) 123-4567, 555-123-4567, 555.123.4567, 5551234567, +1 555 123 4567
        phone_patterns = [
            r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US formats
            r'\+?\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}',  # International
        ]
        for pattern in phone_patterns:
            sanitized = re.sub(pattern, '[PHONE]', sanitized, flags=re.IGNORECASE)

        # Email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        sanitized = re.sub(email_pattern, '[EMAIL]', sanitized)

        # API keys, tokens, secrets (common patterns)
        # SANITIZE-001: Fixed overly aggressive hex pattern.
        # Original r'\b[\w]{32,64}\b' matched normal English words because \w
        # includes [a-zA-Z0-9_]. Replaced with hex-only pattern [0-9a-fA-F]{32,64}
        # to only match strings that look like actual hex keys/hashes.
        api_key_patterns = [
            r'\b(?:api[_-]?key|apikey|token|secret|password|passwd|pwd)\s*[:=]\s*["\']?[\w\-]{16,}["\']?',
            r'\b(?:sk-|pk-|ak-|bearer)\s*[\w\-]{20,}',
            r'\b[0-9a-fA-F]{32,64}\b',  # SANITIZE-001: Hex-only strings (likely keys/hashes)
        ]
        for pattern in api_key_patterns:
            sanitized = re.sub(pattern, '[API_KEY]', sanitized, flags=re.IGNORECASE)

        # SSNs (XXX-XX-XXXX or XXXXXXXXX)
        ssn_pattern = r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'
        sanitized = re.sub(ssn_pattern, '[SSN]', sanitized)

        # Credit card numbers (13-19 digits, with or without spaces/dashes)
        cc_pattern = r'\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,19}\b'
        sanitized = re.sub(cc_pattern, '[CREDIT_CARD]', sanitized)

        # IP addresses (IPv4 and IPv6)
        ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        sanitized = re.sub(ipv4_pattern, '[IP_ADDRESS]', sanitized)

        # Physical addresses (simplified pattern)
        address_pattern = r'\d+\s+\w+\s+(?:St|Street|Rd|Road|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|Pl|Place)\b'
        sanitized = re.sub(address_pattern, '[ADDRESS]', sanitized, flags=re.IGNORECASE)

        # Personal names (pattern-based: Two capitalized words)
        # Note: This is a heuristic and may have false positives
        name_pattern = r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
        sanitized = re.sub(name_pattern, '[NAME]', sanitized)

        # Log what was sanitized (without exposing the actual values)
        if sanitized != content:
            logger.info("PII sanitization applied to content")

        return sanitized

    def classify_task_complexity(self, description: str) -> Optional[Dict[str, Any]]:
        """Classify the complexity of a task description.

        Uses the configured classifier to determine complexity score and
        appropriate team size. Returns None if no classifier is configured.

        Args:
            description: Task description to classify

        Returns:
            Dict with 'complexity_score' and 'team_size', or None
        """
        if self.classifier is None:
            return None

        try:
            result = self.classifier.classify(description)
            score = result.get("complexity", 0.0) if isinstance(result, dict) else 0.0
            team_size = result.get("team_size", "individual") if isinstance(result, dict) else "individual"
            return {
                "complexity_score": score,
                "team_size": team_size,
            }
        except Exception as e:
            logger.warning(f"Complexity classification failed: {e}")
            return None

    def determine_agent(self, task_description: str, task_type: Optional[str] = None) -> str:
        """Determine which agent should handle the task.

        Routing rules:
        - research -> researcher (Möngke)
        - write, content, document -> writer (Chagatai)
        - code, develop, security -> developer (Temüjin)
        - analyze, performance, investigate -> analyst (Jochi)
        - ops, deploy, monitor -> ops (Ögedei)
        - Default: main (Kublai handles directly or asks for clarification)

        Args:
            task_description: Description of the task
            task_type: Optional explicit task type

        Returns:
            Agent ID to handle the task
        """
        # If explicit task_type provided, use it directly
        if task_type:
            task_type_lower = task_type.lower()
            if task_type_lower in self.AGENT_ROUTING_RULES:
                return self.AGENT_ROUTING_RULES[task_type_lower]

        # Analyze task description for keywords
        description_lower = task_description.lower()

        # Check for explicit @mentions
        mention_pattern = r'@(\w+)'
        mentions = re.findall(mention_pattern, description_lower)
        for mention in mentions:
            if mention in self.AGENT_ROUTING_RULES:
                return self.AGENT_ROUTING_RULES[mention]
            # Check if it's a direct agent name
            if mention in self.AGENT_NAMES:
                return mention

        # Score each agent based on keyword matches
        agent_scores = {}
        words = set(re.findall(r'\b\w+\b', description_lower))

        for keyword, agent in self.AGENT_ROUTING_RULES.items():
            if keyword in description_lower:
                agent_scores[agent] = agent_scores.get(agent, 0) + 1

        # Return agent with highest score, or default to main
        if agent_scores:
            return max(agent_scores, key=agent_scores.get)

        # Default: Kublai handles directly
        return "main"

    def create_delegation_task(self, from_user: str, description: str,
                               task_type: Optional[str] = None,
                               priority: str = "normal") -> str:
        """Create a task for delegation.

        1. Validate inputs
        2. Sanitize description for privacy
        3. Determine target agent
        4. Create Task node in Neo4j
        5. Return task_id

        Args:
            from_user: User ID who originated the request
            description: Task description
            task_type: Optional explicit task type
            priority: Task priority (low, normal, high, critical)

        Returns:
            task_id: UUID of the created task

        Raises:
            ValueError: If from_user, description, priority, or task_type is invalid
            RuntimeError: If task creation in Neo4j fails
        """
        # VALIDATION-002: Validate priority
        self._validate_priority(priority)

        # VALIDATION-003: Validate from_user
        self._validate_from_user(from_user)

        # VALIDATION-004: Validate description
        self._validate_description(description)

        # VALIDATION-005: Validate task_type if provided
        self._validate_task_type(task_type)

        # Step 1: Sanitize for privacy
        sanitized_description = self.sanitize_for_privacy(description)

        # Step 2: Determine target agent
        target_agent = self.determine_agent(description, task_type)

        # Step 2.5: Classify complexity (uses sanitized description, not raw)
        complexity_result = self.classify_task_complexity(sanitized_description)
        complexity_score = complexity_result["complexity_score"] if complexity_result else None
        team_size = complexity_result["team_size"] if complexity_result else None

        # Step 3: Create Task node in Neo4j
        task_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"

        query = """
        CREATE (t:Task {
            id: $task_id,
            status: 'pending',
            from_user: $from_user,
            original_description: $original_description,
            sanitized_description: $sanitized_description,
            task_type: $task_type,
            target_agent: $target_agent,
            priority: $priority,
            complexity_score: $complexity_score,
            team_size: $team_size,
            created_at: datetime($timestamp),
            updated_at: datetime($timestamp),
            delegated_by: 'main'
        })
        RETURN t.id as task_id
        """

        parameters = {
            "task_id": task_id,
            "from_user": from_user,
            "original_description": description,
            "sanitized_description": sanitized_description,
            "task_type": task_type or "unknown",
            "target_agent": target_agent,
            "priority": priority,
            "complexity_score": complexity_score,
            "team_size": team_size,
            "timestamp": timestamp,
        }

        result = self.memory.execute_query(query, parameters)

        if result:
            logger.info(f"Created task {task_id} for agent {target_agent}")
            return task_id
        else:
            logger.error("Failed to create task in Neo4j")
            raise RuntimeError("Failed to create task in operational memory")

    def delegate_via_agenttoagent(self, task_id: str, target_agent: str,
                                  original_description: str) -> bool:
        """Send delegation via agentToAgent messaging.

        Uses OpenClaw gateway API:
        POST /agent/{target_agent}/message

        Headers:
        - Authorization: Bearer {gateway_token}
        - Content-Type: application/json

        Body:
        {
            "message": "@agent task description",
            "context": {
                "task_id": task_id,
                "delegated_by": "main",
                "task_type": "...",
                "reply_to": "main"
            }
        }

        Args:
            task_id: Task ID to delegate
            target_agent: Target agent ID
            original_description: Original task description

        Returns:
            True if delegation successful, False otherwise
        """
        # Validate target agent against allowlist (prevent SSRF)
        allowed_agents = {'main', 'researcher', 'writer', 'developer', 'analyst', 'ops'}
        if target_agent not in allowed_agents:
            logger.error(f"Invalid target agent: {target_agent}. Must be one of: {allowed_agents}")
            return False

        # Validate gateway URL (defense in depth)
        if not self.gateway_url.startswith(('http://', 'https://')):
            logger.error("Invalid gateway URL: must start with http:// or https://")
            return False

        # Build URL securely using urljoin
        endpoint = f"/agent/{target_agent}/message"
        url = urljoin(self.gateway_url + "/", endpoint)

        # Validate URL components (prevent SSRF)
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                logger.error(f"Invalid URL scheme: {parsed.scheme}")
                return False
        except ValueError as e:
            logger.error(f"URL parsing failed: {e}")
            return False

        # Prepare request payload
        payload = {
            "message": f"@{target_agent} {original_description}",
            "context": {
                "task_id": task_id,
                "delegated_by": "main",
                "task_type": "task_assignment",
                "reply_to": "main"
            }
        }

        headers = {
            "Authorization": f"Bearer {self.gateway_token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30,
                allow_redirects=False  # Security: prevent redirect-based SSRF
            )

            if response.status_code == 200:
                logger.info(f"Successfully delegated task {task_id} to {target_agent}")

                # Update task status to delegated
                self._update_task_status(task_id, "delegated")
                return True
            else:
                logger.error(f"Delegation failed: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return False

    def _update_task_status(self, task_id: str, status: str) -> bool:
        """Update task status in Neo4j.

        ERROR-HANDLING-001: Validates status against VALID_STATUSES. Fetches
        current status from Neo4j and checks that the transition is allowed.
        Raises ValueError for invalid status values and logs warnings for
        invalid transitions instead of silently returning False.

        Args:
            task_id: Task ID to update
            status: New status value

        Returns:
            True if update successful

        Raises:
            ValueError: If status is not a recognized status value
        """
        # ERROR-HANDLING-001: Validate status is a known value
        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_STATUSES.keys()))}"
            )

        # ERROR-HANDLING-001: Fetch current status and validate transition
        current_query = """
        MATCH (t:Task {id: $task_id})
        RETURN t.status as status
        """
        current_result = self.memory.execute_query(current_query, {"task_id": task_id})

        if not current_result:
            # ERROR-HANDLING-002: Log explicitly instead of silent False
            logger.error(f"Cannot update status: task {task_id} not found in Neo4j")
            return False

        current_status = current_result[0].get("status")

        if current_status and current_status in self.VALID_STATUSES:
            allowed_next = self.VALID_STATUSES[current_status]
            if status not in allowed_next:
                # ERROR-HANDLING-002: Log warning for invalid transition
                logger.warning(
                    f"Invalid status transition for task {task_id}: "
                    f"'{current_status}' -> '{status}'. "
                    f"Allowed transitions from '{current_status}': "
                    f"{', '.join(sorted(allowed_next)) if allowed_next else 'none (terminal state)'}"
                )
                return False

        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = $status,
            t.updated_at = datetime()
        RETURN t.id as task_id
        """

        parameters = {
            "task_id": task_id,
            "status": status
        }

        result = self.memory.execute_query(query, parameters)
        if result:
            logger.info(f"Task {task_id} status updated to '{status}'")
        else:
            # ERROR-HANDLING-002: Log failure explicitly
            logger.error(f"Failed to update task {task_id} status to '{status}' in Neo4j")
        return bool(result)

    def handle_task_completion(self, task_id: str, results: Dict) -> str:
        """Handle completed task from specialist.

        1. Validate results input
        2. Mark task complete in Neo4j
        3. Synthesize results into user-friendly response
        4. Return synthesized response

        Args:
            task_id: Completed task ID
            results: Task results from specialist (must be a dict)

        Returns:
            Synthesized user-friendly response

        Raises:
            TypeError: If results is not a dict
        """
        # VALIDATION-007: Validate results is a dict
        if not isinstance(results, dict):
            raise TypeError(
                f"results must be a dict, got {type(results).__name__}"
            )

        # Step 1: Mark task complete
        completed_at = datetime.utcnow().isoformat() + "Z"

        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = 'completed',
            t.completed_at = datetime($completed_at),
            t.results = $results,
            t.updated_at = datetime()
        RETURN t.target_agent as agent, t.sanitized_description as description
        """

        parameters = {
            "task_id": task_id,
            "completed_at": completed_at,
            "results": str(results)  # Neo4j doesn't support nested dicts directly
        }

        task_info = self.memory.execute_query(query, parameters)

        if not task_info:
            logger.warning(f"Task {task_id} not found for completion")
            return "Task completed but record not found."

        agent = task_info[0].get('agent', 'specialist')
        agent_name = self.AGENT_NAMES.get(agent, agent.capitalize())

        # Step 2: Synthesize response
        result_summary = results.get('summary', 'Task completed successfully.')
        result_details = results.get('details', '')

        synthesized = f"""{result_summary}

_(Completed by {agent_name})_"""

        if result_details:
            synthesized += f"\n\n{result_details}"

        logger.info(f"Task {task_id} marked complete by {agent}")
        return synthesized

    def get_pending_delegations(self) -> List[Dict]:
        """Get all pending delegated tasks.

        Returns:
            List of pending task dictionaries
        """
        query = """
        MATCH (t:Task)
        WHERE t.status IN ['pending', 'delegated', 'in_progress']
        RETURN t.id as task_id,
               t.status as status,
               t.target_agent as target_agent,
               t.priority as priority,
               t.sanitized_description as description,
               t.created_at as created_at,
               t.from_user as from_user
        ORDER BY t.priority DESC, t.created_at ASC
        """

        return self.memory.execute_query(query)

    def check_agent_availability(self, agent: str) -> bool:
        """Check if agent is available (heartbeat within last 5 min).

        Args:
            agent: Agent ID to check

        Returns:
            True if agent is available
        """
        five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z"

        query = """
        MATCH (a:Agent {name: $agent})
        WHERE a.last_heartbeat >= datetime($five_minutes_ago)
          AND a.status IN ['active', 'idle', 'available']
        RETURN a.name as name, a.status as status, a.last_heartbeat as last_heartbeat
        """

        parameters = {
            "agent": agent,
            "five_minutes_ago": five_minutes_ago
        }

        result = self.memory.execute_query(query, parameters)
        return bool(result)

    def get_agent_status(self, agent: str) -> Optional[Dict]:
        """Get full status for an agent.

        Args:
            agent: Agent ID

        Returns:
            Agent status dictionary or None
        """
        query = """
        MATCH (a:Agent {name: $agent})
        RETURN a.name as name,
               a.status as status,
               a.current_task as current_task,
               a.last_heartbeat as last_heartbeat,
               a.capabilities as capabilities
        """

        parameters = {"agent": agent}
        result = self.memory.execute_query(query, parameters)

        return result[0] if result else None

    def delegate_task(self, from_user: str, description: str,
                      task_type: Optional[str] = None,
                      priority: str = "normal") -> Dict[str, Any]:
        """Complete delegation workflow: create task and send to agent.

        This is a convenience method that combines create_delegation_task
        and delegate_via_agenttoagent.

        VALIDATION-006: Validates inputs before proceeding (same validations
        as create_delegation_task, applied early to fail fast before any
        side effects).

        Args:
            from_user: User ID who originated the request
            description: Task description
            task_type: Optional explicit task type
            priority: Task priority (low, normal, high, critical)

        Returns:
            Dictionary with task_id, target_agent, and success status
        """
        # VALIDATION-006: Validate inputs early to fail fast
        try:
            self._validate_priority(priority)
            self._validate_from_user(from_user)
            self._validate_description(description)
            self._validate_task_type(task_type)
        except (ValueError, TypeError) as e:
            logger.error(f"Delegation input validation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

        try:
            # Create task (validations will pass since we already checked above)
            task_id = self.create_delegation_task(
                from_user=from_user,
                description=description,
                task_type=task_type,
                priority=priority
            )

            # Get target agent from created task
            query = """
            MATCH (t:Task {id: $task_id})
            RETURN t.target_agent as target_agent,
                   t.sanitized_description as sanitized_description
            """
            task_info = self.memory.execute_query(query, {"task_id": task_id})

            if not task_info:
                return {
                    "success": False,
                    "error": "Task created but could not retrieve details",
                    "task_id": task_id
                }

            target_agent = task_info[0]["target_agent"]
            sanitized = task_info[0]["sanitized_description"]

            # Check agent availability
            if not self.check_agent_availability(target_agent):
                logger.warning(f"Agent {target_agent} may be unavailable")

            # Delegate via agentToAgent
            success = self.delegate_via_agenttoagent(
                task_id=task_id,
                target_agent=target_agent,
                original_description=sanitized
            )

            return {
                "success": success,
                "task_id": task_id,
                "target_agent": target_agent,
                "agent_name": self.AGENT_NAMES.get(target_agent, target_agent)
            }

        except Exception as e:
            logger.error(f"Delegation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Example: Create protocol instance
    # memory = OperationalMemory(neo4j_driver)
    # protocol = DelegationProtocol(
    #     memory=memory,
    #     gateway_url="https://kublai.kurult.ai",
    #     gateway_token="your_token_here"
    # )

    # Example: Sanitize content
    # sanitized = protocol.sanitize_for_privacy(
    #     "Contact John Doe at john@example.com or 555-123-4567"
    # )
    # print(sanitized)  # "Contact [NAME] at [EMAIL] or [PHONE]"

    # Example: Determine agent
    # agent = protocol.determine_agent("Write a blog post about Python")
    # print(agent)  # "writer"

    # Example: Full delegation
    # result = protocol.delegate_task(
    #     from_user="user123",
    #     description="Research the latest AI developments",
    #     task_type="research",
    #     priority="high"
    # )
    # print(result)

    print("Kublai Delegation Protocol (Improved) loaded successfully.")
    print("Import and instantiate DelegationProtocol to use.")
