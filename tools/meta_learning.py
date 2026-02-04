"""
Meta Learning Engine - Abstracting reflections into general rules for the OpenClaw system.

This module provides the MetaLearningEngine class for generating MetaRule nodes from
reflections, tracking rule effectiveness, managing Kublai approval workflow, and
versioning rules with REPLACED_BY relationships.

Named after the meta-learning capabilities that enable the system to abstract
specific mistakes into general principles that improve agent behavior over time.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from neo4j.exceptions import Neo4jError

# Configure logging
logger = logging.getLogger(__name__)


class MetaRuleNotFoundError(Exception):
    """Raised when a MetaRule ID is not found."""
    pass


class MetaRuleError(Exception):
    """Raised when a MetaRule operation fails."""
    pass


class MetaLearningEngine:
    """
    Meta-learning engine for generating and managing MetaRules.

    Provides capabilities for:
    - Generating MetaRules from reflections
    - Abstracting common patterns from multiple reflections
    - Tracking rule effectiveness (success_count, application_count)
    - Kublai approval workflow for rules
    - Rule versioning with REPLACED_BY relationships
    - Queueing SOUL file updates

    Attributes:
        memory: OperationalMemory instance for persistence
        reflection_memory: AgentReflectionMemory instance for accessing reflections
        min_reflections_for_rule: Minimum reflections needed to generate a rule
        default_rule_confidence: Default confidence threshold for rule application
    """

    # Valid rule types
    VALID_RULE_TYPES = ["absolute", "guideline", "conditional"]

    def __init__(
        self,
        memory: Any,  # OperationalMemory
        reflection_memory: Any,  # AgentReflectionMemory
        min_reflections_for_rule: int = 3,
        default_rule_confidence: float = 0.7
    ):
        """
        Initialize the MetaLearningEngine.

        Args:
            memory: OperationalMemory instance for Neo4j persistence
            reflection_memory: AgentReflectionMemory instance for reflections
            min_reflections_for_rule: Minimum reflections to generate a rule
            default_rule_confidence: Default confidence threshold for rules
        """
        self.memory = memory
        self.reflection_memory = reflection_memory
        self.min_reflections_for_rule = min_reflections_for_rule
        self.default_rule_confidence = default_rule_confidence

        logger.info(
            f"MetaLearningEngine initialized with min_reflections_for_rule={min_reflections_for_rule}, "
            f"default_rule_confidence={default_rule_confidence}"
        )

    def _generate_id(self) -> str:
        """Generate a unique ID using the memory's method or fallback to uuid."""
        if hasattr(self.memory, '_generate_id'):
            return self.memory._generate_id()
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime using the memory's method or fallback."""
        if hasattr(self.memory, '_now'):
            return self.memory._now()
        return datetime.now(timezone.utc)

    def _session(self):
        """Get Neo4j session context manager from memory."""
        if hasattr(self.memory, '_session'):
            return self.memory._session()
        # Fallback - return a no-op context manager
        from contextlib import nullcontext
        return nullcontext(None)

    def generate_metarule_from_reflections(
        self,
        reflection_ids: List[str]
    ) -> str:
        """
        Generate a MetaRule from a list of reflections.

        Analyzes the reflections to extract common patterns and generates
        a rule in the format:
        - Absolute directive (NEVER/ALWAYS)
        - 1-3 bullet point explanations
        - Concrete example

        Args:
            reflection_ids: List of reflection IDs to analyze

        Returns:
            Generated rule content string

        Raises:
            MetaRuleError: If insufficient reflections or generation fails
        """
        if len(reflection_ids) < self.min_reflections_for_rule:
            raise MetaRuleError(
                f"Insufficient reflections for rule generation. "
                f"Need {self.min_reflections_for_rule}, got {len(reflection_ids)}"
            )

        # Get reflection data
        reflections = []
        for rid in reflection_ids:
            ref = self.reflection_memory.get_reflection(rid)
            if ref:
                reflections.append(ref)

        if len(reflections) < self.min_reflections_for_rule:
            raise MetaRuleError(
                f"Only {len(reflections)} valid reflections found, "
                f"need {self.min_reflections_for_rule}"
            )

        # Abstract pattern from reflections
        rule_content = self.abstract_pattern(reflections)

        logger.info(
            f"Generated MetaRule from {len(reflections)} reflections: "
            f"{rule_content[:100]}..."
        )

        return rule_content

    def abstract_pattern(self, reflections: List[Dict]) -> str:
        """
        Abstract a common pattern from a list of reflections.

        Analyzes reflections to identify common themes and generates
        a rule following the format:
        - Absolute directive
        - Explanation bullet points
        - Concrete example

        Args:
            reflections: List of reflection dicts

        Returns:
            Rule content string
        """
        # Group by mistake type
        by_type: Dict[str, List[Dict]] = {}
        for reflection in reflections:
            mtype = reflection.get("mistake_type", "other")
            if mtype not in by_type:
                by_type[mtype] = []
            by_type[mtype].append(reflection)

        # Determine the dominant mistake type
        dominant_type = max(by_type.keys(), key=lambda k: len(by_type[k]))
        dominant_reflections = by_type[dominant_type]

        # Extract common patterns
        lessons = [r.get("lesson", "") for r in dominant_reflections]
        root_causes = [r.get("root_cause", "") for r in dominant_reflections]
        contexts = [r.get("context", "") for r in dominant_reflections]

        # Generate rule based on mistake type
        if dominant_type == "security":
            rule = self._generate_security_rule(lessons, root_causes, contexts)
        elif dominant_type == "logic":
            rule = self._generate_logic_rule(lessons, root_causes, contexts)
        elif dominant_type == "error":
            rule = self._generate_error_handling_rule(lessons, root_causes, contexts)
        elif dominant_type == "communication":
            rule = self._generate_communication_rule(lessons, root_causes, contexts)
        else:
            rule = self._generate_generic_rule(lessons, root_causes, contexts)

        return rule

    def _generate_security_rule(
        self,
        lessons: List[str],
        root_causes: List[str],
        contexts: List[str]
    ) -> str:
        """Generate a security-focused rule."""
        # Extract common security keywords
        all_text = " ".join(lessons + root_causes).lower()

        if "password" in all_text or "credential" in all_text:
            directive = "NEVER store or log passwords, API keys, or credentials in plaintext."
            explanations = [
                "Always use environment variables or secure vaults for secrets",
                "Hash passwords using bcrypt or Argon2 before storage"
            ]
            example = "Use os.environ.get('API_KEY') instead of hardcoding credentials."
        elif "input" in all_text or "sanitize" in all_text or "escape" in all_text:
            directive = "ALWAYS validate and sanitize user input before processing."
            explanations = [
                "Use parameterized queries to prevent injection attacks",
                "Validate input type, length, and format against expected schema"
            ]
            example = "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))"
        elif "eval" in all_text or "exec" in all_text:
            directive = "NEVER use eval() or exec() on untrusted/user input."
            explanations = [
                "Use ast.literal_eval() for safe evaluation of literals",
                "Implement proper parsing for dynamic code execution needs"
            ]
            example = "Use json.loads() for parsing JSON instead of eval(json_string)."
        else:
            directive = "ALWAYS apply defense-in-depth for security-critical operations."
            explanations = [
                "Validate at multiple layers (input, processing, output)",
                "Use principle of least privilege for all operations"
            ]
            example = "Check permissions both in middleware and at the data access layer."

        return self._format_rule(directive, explanations, example)

    def _generate_logic_rule(
        self,
        lessons: List[str],
        root_causes: List[str],
        contexts: List[str]
    ) -> str:
        """Generate a logic-focused rule."""
        all_text = " ".join(lessons + root_causes).lower()

        if "null" in all_text or "none" in all_text or "undefined" in all_text:
            directive = "ALWAYS check for null/None values before dereferencing."
            explanations = [
                "Use optional chaining or explicit null checks",
                "Fail fast with clear error messages for missing required values"
            ]
            example = "Use value?.property or if value is not None: value.property"
        elif "race" in all_text or "concurrent" in all_text or "thread" in all_text:
            directive = "ALWAYS use proper synchronization for shared state access."
            explanations = [
                "Use locks, semaphores, or atomic operations as appropriate",
                "Minimize critical section size to reduce contention"
            ]
            example = "Use with threading.Lock(): when modifying shared counters."
        else:
            directive = "ALWAYS validate assumptions with assertions or explicit checks."
            explanations = [
                "Document preconditions and postconditions",
                "Use type hints and runtime validation where needed"
            ]
            example = "assert user_id is not None, 'user_id is required for this operation'"

        return self._format_rule(directive, explanations, example)

    def _generate_error_handling_rule(
        self,
        lessons: List[str],
        root_causes: List[str],
        contexts: List[str]
    ) -> str:
        """Generate an error handling rule."""
        directive = "ALWAYS handle errors explicitly and provide meaningful messages."
        explanations = [
            "Catch specific exceptions, not generic Exception",
            "Log errors with sufficient context for debugging"
        ]
        example = """
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Invalid input to risky_operation: {e}")
    raise UserError("Invalid input provided")
        """.strip()

        return self._format_rule(directive, explanations, example)

    def _generate_communication_rule(
        self,
        lessons: List[str],
        root_causes: List[str],
        contexts: List[str]
    ) -> str:
        """Generate a communication-focused rule."""
        directive = "ALWAYS communicate intent clearly and confirm understanding."
        explanations = [
            "Document the 'why' not just the 'what'",
            "Confirm requirements before implementing complex features"
        ]
        example = "Add comments explaining business logic, not just describing code."

        return self._format_rule(directive, explanations, example)

    def _generate_generic_rule(
        self,
        lessons: List[str],
        root_causes: List[str],
        contexts: List[str]
    ) -> str:
        """Generate a generic rule when no specific pattern matches."""
        # Extract most common words from lessons
        all_lessons = " ".join(lessons).lower()
        words = [w for w in all_lessons.split() if len(w) > 4]
        word_counts = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

        # Get top themes
        top_themes = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        themes = [t[0] for t in top_themes]

        directive = f"ALWAYS review code for issues related to: {', '.join(themes)}."
        explanations = [
            "Learn from past mistakes documented in reflections",
            "Apply lessons consistently across similar contexts"
        ]
        example = "Before committing, verify against reflection history for similar issues."

        return self._format_rule(directive, explanations, example)

    def _format_rule(
        self,
        directive: str,
        explanations: List[str],
        example: str
    ) -> str:
        """Format a rule with directive, explanations, and example."""
        lines = [directive, ""]
        lines.append("Explanation:")
        for exp in explanations[:3]:  # Max 3 explanations
            lines.append(f"- {exp}")
        lines.append("")
        lines.append(f"Example: {example}")

        return "\n".join(lines)

    def create_metarule(
        self,
        rule_content: str,
        rule_type: str,
        source_reflections: List[str]
    ) -> str:
        """
        Create a MetaRule node in Neo4j.

        Args:
            rule_content: The rule text content
            rule_type: Type of rule (absolute/guideline/conditional)
            source_reflections: List of reflection IDs that generated this rule

        Returns:
            MetaRule ID string

        Raises:
            ValueError: If rule_type is invalid
            MetaRuleError: If creation fails
        """
        if rule_type not in self.VALID_RULE_TYPES:
            raise ValueError(
                f"Invalid rule_type '{rule_type}'. "
                f"Must be one of: {self.VALID_RULE_TYPES}"
            )

        rule_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (m:MetaRule {
            id: $rule_id,
            rule_content: $rule_content,
            rule_type: $rule_type,
            source_reflections: $source_reflections,
            success_count: 0,
            application_count: 0,
            effectiveness_score: 0.0,
            approved: false,
            approved_by: null,
            approved_at: null,
            version: 1,
            created_at: $created_at
        })
        RETURN m.id as rule_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule creation simulated")
                return rule_id

            try:
                result = session.run(
                    cypher,
                    rule_id=rule_id,
                    rule_content=rule_content,
                    rule_type=rule_type,
                    source_reflections=source_reflections,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"MetaRule created: {rule_id} (type: {rule_type})")
                    return record["rule_id"]
                else:
                    raise MetaRuleError("MetaRule creation failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to create MetaRule: {e}")
                raise MetaRuleError(f"Failed to create MetaRule: {e}")

    def approve_metarule(
        self,
        rule_id: str,
        approved_by: str
    ) -> bool:
        """
        Approve a MetaRule (Kublai action).

        Args:
            rule_id: ID of the rule to approve
            approved_by: Agent who approved the rule

        Returns:
            True if approval successful

        Raises:
            MetaRuleNotFoundError: If rule ID not found
            MetaRuleError: If approval fails
        """
        approved_at = self._now()

        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        SET m.approved = true,
            m.approved_by = $approved_by,
            m.approved_at = $approved_at
        RETURN m.id as rule_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule approval simulated for {rule_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    rule_id=rule_id,
                    approved_by=approved_by,
                    approved_at=approved_at
                )
                record = result.single()

                if record is None:
                    raise MetaRuleNotFoundError(f"MetaRule not found: {rule_id}")

                logger.info(f"MetaRule approved: {rule_id} by {approved_by}")

                # Create notification for the approving agent
                if hasattr(self.memory, 'create_notification'):
                    self.memory.create_notification(
                        agent=approved_by,
                        type="metarule_approved",
                        summary=f"MetaRule approved and ready for propagation: {rule_id[:8]}...",
                        task_id=None
                    )

                return True

            except Neo4jError as e:
                logger.error(f"Failed to approve MetaRule: {e}")
                raise MetaRuleError(f"Failed to approve MetaRule: {e}")

    def apply_metarule(
        self,
        rule_id: str,
        outcome_success: bool
    ) -> bool:
        """
        Record a MetaRule application outcome.

        Updates success_count and application_count, recalculates effectiveness_score.

        Args:
            rule_id: ID of the rule that was applied
            outcome_success: Whether the application was successful

        Returns:
            True if update successful

        Raises:
            MetaRuleNotFoundError: If rule ID not found
            MetaRuleError: If update fails
        """
        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        SET m.application_count = m.application_count + 1,
            m.success_count = CASE WHEN $outcome_success
                THEN m.success_count + 1
                ELSE m.success_count
            END,
            m.effectiveness_score = CASE WHEN $outcome_success
                THEN (m.success_count + 1.0) / (m.application_count + 1.0)
                ELSE m.success_count / (m.application_count + 1.0)
            END
        RETURN m.id as rule_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule application simulated for {rule_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    rule_id=rule_id,
                    outcome_success=outcome_success
                )
                record = result.single()

                if record is None:
                    raise MetaRuleNotFoundError(f"MetaRule not found: {rule_id}")

                logger.debug(
                    f"MetaRule application recorded: {rule_id}, "
                    f"success={outcome_success}"
                )
                return True

            except Neo4jError as e:
                logger.error(f"Failed to record MetaRule application: {e}")
                raise MetaRuleError(f"Failed to record MetaRule application: {e}")

    def get_applicable_rules(
        self,
        agent: Optional[str] = None,
        min_confidence: Optional[float] = None
    ) -> List[Dict]:
        """
        Get MetaRules applicable to an agent.

        Returns approved rules that meet the confidence threshold.

        Args:
            agent: Optional agent filter
            min_confidence: Minimum effectiveness score (uses default if None)

        Returns:
            List of MetaRule dicts
        """
        confidence_threshold = min_confidence or self.default_rule_confidence

        cypher = """
        MATCH (m:MetaRule)
        WHERE m.approved = true
        AND m.effectiveness_score >= $confidence_threshold
        RETURN m
        ORDER BY m.effectiveness_score DESC, m.application_count DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, confidence_threshold=confidence_threshold)
                rules = []
                for record in result:
                    rule = dict(record["m"])
                    rules.append(rule)
                return rules
            except Neo4jError as e:
                logger.error(f"Failed to get applicable rules: {e}")
                return []

    def get_rule_effectiveness(self, rule_id: str) -> Dict:
        """
        Get effectiveness metrics for a MetaRule.

        Args:
            rule_id: ID of the rule

        Returns:
            Dict with effectiveness metrics

        Raises:
            MetaRuleNotFoundError: If rule ID not found
        """
        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        RETURN m.success_count as success_count,
               m.application_count as application_count,
               m.effectiveness_score as effectiveness_score
        """

        with self._session() as session:
            if session is None:
                return {
                    "rule_id": rule_id,
                    "success_count": 0,
                    "application_count": 0,
                    "effectiveness_score": 0.0
                }

            try:
                result = session.run(cypher, rule_id=rule_id)
                record = result.single()

                if record is None:
                    raise MetaRuleNotFoundError(f"MetaRule not found: {rule_id}")

                return {
                    "rule_id": rule_id,
                    "success_count": record["success_count"],
                    "application_count": record["application_count"],
                    "effectiveness_score": record["effectiveness_score"]
                }

            except Neo4jError as e:
                logger.error(f"Failed to get rule effectiveness: {e}")
                raise MetaRuleError(f"Failed to get rule effectiveness: {e}")

    def update_rule_version(
        self,
        old_rule_id: str,
        new_rule_content: str,
        reason: str
    ) -> str:
        """
        Create a new version of a MetaRule.

        Creates a new rule node and adds REPLACED_BY relationship from old to new.

        Args:
            old_rule_id: ID of the rule being replaced
            new_rule_content: Content for the new rule version
            reason: Reason for the replacement

        Returns:
            New rule ID

        Raises:
            MetaRuleNotFoundError: If old rule ID not found
            MetaRuleError: If versioning fails
        """
        # Get old rule data
        old_rule = self._get_metarule(old_rule_id)
        if old_rule is None:
            raise MetaRuleNotFoundError(f"MetaRule not found: {old_rule_id}")

        # Create new rule with incremented version
        new_rule_id = self._generate_id()
        created_at = self._now()
        new_version = old_rule.get("version", 1) + 1

        cypher_create = """
        CREATE (m:MetaRule {
            id: $rule_id,
            rule_content: $rule_content,
            rule_type: $rule_type,
            source_reflections: $source_reflections,
            success_count: 0,
            application_count: 0,
            effectiveness_score: 0.0,
            approved: false,
            approved_by: null,
            approved_at: null,
            version: $version,
            created_at: $created_at,
            replaces_rule: $old_rule_id
        })
        RETURN m.id as rule_id
        """

        cypher_relate = """
        MATCH (old:MetaRule {id: $old_rule_id})
        MATCH (new:MetaRule {id: $new_rule_id})
        CREATE (old)-[r:REPLACED_BY {
            reason: $reason,
            replaced_at: $replaced_at
        }]->(new)
        RETURN r
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Rule versioning simulated")
                return new_rule_id

            try:
                # Create new rule
                result = session.run(
                    cypher_create,
                    rule_id=new_rule_id,
                    rule_content=new_rule_content,
                    rule_type=old_rule.get("rule_type", "guideline"),
                    source_reflections=old_rule.get("source_reflections", []),
                    version=new_version,
                    created_at=created_at,
                    old_rule_id=old_rule_id
                )
                record = result.single()
                if not record:
                    raise MetaRuleError("New rule creation failed")

                # Create REPLACED_BY relationship
                session.run(
                    cypher_relate,
                    old_rule_id=old_rule_id,
                    new_rule_id=new_rule_id,
                    reason=reason,
                    replaced_at=created_at
                )

                logger.info(
                    f"MetaRule versioned: {old_rule_id} -> {new_rule_id} "
                    f"(version {new_version})"
                )
                return new_rule_id

            except Neo4jError as e:
                logger.error(f"Failed to version MetaRule: {e}")
                raise MetaRuleError(f"Failed to version MetaRule: {e}")

    def _get_metarule(self, rule_id: str) -> Optional[Dict]:
        """Get a MetaRule by ID (internal method)."""
        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        RETURN m
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, rule_id=rule_id)
                record = result.single()
                return dict(record["m"]) if record else None
            except Neo4jError:
                return None

    def queue_soul_update(
        self,
        agent: str,
        rule_id: str
    ) -> bool:
        """
        Queue a SOUL file update for an agent.

        Creates a notification or task for updating the agent's SOUL file
        with an approved MetaRule.

        Args:
            agent: Agent whose SOUL file should be updated
            rule_id: ID of the approved rule to add

        Returns:
            True if queued successfully

        Raises:
            MetaRuleNotFoundError: If rule ID not found
            MetaRuleError: If queuing fails
        """
        # Verify rule exists and is approved
        rule = self._get_metarule(rule_id)
        if rule is None:
            raise MetaRuleNotFoundError(f"MetaRule not found: {rule_id}")

        if not rule.get("approved", False):
            raise MetaRuleError(f"Cannot queue unapproved rule: {rule_id}")

        # Create notification for the agent
        if hasattr(self.memory, 'create_notification'):
            try:
                self.memory.create_notification(
                    agent=agent,
                    type="soul_update_required",
                    summary=f"Update SOUL file with new MetaRule: {rule['rule_content'][:50]}...",
                    task_id=None,
                    data={
                        "rule_id": rule_id,
                        "rule_content": rule.get("rule_content", ""),
                        "rule_type": rule.get("rule_type", "guideline")
                    }
                )
                logger.info(f"SOUL update queued for {agent}: rule {rule_id[:8]}...")
                return True
            except Exception as e:
                logger.error(f"Failed to queue SOUL update: {e}")
                raise MetaRuleError(f"Failed to queue SOUL update: {e}")
        else:
            logger.warning("Memory does not support create_notification")
            return False

    def consolidate_reflections_and_generate_rules(
        self,
        agent: Optional[str] = None
    ) -> Dict:
        """
        Full consolidation pipeline: reflections -> MetaRules.

        1. Consolidates unconsolidated reflections
        2. Generates MetaRules from consolidated reflections
        3. Returns summary of actions taken

        Args:
            agent: Optional agent filter

        Returns:
            Dict with pipeline results
        """
        results = {
            "reflections_consolidated": 0,
            "rules_generated": 0,
            "rule_ids": [],
            "errors": []
        }

        try:
            # Step 1: Consolidate reflections
            consolidation = self.reflection_memory.consolidate_reflections(agent=agent)

            if not consolidation.get("consolidated", False):
                results["message"] = consolidation.get("reason", "No reflections to consolidate")
                return results

            results["reflections_consolidated"] = consolidation.get("reflections_processed", 0)
            reflection_ids = consolidation.get("reflection_ids", [])

            # Step 2: Check if we have enough reflections for a rule
            if len(reflection_ids) < self.min_reflections_for_rule:
                results["message"] = (
                    f"Insufficient reflections for rule generation "
                    f"({len(reflection_ids)}/{self.min_reflections_for_rule})"
                )
                return results

            # Step 3: Generate rule from reflections
            try:
                rule_content = self.generate_metarule_from_reflections(reflection_ids)

                # Determine rule type based on content analysis
                rule_type = self._determine_rule_type(rule_content)

                # Create the MetaRule
                rule_id = self.create_metarule(
                    rule_content=rule_content,
                    rule_type=rule_type,
                    source_reflections=reflection_ids
                )

                results["rules_generated"] = 1
                results["rule_ids"].append(rule_id)
                results["message"] = "Successfully generated MetaRule from reflections"

                # Create notification for Kublai about pending approval
                if hasattr(self.memory, 'create_notification'):
                    self.memory.create_notification(
                        agent="main",  # Kublai
                        type="metarule_pending_approval",
                        summary=f"New MetaRule pending approval: {rule_content[:50]}...",
                        task_id=None,
                        data={"rule_id": rule_id, "rule_type": rule_type}
                    )

            except MetaRuleError as e:
                results["errors"].append(str(e))
                results["message"] = f"Rule generation failed: {e}"

        except Exception as e:
            results["errors"].append(str(e))
            results["message"] = f"Consolidation failed: {e}"

        return results

    def _determine_rule_type(self, rule_content: str) -> str:
        """Determine rule type based on content analysis."""
        content_lower = rule_content.lower()

        # Check for absolute keywords
        if content_lower.startswith("never ") or content_lower.startswith("always "):
            return "absolute"

        # Check for conditional keywords
        if "if " in content_lower or "when " in content_lower or "unless " in content_lower:
            return "conditional"

        # Default to guideline
        return "guideline"

    def list_metarules(
        self,
        approved: Optional[bool] = None,
        rule_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        List MetaRules with optional filters.

        Args:
            approved: Filter by approval status
            rule_type: Filter by rule type
            limit: Maximum number of rules to return

        Returns:
            List of MetaRule dicts
        """
        conditions = []
        params = {"limit": limit}

        if approved is not None:
            conditions.append("m.approved = $approved")
            params["approved"] = approved

        if rule_type is not None:
            conditions.append("m.rule_type = $rule_type")
            params["rule_type"] = rule_type

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (m:MetaRule)
        {where_clause}
        RETURN m
        ORDER BY m.effectiveness_score DESC, m.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["m"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to list MetaRules: {e}")
                return []

    def get_rule_history(self, rule_id: str) -> List[Dict]:
        """
        Get version history for a MetaRule.

        Follows REPLACED_BY relationships to build version chain.

        Args:
            rule_id: Current rule ID

        Returns:
            List of rule versions (oldest first)
        """
        # First check if this rule replaced another
        cypher = """
        MATCH (old:MetaRule)-[r:REPLACED_BY]->(new:MetaRule {id: $rule_id})
        RETURN old, r
        """

        history = []

        with self._session() as session:
            if session is None:
                return history

            try:
                # Walk backwards through the chain
                current_id = rule_id
                chain = []

                while True:
                    result = session.run(cypher, rule_id=current_id)
                    record = result.single()

                    if record is None:
                        break

                    old_rule = dict(record["old"])
                    relationship = dict(record["r"])
                    chain.append({
                        "rule": old_rule,
                        "replaced_by_reason": relationship.get("reason", ""),
                        "replaced_at": relationship.get("replaced_at")
                    })
                    current_id = old_rule["id"]

                # Reverse to get oldest first
                chain.reverse()

                # Add current rule
                current_rule = self._get_metarule(rule_id)
                if current_rule:
                    chain.append({"rule": current_rule})

                return chain

            except Neo4jError as e:
                logger.error(f"Failed to get rule history: {e}")
                return []

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for MetaRule tracking.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX metarule_id_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.id)", "metarule_id_idx"),
            ("CREATE INDEX metarule_approved_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.approved)", "metarule_approved_idx"),
            ("CREATE INDEX metarule_type_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.rule_type)", "metarule_type_idx"),
            ("CREATE INDEX metarule_version_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.version)", "metarule_version_idx"),
            ("CREATE INDEX metarule_created_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.created_at)", "metarule_created_idx"),
            ("CREATE INDEX metarule_effectiveness_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.effectiveness_score)", "metarule_effectiveness_idx"),
        ]

        created = []

        with self._session() as session:
            if session is None:
                logger.warning("Cannot create indexes: Neo4j unavailable")
                return created

            for cypher, name in indexes:
                try:
                    session.run(cypher)
                    created.append(name)
                    logger.info(f"Created index: {name}")
                except Neo4jError as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Failed to create index {name}: {e}")

        return created


# =============================================================================
# Convenience Functions
# =============================================================================

def create_meta_learning_engine(
    memory: Any,
    reflection_memory: Any,
    min_reflections_for_rule: int = 3,
    default_rule_confidence: float = 0.7
) -> MetaLearningEngine:
    """
    Create a MetaLearningEngine instance.

    Args:
        memory: OperationalMemory instance
        reflection_memory: AgentReflectionMemory instance
        min_reflections_for_rule: Minimum reflections to generate a rule
        default_rule_confidence: Default confidence threshold

    Returns:
        MetaLearningEngine instance
    """
    return MetaLearningEngine(
        memory=memory,
        reflection_memory=reflection_memory,
        min_reflections_for_rule=min_reflections_for_rule,
        default_rule_confidence=default_rule_confidence
    )


def generate_and_create_metarule(
    engine: MetaLearningEngine,
    reflection_ids: List[str],
    rule_type: str = "guideline"
) -> str:
    """
    Generate and create a MetaRule from reflections.

    Args:
        engine: MetaLearningEngine instance
        reflection_ids: List of reflection IDs
        rule_type: Type of rule to create

    Returns:
        MetaRule ID
    """
    rule_content = engine.generate_metarule_from_reflections(reflection_ids)
    return engine.create_metarule(rule_content, rule_type, reflection_ids)


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage (requires OperationalMemory and AgentReflectionMemory)
    print("MetaLearningEngine - Example Usage")
    print("=" * 50)

    print("""
    from openclaw_memory import OperationalMemory
    from tools.reflection_memory import AgentReflectionMemory
    from tools.meta_learning import MetaLearningEngine

    # Initialize
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password"
    ) as memory:

        # Create reflection memory and meta learning engine
        reflection_memory = AgentReflectionMemory(memory=memory)
        meta_engine = MetaLearningEngine(
            memory=memory,
            reflection_memory=reflection_memory
        )

        # Create indexes
        meta_engine.create_indexes()

        # Generate MetaRule from reflections
        rule_content = meta_engine.generate_metarule_from_reflections([
            "ref-1", "ref-2", "ref-3"
        ])

        # Create the MetaRule
        rule_id = meta_engine.create_metarule(
            rule_content=rule_content,
            rule_type="absolute",
            source_reflections=["ref-1", "ref-2", "ref-3"]
        )

        # Kublai approves the rule
        meta_engine.approve_metarule(rule_id, approved_by="main")

        # Record rule application
        meta_engine.apply_metarule(rule_id, outcome_success=True)

        # Get applicable rules
        rules = meta_engine.get_applicable_rules(min_confidence=0.7)

        # Version a rule
        new_rule_id = meta_engine.update_rule_version(
            old_rule_id=rule_id,
            new_rule_content="Updated rule content...",
            reason="Clarified based on edge case feedback"
        )

        # Queue SOUL update
        meta_engine.queue_soul_update(agent="developer", rule_id=rule_id)

        # Run full consolidation pipeline
        results = meta_engine.consolidate_reflections_and_generate_rules()
    """)
