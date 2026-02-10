# Swarm Orchestrator Agent Proposal

## Executive Summary

This document proposes a `swarm-orchestrator` agent that enhances the existing horde-swarm pattern by intelligently composing agent teams. Instead of requiring manual agent selection, the swarm-orchestrator analyzes task descriptions, automatically selects optimal agent combinations, generates tailored prompts, and recommends appropriate swarm patterns.

## 1. Naming Convention

**Proposed Name**: `swarm-orchestrator`

**Rationale**:
- Follows existing kebab-case naming convention (e.g., `multi-goal-orchestration`)
- Clearly indicates its function: orchestrating swarms of agents
- Distinct from existing `orchestrator` types to avoid confusion
- Aligns with the "horde-swarm" terminology already in use

**Alternative Names Considered**:
- `team-composer` - Too generic, doesn't capture swarm dynamics
- `agent-selector` - Too narrow, doesn't include prompt generation
- `swarm-conductor` - Good but less commonly used terminology
- `horde-captain` - Too specific to existing naming

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SWARM ORCHESTRATOR FLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────────┐  │
│  │ Task Input   │───▶│ Task Analysis    │───▶│ Agent Selection Engine   │  │
│  │ (User Query) │    │ & Decomposition  │    │                          │  │
│  └──────────────┘    └──────────────────┘    └──────────────────────────┘  │
│                                                        │                     │
│                                                        ▼                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────────┐  │
│  │ Synthesis    │◀───│ Pattern Executor │◀───│ Prompt Generation        │  │
│  │ & Delivery   │    │ (Horde-Swarm)    │    │ (Per-Agent Prompts)      │  │
│  └──────────────┘    └──────────────────┘    └──────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. Core Components

### 3.1 Task Analysis Engine

**Purpose**: Decompose and characterize incoming tasks to determine optimal agent composition.

**Task Characteristics Analyzed**:

| Dimension | Description | Examples |
|-----------|-------------|----------|
| **Domain** | Subject matter area | `code`, `security`, `research`, `writing`, `analysis`, `operations` |
| **Complexity** | Estimated effort/depth | `simple` (1 agent), `moderate` (2-3 agents), `complex` (4+ agents) |
| **Scope** | Breadth of work | `narrow` (focused), `broad` (multi-faceted), `cross-cutting` (system-wide) |
| **Time Horizon** | Urgency and duration | `immediate`, `short-term`, `medium-term`, `long-term` |
| **Risk Level** | Potential impact | `low`, `medium`, `high`, `critical` |
| **Deliverable Type** | Output format | `code`, `document`, `analysis`, `decision`, `plan` |

**Analysis Algorithm**:

```python
@dataclass
class TaskCharacteristics:
    """Comprehensive task characterization for swarm composition."""

    domains: List[str]  # Primary and secondary domains
    complexity: str  # simple | moderate | complex
    scope: str  # narrow | broad | cross-cutting
    time_horizon: str  # immediate | short-term | medium-term | long-term
    risk_level: str  # low | medium | high | critical
    deliverable_type: str
    estimated_subtasks: int
    required_capabilities: List[str]
    conflicting_requirements: List[str]  # e.g., speed vs thoroughness


class TaskAnalyzer:
    """Analyzes task descriptions to extract characteristics."""

    # Domain detection patterns
    DOMAIN_PATTERNS = {
        "code": ["code", "develop", "implement", "program", "build", "refactor", "debug"],
        "security": ["security", "audit", "vulnerability", "penetration", "secure", "auth"],
        "research": ["research", "investigate", "find", "explore", "discover", "study"],
        "writing": ["write", "document", "draft", "content", "compose", "blog"],
        "analysis": ["analyze", "metrics", "performance", "data", "report", "review"],
        "operations": ["deploy", "monitor", "ops", "infrastructure", "setup", "configure"],
    }

    # Complexity indicators
    COMPLEXITY_INDICATORS = {
        "simple": ["quick", "simple", "basic", "minor", "small", "fix"],
        "moderate": ["implement", "create", "build", "design", "update"],
        "complex": ["architect", "redesign", "migrate", "integrate", "scale", "optimize"],
    }

    def analyze(self, task_description: str) -> TaskCharacteristics:
        """
        Analyze task description to extract characteristics.

        Uses a hybrid approach:
        1. Keyword-based pattern matching (fast)
        2. LLM-based semantic analysis (accurate)
        3. Historical task similarity (contextual)
        """
        # Step 1: Extract domains
        domains = self._detect_domains(task_description)

        # Step 2: Assess complexity
        complexity = self._assess_complexity(task_description)

        # Step 3: Determine scope
        scope = self._determine_scope(task_description, domains)

        # Step 4: Estimate subtasks
        estimated_subtasks = self._estimate_subtasks(task_description, complexity)

        # Step 5: Identify required capabilities
        required_capabilities = self._identify_capabilities(domains, complexity)

        return TaskCharacteristics(
            domains=domains,
            complexity=complexity,
            scope=scope,
            time_horizon=self._detect_time_horizon(task_description),
            risk_level=self._assess_risk(task_description),
            deliverable_type=self._detect_deliverable(task_description),
            estimated_subtasks=estimated_subtasks,
            required_capabilities=required_capabilities,
            conflicting_requirements=self._detect_conflicts(task_description),
        )

    def _detect_domains(self, description: str) -> List[str]:
        """Detect relevant domains from task description."""
        description_lower = description.lower()
        domain_scores = {}

        for domain, patterns in self.DOMAIN_PATTERNS.items():
            score = sum(1 for pattern in patterns if pattern in description_lower)
            if score > 0:
                domain_scores[domain] = score

        # Sort by score and return top domains
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        return [d[0] for d in sorted_domains[:2]]  # Primary and secondary domains

    def _assess_complexity(self, description: str) -> str:
        """Assess task complexity based on indicators."""
        description_lower = description.lower()

        # Count complexity indicators
        simple_count = sum(1 for w in self.COMPLEXITY_INDICATORS["simple"] if w in description_lower)
        moderate_count = sum(1 for w in self.COMPLEXITY_INDICATORS["moderate"] if w in description_lower)
        complex_count = sum(1 for w in self.COMPLEXITY_INDICATORS["complex"] if w in description_lower)

        # Also consider description length as a proxy
        word_count = len(description.split())
        if word_count > 100:
            complex_count += 1

        # Return highest scoring complexity
        scores = [("simple", simple_count), ("moderate", moderate_count), ("complex", complex_count)]
        return max(scores, key=lambda x: x[1])[0]

    def _determine_scope(self, description: str, domains: List[str]) -> str:
        """Determine task scope based on description and domains."""
        # Multi-domain tasks are likely broader in scope
        if len(domains) > 1:
            return "broad"

        # Check for scope indicators
        broad_indicators = ["system", "architecture", "multiple", "all", "across", "entire"]
        narrow_indicators = ["single", "specific", "one", "particular", "focused"]

        description_lower = description.lower()
        broad_score = sum(1 for w in broad_indicators if w in description_lower)
        narrow_score = sum(1 for w in narrow_indicators if w in description_lower)

        if broad_score > narrow_score:
            return "broad"
        elif narrow_score > broad_score:
            return "narrow"
        return "broad" if len(domains) > 1 else "narrow"

    def _estimate_subtasks(self, description: str, complexity: str) -> int:
        """Estimate number of subtasks based on complexity and description."""
        base_estimate = {"simple": 1, "moderate": 3, "complex": 5}[complexity]

        # Count explicit task indicators
        task_indicators = ["and", "then", "also", "additionally", "furthermore"]
        additional_tasks = sum(1 for w in task_indicators if w in description.lower())

        return min(base_estimate + additional_tasks, 8)  # Cap at 8 subtasks

    def _identify_capabilities(self, domains: List[str], complexity: str) -> List[str]:
        """Map domains to required agent capabilities."""
        capability_map = {
            "code": ["coding", "architecture", "debugging"],
            "security": ["security_audit", "vulnerability_assessment"],
            "research": ["research", "synthesis", "information_gathering"],
            "writing": ["writing", "editing", "documentation"],
            "analysis": ["analysis", "metrics", "reporting"],
            "operations": ["deployment", "monitoring", "infrastructure"],
        }

        capabilities = []
        for domain in domains:
            capabilities.extend(capability_map.get(domain, []))

        # Add complexity-based capabilities
        if complexity == "complex":
            capabilities.extend(["coordination", "planning"])

        return list(set(capabilities))

    def _detect_time_horizon(self, description: str) -> str:
        """Detect urgency/time horizon from description."""
        urgent_indicators = ["urgent", "asap", "immediately", "now", "today", "critical"]
        short_indicators = ["this week", "soon", "quick", "fast"]
        long_indicators = ["long-term", "strategic", "roadmap", "future"]

        description_lower = description.lower()

        if any(w in description_lower for w in urgent_indicators):
            return "immediate"
        elif any(w in description_lower for w in short_indicators):
            return "short-term"
        elif any(w in description_lower for w in long_indicators):
            return "long-term"
        return "medium-term"

    def _assess_risk(self, description: str) -> str:
        """Assess risk level based on keywords."""
        critical_indicators = ["production", "customer-facing", "revenue", "security breach"]
        high_indicators = ["database", "api", "payment", "authentication"]

        description_lower = description.lower()

        if any(w in description_lower for w in critical_indicators):
            return "critical"
        elif any(w in description_lower for w in high_indicators):
            return "high"
        return "medium"

    def _detect_deliverable(self, description: str) -> str:
        """Detect expected deliverable type."""
        if any(w in description.lower() for w in ["code", "implement", "build", "fix"]):
            return "code"
        elif any(w in description.lower() for w in ["write", "document", "draft", "blog"]):
            return "document"
        elif any(w in description.lower() for w in ["analyze", "report", "review", "assess"]):
            return "analysis"
        elif any(w in description.lower() for w in ["decide", "choose", "recommend", "advise"]):
            return "decision"
        return "plan"

    def _detect_conflicts(self, description: str) -> List[str]:
        """Detect potentially conflicting requirements."""
        conflicts = []

        # Speed vs thoroughness
        if any(w in description.lower() for w in ["quick", "fast", "speed"]) and \
           any(w in description.lower() for w in ["thorough", "comprehensive", "detailed"]):
            conflicts.append("speed_vs_thoroughness")

        # Innovation vs stability
        if any(w in description.lower() for w in ["new", "innovative", "cutting-edge"]) and \
           any(w in description.lower() for w in ["stable", "reliable", "proven"]):
            conflicts.append("innovation_vs_stability")

        return conflicts
```

### 3.2 Agent Selection Engine

**Purpose**: Select the optimal 2-4 agent types based on task characteristics.

**Available Agent Pool** (from existing system):

| Agent ID | Name | Primary Role | Capabilities | Best For |
|----------|------|--------------|--------------|----------|
| `researcher` | Möngke | Research | research, synthesis, information_gathering | Deep research, fact-finding |
| `writer` | Chagatai | Writing | writing, editing, documentation | Content creation, docs |
| `developer` | Temüjin | Development | coding, architecture, debugging | Code implementation |
| `analyst` | Jochi | Analysis | analysis, metrics, reporting | Data analysis, review |
| `ops` | Ögedei | Operations | deployment, monitoring, infrastructure | DevOps, infrastructure |
| `main` | Kublai | Orchestration | coordination, synthesis, planning | Complex coordination |

**Selection Algorithm**:

```python
@dataclass
class AgentSelection:
    """Selected agent with role and rationale."""

    agent_id: str
    agent_name: str
    role_in_swarm: str  # e.g., "primary", "reviewer", "specialist"
    rationale: str
    confidence: float  # 0.0 - 1.0


class AgentSelectionEngine:
    """Selects optimal agent team based on task characteristics."""

    # Agent capability matrix
    AGENT_CAPABILITIES = {
        "researcher": {
            "capabilities": ["research", "synthesis", "information_gathering", "fact_checking"],
            "domains": ["research"],
            "complexity_preference": ["moderate", "complex"],
            "strengths": ["deep_research", "information_synthesis", "trend_analysis"],
            "weaknesses": ["implementation", "operations"],
        },
        "writer": {
            "capabilities": ["writing", "editing", "documentation", "content_creation"],
            "domains": ["writing"],
            "complexity_preference": ["simple", "moderate"],
            "strengths": ["clear_communication", "documentation", "audience_adaptation"],
            "weaknesses": ["technical_implementation", "data_analysis"],
        },
        "developer": {
            "capabilities": ["coding", "architecture", "debugging", "security_audit"],
            "domains": ["code", "security"],
            "complexity_preference": ["moderate", "complex"],
            "strengths": ["implementation", "problem_solving", "system_design"],
            "weaknesses": ["content_creation", "research"],
        },
        "analyst": {
            "capabilities": ["analysis", "metrics", "reporting", "review"],
            "domains": ["analysis"],
            "complexity_preference": ["moderate", "complex"],
            "strengths": ["data_analysis", "pattern_recognition", "quality_assessment"],
            "weaknesses": ["implementation", "creative_writing"],
        },
        "ops": {
            "capabilities": ["deployment", "monitoring", "infrastructure", "process"],
            "domains": ["operations"],
            "complexity_preference": ["simple", "moderate"],
            "strengths": ["reliability", "automation", "incident_response"],
            "weaknesses": ["creative_work", "research"],
        },
    }

    def select_agents(
        self,
        task_characteristics: TaskCharacteristics,
        max_agents: int = 4,
        min_agents: int = 2
    ) -> List[AgentSelection]:
        """
        Select optimal agent team for the task.

        Returns 2-4 agents with defined roles in the swarm.
        """
        # Score each agent for this task
        agent_scores = {}

        for agent_id, profile in self.AGENT_CAPABILITIES.items():
            score = self._calculate_agent_score(agent_id, profile, task_characteristics)
            agent_scores[agent_id] = score

        # Sort by score
        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)

        # Determine number of agents needed
        num_agents = self._determine_team_size(task_characteristics, min_agents, max_agents)

        # Select top N agents
        selected = []
        for i, (agent_id, score) in enumerate(sorted_agents[:num_agents]):
            role = self._determine_role(agent_id, i, task_characteristics)
            rationale = self._generate_rationale(agent_id, role, task_characteristics)

            selected.append(AgentSelection(
                agent_id=agent_id,
                agent_name=self._get_agent_name(agent_id),
                role_in_swarm=role,
                rationale=rationale,
                confidence=min(score, 1.0)
            ))

        return selected

    def _calculate_agent_score(
        self,
        agent_id: str,
        profile: Dict,
        characteristics: TaskCharacteristics
    ) -> float:
        """Calculate how well an agent matches the task."""
        score = 0.0

        # Domain match (highest weight)
        domain_overlap = set(profile["domains"]) & set(characteristics.domains)
        score += len(domain_overlap) * 0.4

        # Capability match
        capability_overlap = set(profile["capabilities"]) & set(characteristics.required_capabilities)
        score += len(capability_overlap) * 0.2

        # Complexity preference match
        if characteristics.complexity in profile["complexity_preference"]:
            score += 0.2

        # Risk consideration
        if characteristics.risk_level in ["high", "critical"]:
            # Prefer agents with proven reliability
            if "security_audit" in profile["capabilities"] or "analysis" in profile["capabilities"]:
                score += 0.1

        # Time horizon consideration
        if characteristics.time_horizon == "immediate":
            # Prefer agents that work quickly
            if agent_id in ["developer", "ops"]:
                score += 0.1

        return score

    def _determine_team_size(
        self,
        characteristics: TaskCharacteristics,
        min_agents: int,
        max_agents: int
    ) -> int:
        """Determine optimal team size based on task characteristics."""
        # Base size on complexity
        complexity_sizes = {
            "simple": min_agents,
            "moderate": 3,
            "complex": max_agents
        }
        base_size = complexity_sizes.get(characteristics.complexity, min_agents)

        # Adjust for scope
        if characteristics.scope == "cross-cutting":
            base_size = min(base_size + 1, max_agents)

        # Adjust for domains
        if len(characteristics.domains) > 1:
            base_size = min(base_size + 1, max_agents)

        # Risk consideration - high risk tasks need review
        if characteristics.risk_level in ["high", "critical"]:
            base_size = max(base_size, 3)  # At least 3 for peer review

        return max(min(base_size, max_agents), min_agents)

    def _determine_role(
        self,
        agent_id: str,
        rank: int,
        characteristics: TaskCharacteristics
    ) -> str:
        """Determine the agent's role in the swarm."""
        if rank == 0:
            return "primary"
        elif rank == 1 and characteristics.complexity == "complex":
            return "co-primary"
        elif agent_id == "analyst" and characteristics.risk_level in ["high", "critical"]:
            return "reviewer"
        elif agent_id == "researcher":
            return "researcher"
        elif agent_id == "writer":
            return "documentarian"
        else:
            return "specialist"

    def _generate_rationale(
        self,
        agent_id: str,
        role: str,
        characteristics: TaskCharacteristics
    ) -> str:
        """Generate human-readable rationale for agent selection."""
        rationales = {
            "primary": f"Primary executor for {characteristics.domains[0]} work",
            "co-primary": f"Co-executor for complex {characteristics.domains[0]} task",
            "reviewer": "Quality assurance and risk mitigation",
            "researcher": "Background research and information synthesis",
            "documentarian": "Documentation and communication",
            "specialist": f"Specialized expertise in {characteristics.domains[0]}",
        }
        return rationales.get(role, "Supporting specialist")

    def _get_agent_name(self, agent_id: str) -> str:
        """Get display name for agent."""
        names = {
            "researcher": "Möngke",
            "writer": "Chagatai",
            "developer": "Temüjin",
            "analyst": "Jochi",
            "ops": "Ögedei",
        }
        return names.get(agent_id, agent_id.capitalize())
```

### 3.3 Prompt Generation Engine

**Purpose**: Generate tailored, context-aware prompts for each selected agent.

```python
@dataclass
class GeneratedPrompt:
    """Generated prompt with metadata."""

    agent_id: str
    agent_name: str
    prompt: str
    context_injection: Dict[str, Any]
    expected_output_format: str
    success_criteria: List[str]


class PromptGenerationEngine:
    """Generates tailored prompts for each agent in the swarm."""

    # Base prompt templates per agent type
    BASE_TEMPLATES = {
        "researcher": """You are {agent_name}, a research specialist.

TASK: {task_description}

YOUR ROLE IN THIS SWARM: {role_description}

FOCUS AREAS:
{focus_areas}

DELIVERABLE:
{deliverable_requirements}

{context_section}

CONSTRAINTS:
{constraints}

Return your findings in a structured format with citations where applicable.
""",
        "writer": """You are {agent_name}, a writing specialist.

TASK: {task_description}

YOUR ROLE IN THIS SWARM: {role_description}

WRITING CONTEXT:
{focus_areas}

OUTPUT REQUIREMENTS:
{deliverable_requirements}

{context_section}

STYLE GUIDELINES:
{constraints}

Produce polished, ready-to-use content.
""",
        "developer": """You are {agent_name}, a development specialist.

TASK: {task_description}

YOUR ROLE IN THIS SWARM: {role_description}

TECHNICAL SCOPE:
{focus_areas}

CODE REQUIREMENTS:
{deliverable_requirements}

{context_section}

IMPLEMENTATION NOTES:
{constraints}

Provide production-ready code with comments and error handling.
""",
        "analyst": """You are {agent_name}, an analysis specialist.

TASK: {task_description}

YOUR ROLE IN THIS SWARM: {role_description}

ANALYSIS FOCUS:
{focus_areas}

EVALUATION CRITERIA:
{deliverable_requirements}

{context_section}

METHODOLOGY:
{constraints}

Present findings with data-backed evidence and clear recommendations.
""",
        "ops": """You are {agent_name}, an operations specialist.

TASK: {task_description}

YOUR ROLE IN THIS SWARM: {role_description}

OPERATIONAL SCOPE:
{focus_areas}

DEPLOYMENT REQUIREMENTS:
{deliverable_requirements}

{context_section}

RELIABILITY CONSIDERATIONS:
{constraints}

Ensure solutions are maintainable, monitored, and resilient.
""",
    }

    def generate_prompts(
        self,
        task_description: str,
        task_characteristics: TaskCharacteristics,
        selected_agents: List[AgentSelection],
        swarm_pattern: str
    ) -> List[GeneratedPrompt]:
        """Generate tailored prompts for each selected agent."""
        prompts = []

        # Decompose task for swarm pattern
        subtasks = self._decompose_for_pattern(
            task_description,
            task_characteristics,
            selected_agents,
            swarm_pattern
        )

        for agent_selection in selected_agents:
            prompt = self._generate_single_prompt(
                agent_selection,
                task_description,
                task_characteristics,
                subtasks.get(agent_selection.agent_id, {}),
                selected_agents,
                swarm_pattern
            )
            prompts.append(prompt)

        return prompts

    def _decompose_for_pattern(
        self,
        task_description: str,
        characteristics: TaskCharacteristics,
        agents: List[AgentSelection],
        pattern: str
    ) -> Dict[str, Dict]:
        """Decompose task into subtasks based on swarm pattern."""
        subtasks = {}

        if pattern == "multi-perspective":
            # Each agent approaches from different angle
            angles = ["technical", "user-experience", "business", "security"][:len(agents)]
            for agent, angle in zip(agents, angles):
                subtasks[agent.agent_id] = {
                    "angle": angle,
                    "focus": f"Analyze from {angle} perspective"
                }

        elif pattern == "divide-conquer":
            # Split task into sequential components
            components = self._identify_components(task_description, len(agents))
            for agent, component in zip(agents, components):
                subtasks[agent.agent_id] = component

        elif pattern == "expert-review":
            # Primary does work, others review
            primary = agents[0]
            reviewers = agents[1:]

            subtasks[primary.agent_id] = {
                "role": "executor",
                "focus": "Complete the primary task"
            }

            for reviewer in reviewers:
                subtasks[reviewer.agent_id] = {
                    "role": "reviewer",
                    "focus": f"Review and validate {primary.agent_name}'s work"
                }

        return subtasks

    def _generate_single_prompt(
        self,
        agent_selection: AgentSelection,
        task_description: str,
        characteristics: TaskCharacteristics,
        subtask: Dict,
        all_agents: List[AgentSelection],
        pattern: str
    ) -> GeneratedPrompt:
        """Generate a single tailored prompt."""
        agent_id = agent_selection.agent_id

        # Get base template
        template = self.BASE_TEMPLATES.get(agent_id, self.BASE_TEMPLATES["researcher"])

        # Build context section
        context_section = self._build_context_section(agent_selection, all_agents, pattern)

        # Build focus areas
        focus_areas = self._build_focus_areas(agent_selection, characteristics, subtask)

        # Build constraints
        constraints = self._build_constraints(agent_selection, characteristics)

        # Build deliverable requirements
        deliverable = self._build_deliverable_requirements(agent_selection, characteristics)

        # Generate role description
        role_description = self._generate_role_description(agent_selection, pattern)

        # Fill template
        prompt_text = template.format(
            agent_name=agent_selection.agent_name,
            task_description=task_description,
            role_description=role_description,
            focus_areas=focus_areas,
            deliverable_requirements=deliverable,
            context_section=context_section,
            constraints=constraints
        )

        return GeneratedPrompt(
            agent_id=agent_id,
            agent_name=agent_selection.agent_name,
            prompt=prompt_text,
            context_injection={
                "swarm_pattern": pattern,
                "role": agent_selection.role_in_swarm,
                "subtask": subtask,
                "peer_agents": [a.agent_id for a in all_agents if a.agent_id != agent_id]
            },
            expected_output_format=self._determine_output_format(agent_id, characteristics),
            success_criteria=self._determine_success_criteria(agent_id, characteristics)
        )

    def _build_context_section(
        self,
        agent_selection: AgentSelection,
        all_agents: List[AgentSelection],
        pattern: str
    ) -> str:
        """Build context about other agents in the swarm."""
        peers = [a for a in all_agents if a.agent_id != agent_selection.agent_id]

        if not peers:
            return ""

        peer_descriptions = []
        for peer in peers:
            peer_descriptions.append(f"- {peer.agent_name} ({peer.agent_id}): {peer.role_in_swarm}")

        return f"""TEAM CONTEXT:
You are working alongside:
{chr(10).join(peer_descriptions)}

Swarm Pattern: {pattern}
Coordinate with your teammates as appropriate for this pattern.
"""

    def _build_focus_areas(
        self,
        agent_selection: AgentSelection,
        characteristics: TaskCharacteristics,
        subtask: Dict
    ) -> str:
        """Build focus areas for the agent."""
        focus_items = []

        # Domain-specific focus
        for domain in characteristics.domains:
            focus_items.append(f"- Address {domain} aspects of the task")

        # Subtask-specific focus
        if "focus" in subtask:
            focus_items.append(f"- {subtask['focus']}")

        # Role-specific focus
        if agent_selection.role_in_swarm == "reviewer":
            focus_items.append("- Identify potential issues and risks")
            focus_items.append("- Validate assumptions and approaches")
        elif agent_selection.role_in_swarm == "researcher":
            focus_items.append("- Gather relevant background information")
            focus_items.append("- Identify best practices and patterns")

        return chr(10).join(focus_items) if focus_items else "- Complete assigned task thoroughly"

    def _build_constraints(
        self,
        agent_selection: AgentSelection,
        characteristics: TaskCharacteristics
    ) -> str:
        """Build constraints section."""
        constraints = []

        # Time constraints
        if characteristics.time_horizon == "immediate":
            constraints.append("- Time-critical: Prioritize speed while maintaining quality")
        elif characteristics.time_horizon == "long-term":
            constraints.append("- Strategic focus: Consider long-term implications")

        # Risk constraints
        if characteristics.risk_level in ["high", "critical"]:
            constraints.append("- High-risk context: Extra validation required")

        # Complexity constraints
        if characteristics.complexity == "complex":
            constraints.append("- Complex task: Break down into manageable components")

        # Conflict handling
        for conflict in characteristics.conflicting_requirements:
            if conflict == "speed_vs_thoroughness":
                constraints.append("- Balance speed with thoroughness appropriately")

        return chr(10).join(constraints) if constraints else "- Follow best practices for your domain"

    def _build_deliverable_requirements(
        self,
        agent_selection: AgentSelection,
        characteristics: TaskCharacteristics
    ) -> str:
        """Build deliverable requirements."""
        requirements = []

        # Base on deliverable type
        if characteristics.deliverable_type == "code":
            requirements.append("- Production-ready code with comments")
            requirements.append("- Error handling and edge cases addressed")
        elif characteristics.deliverable_type == "document":
            requirements.append("- Clear, well-structured content")
            requirements.append("- Appropriate for target audience")
        elif characteristics.deliverable_type == "analysis":
            requirements.append("- Data-backed findings")
            requirements.append("- Clear recommendations")

        # Role-specific requirements
        if agent_selection.role_in_swarm == "reviewer":
            requirements.append("- Review report with findings and recommendations")

        return chr(10).join(requirements)

    def _generate_role_description(self, agent_selection: AgentSelection, pattern: str) -> str:
        """Generate role description for the agent."""
        role_descriptions = {
            "primary": f"You are the primary executor for this {pattern} swarm.",
            "co-primary": f"You share primary responsibility in this {pattern} swarm.",
            "reviewer": f"You provide quality assurance in this {pattern} swarm.",
            "researcher": f"You gather intelligence in this {pattern} swarm.",
            "documentarian": f"You handle documentation in this {pattern} swarm.",
            "specialist": f"You provide specialized expertise in this {pattern} swarm.",
        }
        return role_descriptions.get(agent_selection.role_in_swarm, "Support the swarm's objectives.")

    def _determine_output_format(self, agent_id: str, characteristics: TaskCharacteristics) -> str:
        """Determine expected output format."""
        formats = {
            "researcher": "Structured report with findings and sources",
            "writer": "Polished document in requested format",
            "developer": "Code with documentation and tests",
            "analyst": "Analysis report with metrics and recommendations",
            "ops": "Implementation plan with monitoring strategy",
        }
        return formats.get(agent_id, "Structured output")

    def _determine_success_criteria(self, agent_id: str, characteristics: TaskCharacteristics) -> List[str]:
        """Determine success criteria for the agent."""
        criteria = ["Task completed as specified"]

        if agent_id == "developer":
            criteria.extend(["Code is functional", "Tests pass", "Documentation complete"])
        elif agent_id == "analyst":
            criteria.extend(["Analysis is thorough", "Recommendations are actionable"])
        elif agent_id == "writer":
            criteria.extend(["Content is clear", "Audience-appropriate tone"])

        return criteria

    def _identify_components(self, task_description: str, num_components: int) -> List[Dict]:
        """Identify task components for divide-conquer pattern."""
        # Simple heuristic-based component identification
        components = []

        # Look for explicit components
        component_indicators = ["first", "then", "next", "finally", "and", "also"]
        words = task_description.lower().split()

        found_components = []
        current_component = []

        for word in words:
            if word in component_indicators and current_component:
                found_components.append(" ".join(current_component))
                current_component = []
            current_component.append(word)

        if current_component:
            found_components.append(" ".join(current_component))

        # If we found components, use them; otherwise split evenly
        if len(found_components) >= num_components:
            for i, component in enumerate(found_components[:num_components]):
                components.append({
                    "component_id": i + 1,
                    "description": component,
                    "focus": f"Handle component {i + 1}"
                })
        else:
            # Split task description roughly evenly
            words = task_description.split()
            chunk_size = len(words) // num_components

            for i in range(num_components):
                start = i * chunk_size
                end = start + chunk_size if i < num_components - 1 else len(words)
                chunk = " ".join(words[start:end])

                components.append({
                    "component_id": i + 1,
                    "description": chunk,
                    "focus": f"Handle part {i + 1} of the task"
                })

        return components
```

### 3.4 Swarm Pattern Selector

**Purpose**: Recommend the optimal swarm pattern based on task characteristics and selected agents.

```python
class SwarmPattern(Enum):
    """Available swarm execution patterns."""

    MULTI_PERSPECTIVE = "multi-perspective"
    DIVIDE_CONQUER = "divide-conquer"
    EXPERT_REVIEW = "expert-review"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass
class PatternRecommendation:
    """Recommended swarm pattern with rationale."""

    pattern: SwarmPattern
    confidence: float
    rationale: str
    execution_flow: List[str]
    expected_duration: str
    risk_mitigation: List[str]


class SwarmPatternSelector:
    """Selects optimal swarm pattern for the task."""

    def recommend_pattern(
        self,
        task_characteristics: TaskCharacteristics,
        selected_agents: List[AgentSelection]
    ) -> PatternRecommendation:
        """
        Recommend the best swarm pattern for this task.

        Considers:
        - Task characteristics
        - Number and types of agents
        - Risk level
        - Time constraints
        """
        # Score each pattern
        pattern_scores = {
            SwarmPattern.MULTI_PERSPECTIVE: self._score_multi_perspective(task_characteristics, selected_agents),
            SwarmPattern.DIVIDE_CONQUER: self._score_divide_conquer(task_characteristics, selected_agents),
            SwarmPattern.EXPERT_REVIEW: self._score_expert_review(task_characteristics, selected_agents),
            SwarmPattern.SEQUENTIAL: self._score_sequential(task_characteristics, selected_agents),
            SwarmPattern.PARALLEL: self._score_parallel(task_characteristics, selected_agents),
        }

        # Select highest scoring pattern
        best_pattern = max(pattern_scores.items(), key=lambda x: x[1])

        return PatternRecommendation(
            pattern=best_pattern[0],
            confidence=min(best_pattern[1], 1.0),
            rationale=self._generate_rationale(best_pattern[0], task_characteristics),
            execution_flow=self._generate_execution_flow(best_pattern[0], selected_agents),
            expected_duration=self._estimate_duration(best_pattern[0], task_characteristics),
            risk_mitigation=self._identify_risk_mitigation(best_pattern[0], task_characteristics)
        )

    def _score_multi_perspective(
        self,
        characteristics: TaskCharacteristics,
        agents: List[AgentSelection]
    ) -> float:
        """Score multi-perspective pattern suitability."""
        score = 0.0

        # Good for complex decisions requiring multiple viewpoints
        if characteristics.deliverable_type == "decision":
            score += 0.3

        # Good for cross-cutting scope
        if characteristics.scope == "cross-cutting":
            score += 0.2

        # Needs diverse agents
        agent_types = set(a.agent_id for a in agents)
        if len(agent_types) >= 3:
            score += 0.3

        # Good for strategic/long-term tasks
        if characteristics.time_horizon in ["medium-term", "long-term"]:
            score += 0.1

        return score

    def _score_divide_conquer(
        self,
        characteristics: TaskCharacteristics,
        agents: List[AgentSelection]
    ) -> float:
        """Score divide-and-conquer pattern suitability."""
        score = 0.0

        # Good for complex tasks with clear components
        if characteristics.complexity == "complex":
            score += 0.3

        # Good when multiple subtasks exist
        if characteristics.estimated_subtasks >= 3:
            score += 0.2

        # Needs sufficient agents
        if len(agents) >= 3:
            score += 0.2

        # Good for implementation tasks
        if characteristics.deliverable_type == "code":
            score += 0.2

        return score

    def _score_expert_review(
        self,
        characteristics: TaskCharacteristics,
        agents: List[AgentSelection]
    ) -> float:
        """Score expert-review pattern suitability."""
        score = 0.0

        # Excellent for high-risk tasks
        if characteristics.risk_level in ["high", "critical"]:
            score += 0.4

        # Good when analyst is available
        if any(a.agent_id == "analyst" for a in agents):
            score += 0.2

        # Good for code and security tasks
        if characteristics.domains[0] in ["code", "security"]:
            score += 0.2

        # Needs at least 2 agents (executor + reviewer)
        if len(agents) >= 2:
            score += 0.1

        return score

    def _score_sequential(
        self,
        characteristics: TaskCharacteristics,
        agents: List[AgentSelection]
    ) -> float:
        """Score sequential pattern suitability."""
        score = 0.0

        # Good for tasks with clear dependencies
        if characteristics.complexity == "complex":
            score += 0.2

        # Good for research -> write -> review workflows
        if set(a.agent_id for a in agents) == {"researcher", "writer", "analyst"}:
            score += 0.3

        # Good when time permits
        if characteristics.time_horizon in ["medium-term", "long-term"]:
            score += 0.1

        return score

    def _score_parallel(
        self,
        characteristics: TaskCharacteristics,
        agents: List[AgentSelection]
    ) -> float:
        """Score parallel pattern suitability."""
        score = 0.0

        # Good for independent subtasks
        if characteristics.scope == "broad":
            score += 0.2

        # Good when time is critical
        if characteristics.time_horizon == "immediate":
            score += 0.3

        # Needs multiple agents
        if len(agents) >= 2:
            score += 0.2

        # Good for simple tasks
        if characteristics.complexity == "simple":
            score += 0.2

        return score

    def _generate_rationale(self, pattern: SwarmPattern, characteristics: TaskCharacteristics) -> str:
        """Generate human-readable rationale for pattern selection."""
        rationales = {
            SwarmPattern.MULTI_PERSPECTIVE: (
                f"Multi-perspective approach optimal for {characteristics.scope} scope task. "
                "Multiple specialists will analyze from different angles, then synthesize findings."
            ),
            SwarmPattern.DIVIDE_CONQUER: (
                f"Divide-and-conquer approach best for complex task with {characteristics.estimated_subtasks} "
                "estimated subtasks. Work will be split and executed in parallel."
            ),
            SwarmPattern.EXPERT_REVIEW: (
                f"Expert-review pattern selected due to {characteristics.risk_level} risk level. "
                "Primary executor will complete work, then reviewers will validate."
            ),
            SwarmPattern.SEQUENTIAL: (
                "Sequential workflow optimal for tasks with clear dependencies. "
                "Each agent's output feeds into the next stage."
            ),
            SwarmPattern.PARALLEL: (
                f"Parallel execution selected for {characteristics.time_horizon} timeline. "
                "Agents will work simultaneously on independent components."
            ),
        }
        return rationales.get(pattern, "Pattern selected based on task characteristics.")

    def _generate_execution_flow(
        self,
        pattern: SwarmPattern,
        agents: List[AgentSelection]
    ) -> List[str]:
        """Generate execution flow description."""
        agent_names = [a.agent_name for a in agents]

        flows = {
            SwarmPattern.MULTI_PERSPECTIVE: [
                "1. All agents analyze task from their specialty perspective",
                "2. Agents share findings with each other",
                "3. Synthesis of multiple perspectives into unified solution",
                "4. Final validation"
            ],
            SwarmPattern.DIVIDE_CONQUER: [
                f"1. Task decomposition into {len(agents)} components",
                f"2. Parallel execution by {', '.join(agent_names)}",
                "3. Component integration",
                "4. Integration testing/validation"
            ],
            SwarmPattern.EXPERT_REVIEW: [
                f"1. {agent_names[0]} completes primary work",
                f"2. {', '.join(agent_names[1:])} review and validate",
                "3. Feedback incorporation",
                "4. Final approval"
            ],
            SwarmPattern.SEQUENTIAL: [
                f"1. {agent_names[0]} completes first phase",
            ] + [f"{i+2}. {name} completes next phase" for i, name in enumerate(agent_names[1:])] + [
                f"{len(agent_names)+2}. Final delivery"
            ],
            SwarmPattern.PARALLEL: [
                "1. Task split into independent workstreams",
                f"2. {', '.join(agent_names)} execute in parallel",
                "3. Results aggregation",
                "4. Final synthesis"
            ],
        }

        return flows.get(pattern, ["Execute task", "Deliver results"])

    def _estimate_duration(self, pattern: SwarmPattern, characteristics: TaskCharacteristics) -> str:
        """Estimate execution duration."""
        # Base estimates by complexity
        base_durations = {
            "simple": 30,  # minutes
            "moderate": 60,
            "complex": 120
        }

        base = base_durations.get(characteristics.complexity, 60)

        # Pattern adjustments
        adjustments = {
            SwarmPattern.MULTI_PERSPECTIVE: 1.2,  # Slight overhead for coordination
            SwarmPattern.DIVIDE_CONQUER: 0.7,  # Parallel speedup
            SwarmPattern.EXPERT_REVIEW: 1.5,  # Review adds time
            SwarmPattern.SEQUENTIAL: 1.0,  # Baseline
            SwarmPattern.PARALLEL: 0.6,  # Maximum parallelization
        }

        adjusted = base * adjustments.get(pattern, 1.0)

        if adjusted < 60:
            return f"~{int(adjusted)} minutes"
        else:
            return f"~{adjusted/60:.1f} hours"

    def _identify_risk_mitigation(self, pattern: SwarmPattern, characteristics: TaskCharacteristics) -> List[str]:
        """Identify risk mitigation strategies for the pattern."""
        mitigations = {
            SwarmPattern.MULTI_PERSPECTIVE: [
                "Clear perspective definitions prevent overlap",
                "Structured synthesis process ensures coherence"
            ],
            SwarmPattern.DIVIDE_CONQUER: [
                "Well-defined interfaces between components",
                "Integration testing before final delivery"
            ],
            SwarmPattern.EXPERT_REVIEW: [
                "Multiple reviewers catch more issues",
                "Clear review criteria and checklists"
            ],
            SwarmPattern.SEQUENTIAL: [
                "Milestone checkpoints between phases",
                "Early feedback on initial phases"
            ],
            SwarmPattern.PARALLEL: [
                "Regular sync points to maintain alignment",
                "Clear ownership of each workstream"
            ],
        }

        base_mitigations = mitigations.get(pattern, [])

        # Add risk-specific mitigations
        if characteristics.risk_level in ["high", "critical"]:
            base_mitigations.append("Escalation path for blockers")

        return base_mitigations
```

## 4. Safety Mechanisms

### 4.1 Poor Agent Selection Prevention

```python
class SelectionSafetyChecker:
    """Validates agent selections to prevent poor choices."""

    # Anti-patterns to detect
    ANTI_PATTERNS = {
        "redundant_agents": {
            "description": "Multiple agents with identical capabilities",
            "check": lambda agents: len(set(a.agent_id for a in agents)) < len(agents)
        },
        "missing_critical_capability": {
            "description": "No agent has required capability for task domain",
            "check": lambda agents, domain: not any(
                domain in AGENT_CAPABILITIES.get(a.agent_id, {}).get("domains", [])
                for a in agents
            )
        },
        "too_many_agents": {
            "description": "More agents than beneficial for task complexity",
            "check": lambda agents, complexity: len(agents) > 4 and complexity == "simple"
        },
        "single_point_of_failure": {
            "description": "Only one agent for critical task",
            "check": lambda agents, risk: len(agents) == 1 and risk in ["high", "critical"]
        },
    }

    def validate_selection(
        self,
        selected_agents: List[AgentSelection],
        task_characteristics: TaskCharacteristics
    ) -> Tuple[bool, List[str]]:
        """
        Validate agent selection and return warnings if issues found.

        Returns:
            Tuple of (is_valid, list_of_warnings)
        """
        warnings = []

        # Check for too few agents
        if len(selected_agents) < 2:
            warnings.append("Only one agent selected. Consider adding a reviewer for quality.")

        # Check for too many agents
        if len(selected_agents) > 4:
            warnings.append(f"{len(selected_agents)} agents may create coordination overhead.")

        # Check for domain coverage
        primary_domain = task_characteristics.domains[0] if task_characteristics.domains else None
        if primary_domain:
            has_domain_expert = any(
                primary_domain in AGENT_CAPABILITIES.get(a.agent_id, {}).get("domains", [])
                for a in selected_agents
            )
            if not has_domain_expert:
                warnings.append(f"No agent with explicit {primary_domain} expertise selected.")

        # Check for high-risk without review
        if task_characteristics.risk_level in ["high", "critical"]:
            has_reviewer = any(a.role_in_swarm == "reviewer" for a in selected_agents)
            if not has_reviewer:
                warnings.append("High-risk task should include a reviewer agent.")

        # Check for conflicting agent combinations
        agent_ids = set(a.agent_id for a in selected_agents)

        # Example: Researcher + Writer without Analyst for complex synthesis
        if "researcher" in agent_ids and "writer" in agent_ids and len(agent_ids) == 2:
            if task_characteristics.complexity == "complex":
                warnings.append("Complex synthesis may benefit from an analyst for validation.")

        # Determine if selection is valid (warnings don't invalidate, only critical issues do)
        is_valid = len([w for w in warnings if "should" in w.lower() or "must" in w.lower()]) == 0

        return is_valid, warnings

    def suggest_improvements(
        self,
        selected_agents: List[AgentSelection],
        task_characteristics: TaskCharacteristics,
        available_agents: List[str]
    ) -> List[Dict]:
        """Suggest improvements to agent selection."""
        suggestions = []

        # Suggest adding analyst for complex tasks
        if task_characteristics.complexity == "complex" and "analyst" not in [a.agent_id for a in selected_agents]:
            suggestions.append({
                "type": "add_agent",
                "agent": "analyst",
                "rationale": "Complex tasks benefit from analytical validation"
            })

        # Suggest removing redundant agents
        agent_counts = {}
        for agent in selected_agents:
            agent_counts[agent.agent_id] = agent_counts.get(agent.agent_id, 0) + 1

        for agent_id, count in agent_counts.items():
            if count > 1:
                suggestions.append({
                    "type": "remove_redundant",
                    "agent": agent_id,
                    "rationale": f"Multiple {agent_id} agents may be redundant"
                })

        return suggestions
```

### 4.2 Prompt Quality Validation

```python
class PromptQualityChecker:
    """Validates generated prompts for quality and completeness."""

    REQUIRED_ELEMENTS = [
        "task_description",
        "role_definition",
        "deliverable_expectations",
    ]

    def validate_prompt(self, prompt: GeneratedPrompt) -> Tuple[bool, List[str]]:
        """Validate a generated prompt."""
        issues = []

        # Check prompt length
        if len(prompt.prompt) < 100:
            issues.append("Prompt is too short - may lack necessary context")
        elif len(prompt.prompt) > 4000:
            issues.append("Prompt is very long - may exceed context limits")

        # Check for required elements
        prompt_lower = prompt.prompt.lower()

        if "task" not in prompt_lower:
            issues.append("Prompt missing explicit task description")

        if any(word in prompt_lower for word in ["you are", "your role", "as a"]):
            pass  # Role is defined
        else:
            issues.append("Prompt missing role definition")

        if any(word in prompt_lower for word in ["deliver", "output", "return", "provide"]):
            pass  # Deliverable is mentioned
        else:
            issues.append("Prompt missing deliverable expectations")

        # Check for agent-specific requirements
        if prompt.agent_id == "developer" and "code" not in prompt_lower:
            issues.append("Developer prompt should explicitly mention code")

        if prompt.agent_id == "analyst" and "analysis" not in prompt_lower:
            issues.append("Analyst prompt should explicitly mention analysis")

        is_valid = len(issues) == 0
        return is_valid, issues
```

## 5. Integration with Existing System

### 5.1 Integration Points

The swarm-orchestrator integrates with existing components:

```python
class SwarmOrchestrator:
    """
    Main orchestrator that combines all components.

    Integrates with:
    - DelegationProtocol: For agent communication
    - MultiGoalDAG: For task dependency tracking
    - Neo4j: For operational memory
    """

    def __init__(
        self,
        delegation_protocol: DelegationProtocol,
        operational_memory: OperationalMemory,
        config: Optional[Dict] = None
    ):
        self.delegation = delegation_protocol
        self.memory = operational_memory
        self.config = config or {}

        # Initialize components
        self.task_analyzer = TaskAnalyzer()
        self.agent_selector = AgentSelectionEngine()
        self.prompt_generator = PromptGenerationEngine()
        self.pattern_selector = SwarmPatternSelector()
        self.safety_checker = SelectionSafetyChecker()
        self.prompt_checker = PromptQualityChecker()

    async def orchestrate(
        self,
        task_description: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: orchestrate a swarm for the given task.

        Returns complete orchestration plan including:
        - Selected agents with roles
        - Generated prompts
        - Recommended pattern
        - Execution plan
        """
        context = context or {}

        # Step 1: Analyze task
        characteristics = self.task_analyzer.analyze(task_description)

        # Step 2: Select agents
        selected_agents = self.agent_selector.select_agents(
            characteristics,
            max_agents=self.config.get("max_agents", 4),
            min_agents=self.config.get("min_agents", 2)
        )

        # Step 3: Validate selection
        is_valid, warnings = self.safety_checker.validate_selection(
            selected_agents, characteristics
        )

        if not is_valid:
            # Attempt to fix selection
            selected_agents = self._fix_selection(selected_agents, characteristics, warnings)

        # Step 4: Select pattern
        pattern_recommendation = self.pattern_selector.recommend_pattern(
            characteristics, selected_agents
        )

        # Step 5: Generate prompts
        prompts = self.prompt_generator.generate_prompts(
            task_description,
            characteristics,
            selected_agents,
            pattern_recommendation.pattern.value
        )

        # Step 6: Validate prompts
        for prompt in prompts:
            prompt_valid, prompt_issues = self.prompt_checker.validate_prompt(prompt)
            if not prompt_valid:
                logger.warning(f"Prompt issues for {prompt.agent_id}: {prompt_issues}")

        # Step 7: Store orchestration plan
        orchestration_id = await self._store_orchestration(
            task_description,
            characteristics,
            selected_agents,
            pattern_recommendation,
            prompts
        )

        return {
            "orchestration_id": orchestration_id,
            "task_characteristics": characteristics,
            "selected_agents": selected_agents,
            "pattern": pattern_recommendation,
            "prompts": prompts,
            "warnings": warnings,
            "execution_ready": True
        }

    async def execute_swarm(
        self,
        orchestration_plan: Dict[str, Any],
        async_execution: bool = True
    ) -> Dict[str, Any]:
        """
        Execute the orchestrated swarm.

        Uses DelegationProtocol to delegate to individual agents.
        """
        results = {}
        pattern = orchestration_plan["pattern"].pattern

        if pattern == SwarmPattern.PARALLEL:
            # Execute all agents in parallel
            tasks = []
            for prompt in orchestration_plan["prompts"]:
                task = self._delegate_to_agent(prompt)
                tasks.append(task)

            if async_execution:
                results = await asyncio.gather(*tasks, return_exceptions=True)

        elif pattern == SwarmPattern.SEQUENTIAL:
            # Execute agents sequentially
            for prompt in orchestration_plan["prompts"]:
                result = await self._delegate_to_agent(prompt)
                results[prompt.agent_id] = result

        # ... handle other patterns

        # Synthesize results
        synthesized = self._synthesize_results(results, orchestration_plan)

        return {
            "individual_results": results,
            "synthesized_output": synthesized,
            "status": "completed"
        }

    async def _delegate_to_agent(self, prompt: GeneratedPrompt) -> Dict[str, Any]:
        """Delegate task to agent via DelegationProtocol."""
        return self.delegation.delegate_task(
            task_description=prompt.prompt,
            context={
                "agent_id": prompt.agent_id,
                "swarm_context": prompt.context_injection
            },
            suggested_agent=prompt.agent_id
        )

    def _synthesize_results(
        self,
        results: Dict[str, Any],
        orchestration_plan: Dict[str, Any]
    ) -> str:
        """Synthesize individual agent results into cohesive output."""
        # Implementation depends on pattern and deliverable type
        pattern = orchestration_plan["pattern"].pattern

        if pattern == SwarmPattern.MULTI_PERSPECTIVE:
            return self._synthesize_multi_perspective(results)
        elif pattern == SwarmPattern.EXPERT_REVIEW:
            return self._synthesize_expert_review(results)
        else:
            return self._synthesize_default(results)
```

### 5.2 Neo4j Schema Extensions

```cypher
// SwarmOrchestration node
CREATE (:SwarmOrchestration {
  id: uuid,
  task_description: string,
  created_at: datetime,
  status: string,  // "planned" | "executing" | "completed" | "failed"

  // Task characteristics
  domains: [string],
  complexity: string,
  scope: string,
  risk_level: string,

  // Pattern
  pattern: string,
  pattern_confidence: float
});

// AgentAssignment relationship
(:SwarmOrchestration)-[:AGENT_ASSIGNMENT {
  role: string,  // "primary" | "reviewer" | "specialist"
  confidence: float,
  rationale: string,
  prompt: string  // The generated prompt
}]->(:Agent)

// ExecutionStep for tracking progress
CREATE (:ExecutionStep {
  id: uuid,
  step_number: int,
  agent_id: string,
  status: string,
  started_at: datetime,
  completed_at: datetime,
  result_summary: string
});

(:SwarmOrchestration)-[:HAS_STEP]->(:ExecutionStep)
```

## 6. Usage Examples

### Example 1: Security Audit Task

```python
# User request
 task = "Perform a comprehensive security audit of our authentication system"

# Orchestration result
{
    "orchestration_id": "swarm-001",
    "task_characteristics": {
        "domains": ["security", "code"],
        "complexity": "complex",
        "scope": "cross-cutting",
        "risk_level": "critical",
        "deliverable_type": "analysis"
    },
    "selected_agents": [
        {
            "agent_id": "developer",
            "agent_name": "Temüjin",
            "role_in_swarm": "primary",
            "rationale": "Primary executor for security audit work",
            "confidence": 0.95
        },
        {
            "agent_id": "analyst",
            "agent_name": "Jochi",
            "role_in_swarm": "reviewer",
            "rationale": "Quality assurance and risk mitigation",
            "confidence": 0.90
        },
        {
            "agent_id": "ops",
            "agent_name": "Ögedei",
            "role_in_swarm": "specialist",
            "rationale": "Infrastructure and deployment security",
            "confidence": 0.75
        }
    ],
    "pattern": {
        "pattern": "expert-review",
        "confidence": 0.92,
        "rationale": "Expert-review pattern selected due to critical risk level...",
        "execution_flow": [
            "1. Temüjin completes primary security audit",
            "2. Jochi, Ögedei review and validate",
            "3. Feedback incorporation",
            "4. Final approval"
        ],
        "expected_duration": "~3.0 hours"
    },
    "prompts": [
        {
            "agent_id": "developer",
            "prompt": "You are Temüjin, a development specialist...",
            "expected_output_format": "Security audit report with findings and recommendations"
        },
        // ... other prompts
    ]
}
```

### Example 2: Documentation Task

```python
# User request
task = "Write API documentation for our new payment endpoints"

# Orchestration result
{
    "task_characteristics": {
        "domains": ["writing", "code"],
        "complexity": "moderate",
        "scope": "narrow",
        "risk_level": "medium"
    },
    "selected_agents": [
        {
            "agent_id": "writer",
            "agent_name": "Chagatai",
            "role_in_swarm": "primary"
        },
        {
            "agent_id": "developer",
            "agent_name": "Temüjin",
            "role_in_swarm": "specialist"
        }
    ],
    "pattern": {
        "pattern": "sequential",
        "rationale": "Sequential workflow optimal for documentation with technical review"
    }
}
```

## 7. Implementation Roadmap

### Phase 1: Core Engine (Week 1)
- Implement TaskAnalyzer
- Implement AgentSelectionEngine
- Basic prompt generation

### Phase 2: Pattern Support (Week 2)
- Implement SwarmPatternSelector
- Add all five swarm patterns
- Pattern-specific decomposition logic

### Phase 3: Safety & Quality (Week 3)
- Implement SelectionSafetyChecker
- Implement PromptQualityChecker
- Add validation and improvement suggestions

### Phase 4: Integration (Week 4)
- Integrate with DelegationProtocol
- Neo4j schema extensions
- End-to-end testing

### Phase 5: Optimization (Week 5)
- Historical performance learning
- Agent capability calibration
- Pattern effectiveness tracking

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent Selection Accuracy | >85% | Human review of selections |
| Prompt Quality Score | >4.0/5 | Agent feedback on prompt clarity |
| Pattern Appropriateness | >90% | Post-execution review |
| Task Completion Rate | >95% | Successful swarm executions |
| Average Swarm Size | 2.5-3.5 | Optimal team size tracking |
| Safety Trigger Rate | <10% | How often safety checks intervene |

## 9. Conclusion

The `swarm-orchestrator` agent provides intelligent, automated composition of agent teams for the horde-swarm pattern. By analyzing task characteristics, selecting optimal agents, generating tailored prompts, and recommending appropriate patterns, it eliminates manual agent selection while ensuring high-quality outcomes through built-in safety mechanisms.

The system is designed to integrate seamlessly with the existing OpenClaw multi-agent infrastructure, leveraging the DelegationProtocol for agent communication and Neo4j for operational memory.
