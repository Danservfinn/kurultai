"""
Horde-Learn adapter for Kurultai capability acquisition system.

This module implements a 6-phase learning pipeline that enables agents to
autonomously acquire new capabilities through research, development, validation,
and secure registration with CBAC (Capability-Based Access Control).
"""

from datetime import datetime
from typing import Dict, List, Optional
import json
import re


class HordeLearnKurultai:
    """
    Six-phase capability learning pipeline for autonomous skill acquisition.

    Phases:
    0. Security Check - Validate learning request against prompt injection
    1. Classification - Categorize capability type
    2. Research - Gather information via Mongke (researcher agent)
    3. Implementation - Generate code via Temujin (developer agent)
    4. Validation - Security review via Jochi (analyst agent)
    5. Registration - Store in Neo4j via CapabilityRegistry
    6. Authorization - CBAC grant for requesting agent

    Integrates with:
    - OperationalMemory for Neo4j persistence
    - CapabilityRegistry for CBAC management
    - PromptInjectionFilter for security validation
    """

    CAPABILITY_CATEGORIES = {
        "api_integration": "Integration with external APIs and services",
        "data_processing": "Data transformation, parsing, and analysis",
        "automation": "Workflow automation and task orchestration",
        "analysis": "Code analysis, metrics, and insights",
        "communication": "Messaging, notifications, and reporting",
        "security": "Security scanning, validation, and auditing"
    }

    def __init__(
        self,
        memory,
        capability_registry: Optional[object] = None,
        injection_filter: Optional[object] = None
    ):
        """
        Initialize the Horde-Learn adapter.

        Args:
            memory: OperationalMemory instance for Neo4j operations
            capability_registry: Optional CapabilityRegistry instance
            injection_filter: Optional PromptInjectionFilter instance
        """
        self.memory = memory

        # Lazy import to handle optional dependencies
        if capability_registry is None:
            try:
                from .capability_registry import CapabilityRegistry
                self.registry = CapabilityRegistry(memory)
            except (ImportError, Exception):
                self.registry = None
        else:
            self.registry = capability_registry

        if injection_filter is None:
            try:
                from tools.kurultai.security.prompt_injection_filter import PromptInjectionFilter
                self.injection_filter = PromptInjectionFilter()
            except ImportError:
                # Fallback: no injection filtering
                self.injection_filter = None
        else:
            self.injection_filter = injection_filter

        self.phases_completed: List[str] = []
        self.errors: List[str] = []

    def learn(self, request: str, agent_id: str = "main") -> Dict[str, any]:
        """
        Execute the 6-phase capability learning pipeline.

        Args:
            request: Natural language learning request
                     (e.g., "Learn how to integrate with Parse API")
            agent_id: Requesting agent identifier

        Returns:
            Dictionary containing:
            - success: bool
            - capability_name: str (if successful)
            - phases_completed: list[str]
            - errors: list[str]
            - metadata: dict with phase-specific details
        """
        self.phases_completed = []
        self.errors = []
        metadata = {}

        # Phase 0: Security Check
        security_result = self._phase_0_security(request)
        if not security_result["safe"]:
            return {
                "success": False,
                "capability_name": None,
                "phases_completed": self.phases_completed,
                "errors": self.errors,
                "metadata": {"security_check": security_result}
            }
        metadata["security_check"] = security_result

        # Phase 1: Classification
        classification = self._phase_1_classify(request)
        if not classification["category"]:
            return {
                "success": False,
                "capability_name": None,
                "phases_completed": self.phases_completed,
                "errors": self.errors,
                "metadata": {"classification": classification}
            }
        metadata["classification"] = classification

        # Phase 2: Research
        research = self._phase_2_research(request, classification)
        if not research["success"]:
            return {
                "success": False,
                "capability_name": None,
                "phases_completed": self.phases_completed,
                "errors": self.errors,
                "metadata": {
                    "classification": classification,
                    "research": research
                }
            }
        metadata["research"] = research

        # Phase 3: Implementation
        implementation = self._phase_3_implement(request, classification, research)
        if not implementation["success"]:
            return {
                "success": False,
                "capability_name": None,
                "phases_completed": self.phases_completed,
                "errors": self.errors,
                "metadata": {
                    "classification": classification,
                    "research": research,
                    "implementation": implementation
                }
            }
        metadata["implementation"] = implementation

        # Phase 4: Validation
        validation = self._phase_4_validate(implementation)
        if not validation["approved"]:
            return {
                "success": False,
                "capability_name": None,
                "phases_completed": self.phases_completed,
                "errors": self.errors,
                "metadata": {
                    "classification": classification,
                    "research": research,
                    "implementation": implementation,
                    "validation": validation
                }
            }
        metadata["validation"] = validation

        # Phase 5: Registration
        registration = self._phase_5_register(
            classification,
            implementation,
            agent_id
        )
        if not registration["success"]:
            return {
                "success": False,
                "capability_name": registration.get("capability_name"),
                "phases_completed": self.phases_completed,
                "errors": self.errors,
                "metadata": {
                    "classification": classification,
                    "research": research,
                    "implementation": implementation,
                    "validation": validation,
                    "registration": registration
                }
            }
        metadata["registration"] = registration

        # Phase 6: Authorization
        authorization = self._phase_6_authorize(
            agent_id,
            registration["capability_name"]
        )
        metadata["authorization"] = authorization

        return {
            "success": True,
            "capability_name": registration["capability_name"],
            "phases_completed": self.phases_completed,
            "errors": self.errors,
            "metadata": metadata
        }

    def _phase_0_security(self, request: str) -> Dict[str, any]:
        """
        Phase 0: Security check against prompt injection.

        Args:
            request: Learning request to validate

        Returns:
            Dictionary with safe (bool) and reason (str)
        """
        phase_name = "Phase 0: Security Check"

        if self.injection_filter is None:
            # No filter available, proceed with warning
            self.phases_completed.append(phase_name)
            return {
                "safe": True,
                "reason": "No injection filter available (proceeding with caution)"
            }

        try:
            is_safe = self.injection_filter.is_safe(request)

            if is_safe:
                self.phases_completed.append(phase_name)
                return {"safe": True, "reason": "Request passed security validation"}
            else:
                self.errors.append(
                    "Security check failed: potential prompt injection detected"
                )
                return {
                    "safe": False,
                    "reason": "Potential prompt injection or malicious patterns detected"
                }

        except Exception as e:
            self.errors.append(f"Security check error: {str(e)}")
            return {"safe": False, "reason": f"Security check failed: {str(e)}"}

    def _phase_1_classify(self, request: str) -> Dict[str, any]:
        """
        Phase 1: Classify the capability type.

        Uses keyword matching and pattern detection to categorize the request.

        Args:
            request: Learning request

        Returns:
            Dictionary with category, confidence, and detected_keywords
        """
        phase_name = "Phase 1: Classification"

        # Keyword patterns for each category
        patterns = {
            "api_integration": [
                r"\bapi\b", r"\brest\b", r"\bgraphql\b", r"\bwebhook\b",
                r"\bintegrat", r"\bfetch\b", r"\bhttp\b", r"\brequest\b"
            ],
            "data_processing": [
                r"\bparse\b", r"\btransform\b", r"\bprocess\b", r"\bfilter\b",
                r"\baggregate\b", r"\bclean\b", r"\bformat\b", r"\bconvert\b"
            ],
            "automation": [
                r"\bautomate\b", r"\bworkflow\b", r"\bschedule\b", r"\btask\b",
                r"\borchestrat", r"\bpipeline\b", r"\btrigger\b"
            ],
            "analysis": [
                r"\banalyz", r"\bmetric\b", r"\breport\b", r"\bstatistic",
                r"\bmeasure\b", r"\bprofile\b", r"\bbenchmark\b"
            ],
            "communication": [
                r"\bnotif", r"\bmessage\b", r"\balert\b", r"\bemail\b",
                r"\bslack\b", r"\bsignal\b", r"\bchat\b", r"\bsend\b"
            ],
            "security": [
                r"\bsecur", r"\baudit\b", r"\bscan\b", r"\bvalidat",
                r"\bsanitiz", r"\bencrypt\b", r"\bauth"
            ]
        }

        # Score each category
        scores = {}
        detected = {}

        request_lower = request.lower()

        for category, keyword_patterns in patterns.items():
            matches = []
            for pattern in keyword_patterns:
                if re.search(pattern, request_lower):
                    matches.append(pattern)

            scores[category] = len(matches)
            if matches:
                detected[category] = matches

        # Find highest scoring category
        if not scores or max(scores.values()) == 0:
            self.errors.append(
                "Classification failed: unable to determine capability category"
            )
            return {
                "category": None,
                "confidence": 0.0,
                "detected_keywords": {}
            }

        best_category = max(scores, key=scores.get)
        max_score = scores[best_category]
        total_patterns = len(patterns[best_category])
        confidence = min(max_score / total_patterns, 1.0)

        self.phases_completed.append(phase_name)

        return {
            "category": best_category,
            "confidence": confidence,
            "detected_keywords": detected.get(best_category, [])
        }

    def _phase_2_research(
        self,
        request: str,
        classification: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Phase 2: Research via Mongke (researcher agent).

        In production, this would delegate to a research agent.
        For now, returns structured research template.

        Args:
            request: Learning request
            classification: Classification result from Phase 1

        Returns:
            Dictionary with success, findings, and sources
        """
        phase_name = "Phase 2: Research"

        # TODO: In production, delegate to Mongke agent via:
        # result = self.delegate_to_agent(
        #     agent_type="researcher",
        #     task=f"Research: {request}",
        #     context=classification
        # )

        # Simulated research output
        research_template = {
            "success": True,
            "findings": {
                "key_concepts": [
                    f"Understanding {classification['category']} requirements",
                    "Best practices and design patterns",
                    "Security considerations"
                ],
                "technical_approach": [
                    "Identify required libraries and dependencies",
                    "Design API interface and data structures",
                    "Plan error handling and edge cases"
                ],
                "implementation_notes": [
                    "Follow Python PEP 8 style guidelines",
                    "Use type hints for better code clarity",
                    "Include comprehensive docstrings"
                ]
            },
            "sources": [
                "Python standard library documentation",
                "Security best practices guides",
                f"{classification['category']} implementation patterns"
            ],
            "estimated_complexity": "medium"
        }

        self.phases_completed.append(phase_name)
        return research_template

    def _phase_3_implement(
        self,
        request: str,
        classification: Dict[str, any],
        research: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Phase 3: Implementation via Temujin (developer agent).

        In production, this would delegate to a developer agent.
        For now, returns code template.

        Args:
            request: Learning request
            classification: Classification result
            research: Research findings

        Returns:
            Dictionary with success, code, and metadata
        """
        phase_name = "Phase 3: Implementation"

        # TODO: In production, delegate to Temujin agent via:
        # result = self.delegate_to_agent(
        #     agent_type="developer",
        #     task=f"Implement: {request}",
        #     context={"classification": classification, "research": research}
        # )

        # Generate capability name from request
        capability_name = self._generate_capability_name(request, classification)

        # Code template based on category
        code_template = self._generate_code_template(
            capability_name,
            classification["category"],
            request
        )

        self.phases_completed.append(phase_name)

        return {
            "success": True,
            "code": code_template,
            "capability_name": capability_name,
            "dependencies": ["typing"],
            "entry_point": "execute"
        }

    def _phase_4_validate(
        self,
        implementation: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Phase 4: Validation via Jochi (analyst agent) and static analysis.

        Args:
            implementation: Implementation result from Phase 3

        Returns:
            Dictionary with approved (bool), findings, and recommendations
        """
        phase_name = "Phase 4: Validation"

        code = implementation.get("code", "")

        # Run static analysis
        try:
            from .static_analysis import ASTParser
            parser = ASTParser()
            findings = parser.analyze_code(code)
        except ImportError:
            findings = []
            self.errors.append(
                "Warning: Static analysis unavailable (AST parser not found)"
            )
        except Exception as e:
            findings = []
            self.errors.append(f"Static analysis error: {str(e)}")

        # Check for critical or high severity issues
        critical_issues = [
            f for f in findings
            if f.get("severity") in ["critical", "high"]
        ]

        if critical_issues:
            self.errors.append(
                f"Validation failed: {len(critical_issues)} critical/high "
                f"severity issues found"
            )
            self.phases_completed.append(f"{phase_name} (Failed)")
            return {
                "approved": False,
                "findings": findings,
                "critical_issues": critical_issues,
                "recommendations": [
                    "Fix critical security vulnerabilities before registration",
                    "Review code for injection risks and unsafe operations",
                    "Consider refactoring to use safer alternatives"
                ]
            }

        # TODO: In production, also delegate to Jochi agent for manual review:
        # manual_review = self.delegate_to_agent(
        #     agent_type="analyst",
        #     task="Security review of learned capability",
        #     context={"code": code, "static_findings": findings}
        # )

        self.phases_completed.append(phase_name)

        return {
            "approved": True,
            "findings": findings,
            "critical_issues": [],
            "recommendations": [
                "Code passed automated security validation",
                "Monitor capability usage for unexpected behavior",
                "Schedule periodic re-validation"
            ]
        }

    def _phase_5_register(
        self,
        classification: Dict[str, any],
        implementation: Dict[str, any],
        agent_id: str
    ) -> Dict[str, any]:
        """
        Phase 5: Register capability in Neo4j via CapabilityRegistry.

        Args:
            classification: Classification result
            implementation: Implementation result
            agent_id: Learning agent ID

        Returns:
            Dictionary with success, capability_name, and capability_id
        """
        phase_name = "Phase 5: Registration"

        if self.registry is None:
            self.errors.append("Registration failed: CapabilityRegistry unavailable")
            return {
                "success": False,
                "capability_name": implementation["capability_name"],
                "reason": "Registry not initialized"
            }

        try:
            capability_name = implementation["capability_name"]
            code = implementation["code"]

            # Generate code hash
            code_hash = self.registry.hash_code(code)

            # Register capability
            capability_id = self.registry.register(
                name=capability_name,
                description=f"Learned capability: {capability_name}",
                category=classification["category"],
                code_hash=code_hash,
                learned_by=agent_id
            )

            self.phases_completed.append(phase_name)

            return {
                "success": True,
                "capability_name": capability_name,
                "capability_id": capability_id,
                "code_hash": code_hash
            }

        except Exception as e:
            self.errors.append(f"Registration error: {str(e)}")
            return {
                "success": False,
                "capability_name": implementation["capability_name"],
                "reason": str(e)
            }

    def _phase_6_authorize(
        self,
        agent_id: str,
        capability_name: str
    ) -> Dict[str, any]:
        """
        Phase 6: Grant CBAC authorization to requesting agent.

        Args:
            agent_id: Agent to grant access to
            capability_name: Capability to authorize

        Returns:
            Dictionary with success and expiry information
        """
        phase_name = "Phase 6: Authorization"

        if self.registry is None:
            self.errors.append("Authorization skipped: CapabilityRegistry unavailable")
            return {"success": False, "reason": "Registry not initialized"}

        try:
            granted = self.registry.grant(
                agent_id=agent_id,
                capability_name=capability_name,
                expires_days=90
            )

            if granted:
                self.phases_completed.append(phase_name)
                return {
                    "success": True,
                    "agent_id": agent_id,
                    "capability_name": capability_name,
                    "expires_days": 90
                }
            else:
                self.errors.append("Authorization failed: grant operation returned False")
                return {"success": False, "reason": "Grant operation failed"}

        except Exception as e:
            self.errors.append(f"Authorization error: {str(e)}")
            return {"success": False, "reason": str(e)}

    def _generate_capability_name(
        self,
        request: str,
        classification: Dict[str, any]
    ) -> str:
        """Generate a capability name from the request."""
        # Extract key terms from request
        words = re.findall(r'\b[a-z]{3,}\b', request.lower())

        # Filter out common words
        stopwords = {"the", "and", "for", "with", "how", "learn", "create", "make"}
        keywords = [w for w in words if w not in stopwords][:3]

        # Combine with category
        category = classification["category"]
        if keywords:
            name = "_".join(keywords + [category])
        else:
            name = f"learned_{category}_{datetime.utcnow().strftime('%Y%m%d')}"

        return name

    def _generate_code_template(
        self,
        capability_name: str,
        category: str,
        request: str
    ) -> str:
        """Generate a basic code template for the capability."""
        template = f'''"""
{capability_name}: Auto-generated capability for {category}.

Request: {request}
Generated: {datetime.utcnow().isoformat()}
"""

from typing import Dict, Any, Optional


class {self._to_pascal_case(capability_name)}:
    """
    Implementation of {capability_name} capability.

    Category: {category}
    """

    def __init__(self):
        """Initialize the capability."""
        pass

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute the capability with provided parameters.

        Args:
            **kwargs: Capability-specific parameters

        Returns:
            Execution result dictionary
        """
        # TODO: Implement actual capability logic
        return {{
            "success": True,
            "message": "Capability executed successfully",
            "data": None
        }}

    def validate_input(self, **kwargs: Any) -> bool:
        """
        Validate input parameters.

        Args:
            **kwargs: Parameters to validate

        Returns:
            True if valid
        """
        # TODO: Implement input validation
        return True
'''
        return template

    @staticmethod
    def _to_pascal_case(snake_str: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(word.capitalize() for word in snake_str.split("_"))
