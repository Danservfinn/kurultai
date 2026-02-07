# Autonomous Skill Acquisition Architecture for Kurultai

> **Status**: Design Proposal
> **Date**: 2026-02-04
> **Version**: 0.1

## Executive Summary

This document outlines an architecture for Kurultai's 6-agent system to autonomously learn new skills without human intervention. The system extends the existing Neo4j-backed memory with a dedicated skill graph, enabling agents to discover capability gaps, research solutions, practice in safe environments, validate mastery, and encode reusable skills.

---

## Table of Contents

1. [Skill Learning Loop](#1-skill-learning-loop)
2. [Example Walkthrough: Learning to Call Someone](#2-example-walkthrough-learning-to-call-someone)
3. [Neo4j Skill Schema](#3-neo4j-skill-schema)
4. [Autonomous Skill Discovery](#4-autonomous-skill-discovery)
5. [Risks & Mitigation](#5-risks--mitigation)
6. [Implementation Phases](#6-implementation-phases)

---

## 1. Skill Learning Loop

The skill learning loop consists of four phases that execute autonomously:

```
                    +------------------------+
                    |   CAPABILITY GAP       |
                    |   (Task requires skill |
                    |    agent doesn't have) |
                    +-----------+------------+
                                |
                                v
        +-----------------------+-----------------------+
        |                                               |
        v                                               v
+------------------+                         +------------------+
|  PHASE 1:        |                         |  PHASE 2:        |
|  RESEARCH        |                         |  PRACTICE        |
|  - Find docs     |                         |  - Sandbox env   |
|  - Learn API     |----------------------->|  - Test calls    |
|  - Plan approach |                         |  - Debug errors  |
+------------------+                         +------------------+
        |                                               |
        |                                               v
        |                                       +------------------+
        |                                       |  PHASE 3:        |
        |                                       |  VALIDATION      |
        |                                       |  - Test suite    |
        |                                       |  - Success rate  |
        |                                       |  - Edge cases    |
        |                                       +------------------+
        |                                               |
        +-----------------------+-----------------------+
                                |
                                v
                       +------------------+
                       |  PHASE 4:        |
                       |  STORAGE         |
                       |  - Encode skill  |
                       |  - Store in Neo4j|
                       |  - Mark mastered |
                       +------------------+
                                |
                                v
                       +------------------+
                       |  SKILL ACTIVE    |
                       |  (Reusable for   |
                       |   future tasks)  |
                       +------------------+
```

### Phase 1: Research (Autonomous Information Gathering)

**Goal**: Understand what is required to perform the skill

**Process**:

1. **Capability Gap Detection**
   ```cypher
   // Agent recognizes missing capability during task execution
   MATCH (task:Task {id: $task_id})-[:REQUIRES_SKILL]->(missing:Skill)
   WHERE NOT (agent:Agent {id: $agent_id})-[:KNOWS]->(missing)
   RETURN missing
   ```

2. **Research Task Creation**
   ```python
   # Create autonomous research task for Mongke (researcher agent)
   research_task = memory.create_skill_research_task(
       skill_name="twilio_voice_call",
       assigned_to="researcher",
       priority="high",  # Based on task urgency
       research_questions=[
           "What API provides this capability?",
           "What are the authentication requirements?",
           "What are the costs and rate limits?",
           "What are common failure modes?"
       ]
   )
   ```

3. **Information Gathering** (Mongke executes)
   - Web search for official documentation
   - API reference exploration
   - Code example discovery
   - Pricing/rate limit analysis
   - Security consideration research

4. **Research Output Storage**
   ```cypher
   CREATE (r:SkillResearch {
       id: $research_id,
       skill_name: "twilio_voice_call",
       api_provider: "Twilio",
       api_version: "2010-04-01",
       auth_method: "API Key + Account SID",
       base_url: "https://api.twilio.com",
       cost_per_call: 0.013,  // USD
       rate_limit: "1/second",
       common_errors: ["authentication_failed", "insufficient_funds", "invalid_number"],
       security_considerations: ["store_credentials_secrets", "validate_phone_numbers"],
       research_status: "complete",
       confidence: 0.92
   })
   ```

### Phase 2: Practice (Safe Environment Execution)

**Goal**: Execute the skill in a controlled, safe environment

**Process**:

1. **Sandbox Environment Setup**
   ```python
   # Create isolated practice environment
   sandbox = SkillSandbox(
       skill="twilio_voice_call",
       environment="test",  # Use Twilio Test Credentials
       cost_limit=0.50,     # Maximum $0.50 for practice
       call_limit=5,        // Maximum 5 test calls
       monitoring=True      # Log all attempts
   )
   ```

2. **Iterative Practice Loop**
   ```python
   practice_session = SkillPracticeSession(
       skill_id=skill_id,
       agent_id="developer",  # Temujin learns technical skill
       max_attempts=10,
       success_threshold=0.8
   )

   for attempt in range(practice_session.max_attempts):
       result = practice_session.attempt(
           action="make_call",
           parameters={
               "to": test_phone_number,
               "from": test_twilio_number,
               "message": "This is a test call from Kurultai skill learning system."
           }
       )

       if result.success:
           practice_session.record_success(result)
       else:
           practice_session.record_failure(result)
           # Analyze error and retry with correction
           correction = analyze_error(result.error)
           practice_session.apply_correction(correction)

       if practice_session.success_rate >= practice_session.success_threshold:
           break
   ```

3. **Error Pattern Learning**
   ```cypher
   // Store observed error patterns for future reference
   CREATE (e:SkillErrorPattern {
       skill_id: $skill_id,
       error_type: "authentication_failed",
       frequency: 3,
       solutions: [
           "Verify ACCOUNT_SID is correct",
           "Verify AUTH_TOKEN matches account",
           "Check for trailing whitespace in credentials"
       ],
       resolved: true
   })
   ```

### Phase 3: Validation (Automated Testing)

**Goal**: Confirm skill mastery before production use

**Process**:

1. **Test Suite Generation**
   ```python
   validation_suite = SkillValidationSuite(
       skill_id=skill_id,
       test_cases=[
           {
               "name": "basic_call",
               "description": "Make a simple voice call",
               "params": {"to": VALID_TEST_NUMBER, "message": "Test"},
               "expected_result": "call_connected",
               "weight": 1.0
           },
           {
               "name": "invalid_number_handling",
               "description": "Handle invalid phone numbers gracefully",
               "params": {"to": "+1-invalid", "message": "Test"},
               "expected_result": "error_handled",
               "weight": 0.8
           },
           {
               "name": "rate_limit_respect",
               "description": "Respect API rate limits",
               "params": {"rapid_calls": 5},
               "expected_result": "no_rate_limit_error",
               "weight": 0.9
           }
       ]
   )
   ```

2. **Execution & Scoring**
   ```python
   validation_result = validation_suite.run()

   skill_mastery_score = calculate_mastery_score(
       pass_rate=validation_result.pass_rate,
       test_weights=validation_result.weights,
       edge_case_coverage=validation_result.edge_cases_passed,
       error_handling_quality=validation_result.error_recovery_score
   )
   ```

3. **Mastery Threshold Check**
   ```python
   MASTERY_THRESHOLD = 0.85  # 85% score required

   if skill_mastery_score >= MASTERY_THRESHOLD:
       skill.status = "mastered"
       skill.available_for_production = True
   elif skill_mastery_score >= 0.6:
       skill.status = "learning"
       skill.available_for_production = False
       # Schedule more practice sessions
   else:
       skill.status = "failed"
       # Research alternative approaches
   ```

### Phase 4: Storage (Neo4j Encoding)

**Goal**: Persist learned skill for future retrieval

**Process**:

1. **Skill Node Creation**
   ```cypher
   CREATE (s:Skill {
       id: $skill_id,
       name: "twilio_voice_call",
       category: "communication",
       description: "Make outbound voice calls using Twilio API",
       capability: "api_integration",
       status: "mastered",
       mastery_score: 0.92,
       cost_per_use: 0.013,
       requires_secrets: true,
       secret_keys: ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
       api_endpoint: "https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Calls.json",
       api_method: "POST",
       created_at: datetime(),
       last_validated: datetime(),
       validation_interval_days: 30,  // Re-validate monthly
       usage_count: 0,
       success_rate: 0.0  // Will update with real usage
   })
   ```

2. **Agent-Skill Association**
   ```cypher
   // Mark which agents know this skill
   MATCH (agent:Agent {id: "developer"})
   MATCH (skill:Skill {id: $skill_id})
   CREATE (agent)-[:KNOWS {
       learned_at: datetime(),
       mastery_level: "expert",
       practice_hours: 2.5,
       last_used: null
   }]->(skill)
   ```

3. **Dependency Tracking**
   ```cypher
   // Skills often depend on other skills
   CREATE (s1:Skill {name: "twilio_voice_call"})
   CREATE (s2:Skill {name: "http_request"})
   CREATE (s3:Skill {name: "secret_management"})
   CREATE (s1)-[:REQUIRES]->(s2)
   CREATE (s1)-[:REQUIRES]->(s3)
   ```

---

## 2. Example Walkthrough: Learning to Call Someone

### Scenario: User asks "Call Sarah and tell her the meeting is at 3pm"

### Step 1: Task Analysis & Gap Detection

```
Kublai receives request
    |
    v
Parse intent: "Make phone call with message"
    |
    v
Check available skills
    |
    +--> Skill: send_email (Known)
    +--> Skill: send_signal_message (Known)
    +--> Skill: make_voice_call (NOT KNOWN) <-- GAP
    |
    v
Create autonomous learning task
```

### Step 2: Research Phase (Mongke - Researcher)

```python
# Research task created automatically
research_task = {
    "agent": "researcher",
    "goal": "Learn how to make voice calls programmatically",
    "requirements": [
        "Find API providers for voice calls",
        "Compare costs and features",
        "Identify authentication method",
        "Document rate limits and constraints"
    ]
}
```

**Mongke's research process**:

1. **Web Search**: "programmatic voice call API", "best VOIP API 2026"
2. **Documentation Discovery**: Twilio, Plivo, SignalWire, Vonage
3. **Comparison Analysis**:
   ```
   Provider    Cost/Min  Setup    Rate Limit   Free Tier
   --------    --------  -----    -----------  ----------
   Twilio      $0.013    Easy     1/sec       $10 credit
   Plivo       $0.008    Medium   5/sec       $10 credit
   SignalWire  $0.009    Complex  10/sec      $5 credit
   Vonage      $0.015    Medium   1/sec       None
   ```
4. **Recommendation**: Twilio (easiest setup, good docs, widely used)

### Step 3: Practice Phase (Temujin - Developer)

```python
# Sandbox setup for testing
test_credentials = {
    "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_TEST_ACCOUNT_SID"),
    "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_TEST_AUTH_TOKEN"),
    "TWILIO_PHONE_NUMBER": "+15550000000"  # Test number
}

# Practice loop
practice_attempts = [
    {
        "attempt": 1,
        "action": "make_call",
        "params": {"to": "+15550000001", "message": "Test call 1"},
        "result": "SUCCESS",
        "duration": "3.2s"
    },
    {
        "attempt": 2,
        "action": "make_call",
        "params": {"to": "invalid", "message": "Test call 2"},
        "result": "ERROR",
        "error": "Invalid phone number format"
    },
    # ... more attempts
]
```

**Code generated by Temujin**:

```python
# Stored as part of the skill
def make_voice_call(to: str, message: str, max_retries: int = 3) -> dict:
    """
    Make a voice call using Twilio API.

    Args:
        to: Phone number to call (E.164 format)
        message: Text-to-speech message
        max_retries: Retry attempts on transient failures

    Returns:
        dict with call_status, call_sid, and error if any
    """
    from twilio.rest import Client
    import os

    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

    try:
        call = client.calls.create(
            twiml=f'<Response><Say>{message}</Say></Response>',
            to=to,
            from_=os.getenv("TWILIO_PHONE_NUMBER")
        )
        return {
            "status": "success",
            "call_sid": call.sid,
            "call_status": call.status
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
```

### Step 4: Validation Phase (Jochi - Analyst)

```python
# Validation test suite
test_cases = [
    {"name": "valid_call", "to": "+15550000001", "expected": "success"},
    {"name": "invalid_number", "to": "+1-abc", "expected": "error_handled"},
    {"name": "long_message", "message": "x"*1000, "expected": "truncated"},
    {"name": "rate_limit", "calls": 10, "expected": "backoff_applied"}
]

results = run_validation_suite(test_cases)
mastery_score = calculate_score(results)
# Result: 0.91 (above 0.85 threshold)
```

### Step 5: Storage Phase (Neo4j)

```cypher
// Skill is now encoded and available
CREATE (s:Skill {
    id: "skill_twilio_voice_call_v1",
    name: "twilio_voice_call",
    category: "communication",
    status: "mastered",
    mastery_score: 0.91,
    cost_per_use: 0.013,
    created_at: datetime()
})

// Associate with Temujin (who learned it)
MATCH (t:Agent {id: "developer"})
CREATE (t)-[:KNOWS {mastery: "expert"}]->(s)

// Make available to all agents (shared capability)
MATCH (a:Agent)
CREATE (a)-[:CAN_USE]->(s)
```

### Step 6: Execution

```python
# Now Kublai can complete the original request
result = execute_skill(
    skill="twilio_voice_call",
    params={
        "to": sarah_phone_number,  # Retrieved from personal context
        "message": "Hi Sarah, this is Kurultai. Your meeting is scheduled for 3 PM today."
    }
)
```

---

## 3. Neo4j Skill Schema

### Core Skill Nodes

```cypher
// Primary skill node
(:Skill {
    id: string,              // UUID
    name: string,            // e.g., "twilio_voice_call"
    category: string,        // "communication", "data", "automation"
    capability: string,      // "api_integration", "web_scraping", "data_analysis"
    description: string,
    status: string,          // "researching" | "practicing" | "validating" | "mastered" | "deprecated"

    // Mastery tracking
    mastery_score: float,    // 0-1
    last_validated: datetime,
    validation_interval_days: int,

    // Usage tracking
    usage_count: int,
    success_count: int,
    failure_count: int,
    last_used: datetime,

    // Cost tracking
    cost_per_use: float,     // USD
    cost_limit: float,       // Maximum per task

    // API specifics (if applicable)
    api_endpoint: string,
    api_method: string,
    api_version: string,
    auth_method: string,

    // Security
    requires_secrets: boolean,
    secret_keys: [string],   // Names of required env vars

    // Dependencies
    requires_setup: boolean, // Needs account/service registration
    setup_instructions: string,

    // Metadata
    created_at: datetime,
    created_by: string,      // Agent ID
    version: int,            // Skill version for evolution

    // Embedding for semantic search
    embedding: [float]       // 384-dim vector
})

// Learning progress tracker
(:SkillLearningSession {
    id: string,
    skill_id: string,
    agent_id: string,
    phase: string,           // "research" | "practice" | "validation"
    started_at: datetime,
    completed_at: datetime,
    status: string,          // "in_progress" | "completed" | "failed"
    progress_score: float,   // 0-1
    notes: string,
    errors_encountered: int,
    breakthroughs: [string]
})

// Research findings
(:SkillResearch {
    id: string,
    skill_name: string,
    api_provider: string,
    api_documentation_url: string,
    auth_method: string,
    pricing_model: string,
    rate_limits: string,
    security_considerations: [string],
    common_errors: [string],
    alternative_providers: [string],
    confidence: float,       // Research quality score
    created_at: datetime
})

// Practice attempts
(:SkillPracticeAttempt {
    id: string,
    skill_id: string,
    agent_id: string,
    attempt_number: int,
    action: string,
    parameters: map,
    result: string,          // "success" | "failure" | "partial"
    output: string,
    error_message: string,
    execution_time_ms: int,
    cost_incurred: float,
    timestamp: datetime
})

// Validation results
(:SkillValidation {
    id: string,
    skill_id: string,
    test_suite_version: int,
    total_tests: int,
    passed_tests: int,
    failed_tests: int,
    pass_rate: float,
    edge_cases_passed: int,
    edge_cases_total: int,
    mastery_score: float,
    validated_at: datetime,
    validated_by: string,
    next_validation_due: datetime
})

// Error patterns learned
(:SkillErrorPattern {
    id: string,
    skill_id: string,
    error_type: string,
    error_pattern: string,
    frequency: int,
    solutions: [string],
    prevention_strategy: string,
    resolved: boolean
})

// Skill dependencies
(:SkillDependency {
    requires_skill: string,  // Skill ID
    required_skill: string,  // Skill ID
    dependency_type: string, // "direct" | "indirect" | "optional"
    reason: string
})
```

### Relationships

```cypher
// Skill ownership and knowledge
(Agent)-[:KNOWS {mastery, learned_at, practice_hours}]->(Skill)
(Agent)-[:CAN_USE]->(Skill)  // Available to use even if not expert

// Learning process
(Agent)-[:RESEARCHED]->(SkillResearch)
(SkillResearch)-[:ENABLES]->(Skill)
(Agent)-[:PRACTICED]->(SkillPracticeAttempt)
(SkillPracticeAttempt)-[:IMPROVES]->(Skill)
(Agent)-[:VALIDATED]->(SkillValidation)
(SkillValidation)-[:CONFIRMS]->(Skill)

// Dependencies
(Skill)-[:REQUIRES]->(Skill)

// Task-skill relationship
(Task)-[:REQUIRES_SKILL]->(Skill)

// Error patterns
(Skill)-[:HAS_ERROR_PATTERN]->(SkillErrorPattern)
```

### Indexes for Performance

```cypher
// Skill lookup indexes
CREATE INDEX skill_name FOR (s:Skill) ON (s.name, s.status);
CREATE INDEX skill_category FOR (s:Skill) ON (s.category, s.status);
CREATE INDEX skill_mastery FOR (s:Skill) ON (s.status, s.mastery_score);

// Learning session indexes
CREATE INDEX learning_session_agent FOR (l:SkillLearningSession)
    ON (l.agent_id, l.status, l.started_at);

// Practice attempt indexes
CREATE INDEX practice_attempt_skill FOR (p:SkillPracticeAttempt)
    ON (p.skill_id, p.timestamp);

// Validation indexes
CREATE INDEX validation_due FOR (v:SkillValidation)
    ON (v.next_validation_due);

// Vector index for semantic skill search
CREATE VECTOR INDEX skill_embedding FOR (s:Skill)
    ON s.embedding OPTIONS {indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }};
```

### Example Queries

```cypher
// Find skills needed but not yet known
MATCH (t:Task {id: $task_id})-[:REQUIRES_SKILL]->(s:Skill)
WHERE NOT (agent:Agent {id: $agent_id})-[:KNOWS]->(s)
RETURN s.name, s.category

// Find similar skills for transfer learning
MATCH (s:Skill {id: $known_skill_id})
CALL db.index.vector.queryNodes('skill_embedding', 5, s.embedding)
YIELD node, score
RETURN node.name, node.category, score

// Get skill mastery summary
MATCH (a:Agent {id: $agent_id})-[k:KNOWS]->(s:Skill)
RETURN s.name, s.category, k.mastery, s.mastery_score
ORDER BY s.mastery_score DESC

// Find skills needing re-validation
MATCH (v:SkillValidation)
WHERE v.next_validation_due < datetime()
MATCH (v)-[:CONFIRMS]->(s:Skill)
RETURN s.name, v.mastery_score, v.next_validation_due

// Practice performance trend
MATCH (p:SkillPracticeAttempt {skill_id: $skill_id})
WITH p, p.attempt_number as attempt
ORDER BY attempt ASC
RETURN attempt, p.result
```

---

## 4. Autonomous Skill Discovery

### Gap Analysis

**How does Kurultai identify missing capabilities?**

```python
def analyze_capability_gaps(task_description: str, agent_id: str) -> List[str]:
    """
    Analyze a task to identify required but missing skills.
    """
    # Step 1: Parse task into capability requirements
    required_capabilities = extract_capabilities(task_description)
    # Example: "Call Sarah" -> ["voice_call", "contact_lookup"]

    # Step 2: Check which capabilities are available
    available_skills = get_agent_skills(agent_id)

    # Step 3: Identify gaps
    gaps = []
    for capability in required_capabilities:
        matching_skill = find_skill_for_capability(capability)
        if not matching_skill:
            gaps.append({
                "capability": capability,
                "status": "unknown",
                "action": "initiate_research"
            })
        elif matching_skill not in available_skills:
            gaps.append({
                "capability": capability,
                "status": "known_but_not_learned",
                "skill_id": matching_skill.id,
                "action": "initiate_learning"
            })

    return gaps
```

### Opportunity Sensing

**How does Kurultai discover money-making or improvement opportunities?**

```cypher
// Opportunity pattern: Repeated manual tasks
MATCH (t:Task)
WHERE t.description =~ ".*(?i)(manual|hand|repeat).*"
WITH t.type as task_type, count(t) as frequency
WHERE frequency > 3
RETURN task_type, frequency
ORDER BY frequency DESC

// Opportunity: Tasks that failed due to missing capability
MATCH (t:Task {result_status: "failed"})
WHERE t.blocked_reason CONTAINS "cannot" OR t.blocked_reason CONTAINS "unable"
RETURN t.description, t.blocked_reason
```

**Proactive Opportunity Discovery**:

```python
class OpportunityScanner:
    """
    Periodically scans for opportunities to learn new skills.
    Runs daily as a background task.
    """

    def scan_repeated_patterns(self):
        """Find tasks that repeat frequently - automation candidates."""
        query = """
        MATCH (t:Task)
        WHERE t.created_at > datetime() - duration({days: 30})
        WITH t.type as task_type, t.description as desc, count(t) as freq
        WHERE freq > 5
        RETURN task_type, desc, freq
        ORDER BY freq DESC
        """
        # Results suggest automation opportunities

    def scan_failure_patterns(self):
        """Find failures that suggest missing capabilities."""
        query = """
        MATCH (t:Task {result_status: "failed"})
        WHERE t.completed_at > datetime() - duration({days: 7})
        AND t.blocked_reason IS NOT NULL
        RETURN t.blocked_reason, count(t) as freq
        ORDER BY freq DESC
        """
        # Results suggest skills to learn

    def scan_external_trends(self):
        """Research emerging capabilities that could be valuable."""
        # Mongke runs periodic research on:
        # - New AI capabilities
        # - New API integrations
        # - New automation opportunities
        pass
```

### Learning Priority

**How does Kurultai decide what to learn first?**

```python
def calculate_learning_priority(skill_candidate: dict) -> float:
    """
    Calculate priority score for learning a new skill.
    Higher score = learn first.
    """
    score = 0

    # Factor 1: Urgency (how soon is it needed?)
    if skill_candidate["blocking_task_count"] > 0:
        score += 50 * skill_candidate["blocking_task_count"]

    # Factor 2: Frequency (how often will it be used?)
    score += 20 * skill_candidate["estimated_usage_frequency"]

    # Factor 3: Impact (how much value does it create?)
    score += 15 * skill_candidate["value_estimate"]

    # Factor 4: Feasibility (how easy is it to learn?)
    score += 10 * (1 / skill_candidate["estimated_learning_hours"])

    # Factor 5: Cost (is it affordable?)
    if skill_candidate["cost_per_use"] > 1.0:
        score -= 10  # Penalize expensive skills

    # Factor 6: Dependency chain (does it unlock other skills?)
    score += 5 * skill_candidate["enables_skill_count"]

    return score
```

---

## 5. Risks & Mitigation

### Risk 1: Accidental High Costs

**Scenario**: Agent practicing skill makes thousands of API calls, incurring large bill.

**Mitigations**:
```python
class SkillSandbox:
    """Enforces strict limits on skill practice."""

    MAX_COST_PER_SESSION = 1.00  # $1 maximum per practice
    MAX_ATTEMPTS_PER_SESSION = 10
    ALERT_THRESHOLD = 0.50  # Alert at 50 cents

    def __init__(self, skill_id: str):
        self.cost_tracker = CostTracker()
        self.alert_sent = False

    def check_limits_before_action(self, estimated_cost: float):
        current_cost = self.cost_tracker.get_session_cost()

        if current_cost + estimated_cost > self.MAX_COST_PER_SESSION:
            raise SandboxLimitExceeded(
                f"Cost limit ${self.MAX_COST_PER_SESSION} would be exceeded"
            )

        if not self.alert_sent and current_cost > self.ALERT_THRESHOLD:
            send_alert_to_kublai(
                f"Skill practice at ${current_cost:.2f} / ${self.MAX_COST_PER_SESSION}"
            )
            self.alert_sent = True
```

**Neo4j Safeguard**:
```cypher
// Track skill costs at graph level
MATCH (s:Skill {id: $skill_id})
SET s.total_cost_spent = coalesce(s.total_cost_spent, 0) + $new_cost

// Auto-disable expensive skills
MATCH (s:Skill)
WHERE s.total_cost_spent > 100.0  // $100 lifetime limit
SET s.status = "cost_limit_exceeded"
```

### Risk 2: Secret/Credential Exposure

**Scenario**: Agent accidentally leaks API keys in logs or shared content.

**Mitigations**:
```python
class SecretManager:
    """Manages secrets for skill execution."""

    FORBIDDEN_PATTERNS = [
        r'account[_-]?sid',
        r'auth[_-]?token',
        r'api[_-]?key',
        r'secret[_-]?key',
        r'password'
    ]

    def sanitize_output(self, output: str) -> str:
        """Remove potential secrets from output before storing."""
        import re

        # Redact secret values
        for pattern in self.FORBIDDEN_PATTERNS:
            output = re.sub(
                f'{pattern}["\']?\s*[:=]\s*["\']?[\w-]+',
                f'{pattern}=[REDACTED]',
                output,
                flags=re.IGNORECASE
            )

        # Redact things that look like secrets
        output = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[REDACTED]', output)

        return output

    def check_for_secrets_before_sharing(self, content: str, tier: str) -> bool:
        """Prevent sharing content with secrets to Neo4j."""
        if tier == "SENSITIVE":
            # Extra scrutiny for sensitive content
            return True
        return False
```

### Risk 3: Infinite Learning Loops

**Scenario**: Agent gets stuck trying to learn a skill, wasting resources.

**Mitigations**:
```python
class LearningLimiter:
    """Prevents infinite learning loops."""

    MAX_LEARNING_HOURS = 4  # Per skill
    MAX_RESEARCH_ATTEMPTS = 3
    MAX_PRACTICE_ATTEMPTS = 20
    LEARNING_TIMEOUT = 3600  # 1 hour per session

    def should_abort_learning(self, session: SkillLearningSession) -> bool:
        if session.attempt_count > self.MAX_PRACTICE_ATTEMPTS:
            return True
        if session.duration_hours > self.MAX_LEARNING_HOURS:
            return True
        if session.success_rate_trend == "flat" and session.attempt_count > 5:
            return True  # Not improving
        return False
```

### Risk 4: Skill Degradation (API Changes)

**Scenario**: Learned skill becomes outdated when API changes.

**Mitigations**:
```cypher
// Periodic validation triggers
CREATE (s:Skill {
    validation_interval_days: 30,
    last_validated: datetime(),
    next_validation_due: datetime() + duration({days: 30})
})

// Daily job checks for skills needing validation
MATCH (s:Skill {status: "mastered"})
WHERE s.next_validation_due < datetime()
RETURN s.name, s.id
```

```python
async def validate_skill(skill_id: str) -> bool:
    """Re-validate a skill to ensure it still works."""

    # Re-run test suite
    result = await run_validation_suite(skill_id)

    if result.pass_rate < 0.7:
        # Skill degraded - flag for re-learning
        memory.update_skill(
            skill_id=skill_id,
            status="degraded",
            degradation_reason="API may have changed"
        )
        return False

    # Update validation timestamp
    memory.update_skill(
        skill_id=skill_id,
        last_validated=datetime.now(),
        next_validation_due=datetime.now() + timedelta(days=30)
    )
    return True
```

### Risk 5: Malicious Content from Research

**Scenario**: Research phase returns incorrect or malicious information.

**Mitigations**:
```python
class ResearchValidator:
    """Validates research findings before use."""

    TRUSTED_SOURCES = [
        'docs.twilio.com',
        'developer.mozilla.org',
        'docs.python.org',
        'platform.openai.com'
    ]

    def validate_research(self, research: SkillResearch) -> bool:
        # Check source credibility
        if research.source_domain not in self.TRUSTED_SOURCES:
            research.confidence *= 0.5

        # Cross-reference with multiple sources
        if research.source_count < 2:
            research.confidence *= 0.8

        # Check for known malicious patterns
        if self._contains_malicious_patterns(research.content):
            return False

        return research.confidence > 0.6
```

---

## 6. Implementation Phases

### Phase 1: Skill Schema Foundation (Week 1-2)

**Goal**: Extend Neo4j schema with skill nodes

**Tasks**:
- Add Skill node types to schema
- Create indexes for skill queries
- Add vector index for semantic skill search
- Implement skill CRUD operations
- Write migration script

**Deliverable**:
- Skills can be stored and queried in Neo4j
- Basic skill lifecycle (create, update, deprecate)

### Phase 2: Research Module (Week 3-4)

**Goal**: Enable autonomous research capability

**Tasks**:
- Create SkillResearch node and operations
- Implement web search integration
- Build documentation parser
- Add research validation
- Create research result summarization

**Deliverable**:
- Mongke can autonomously research APIs and document findings
- Research results stored in Neo4j

### Phase 3: Practice Sandbox (Week 5-6)

**Goal**: Safe environment for skill practice

**Tasks**:
- Implement SkillSandbox with cost limits
- Create attempt tracking
- Build error pattern detection
- Add cost monitoring and alerts
- Implement practice session management

**Deliverable**:
- Temujin can practice skills with enforced limits
- All attempts tracked for learning

### Phase 4: Validation Framework (Week 7-8)

**Goal**: Automated skill validation

**Tasks**:
- Build validation test suite generator
- Implement mastery scoring
- Create validation result storage
- Add periodic re-validation job
- Implement skill degradation detection

**Deliverable**:
- Skills validated before production use
- Automatic re-validation on schedule

### Phase 5: Integration & Orchestration (Week 9-10)

**Goal**: End-to-end skill learning loop

**Tasks**:
- Implement gap detection
- Build learning priority calculator
- Create skill opportunity scanner
- Add skill execution layer
- Integrate with existing task system

**Deliverable**:
- Full autonomous skill learning loop operational
- Agents can learn skills without human intervention

### Phase 6: Safety & Guardrails (Week 11-12)

**Goal**: Production-safe skill learning

**Tasks**:
- Add cost limits and monitoring
- Implement secret sanitization
- Build learning loop prevention
- Add skill rollback capability
- Create skill audit logging

**Deliverable**:
- Production-ready skill learning with full safety measures

---

## Appendix: Example Skill Execution

```python
async def execute_skill(
    skill_name: str,
    parameters: dict,
    agent_id: str
) -> dict:
    """
    Execute a learned skill with proper error handling and tracking.
    """

    # 1. Verify agent knows the skill
    skill = memory.get_skill(skill_name)
    if not skill or skill.status != "mastered":
        raise SkillNotReady(f"Skill {skill_name} is not ready for use")

    # 2. Check for required secrets
    if skill.requires_secrets:
        for key in skill.secret_keys:
            if not os.getenv(key):
                raise SecretMissing(f"Required secret {key} not found")

    # 3. Enforce cost limits
    if skill.cost_per_use > 0:
        current_cost = memory.get_agent_skill_cost(agent_id, skill_name)
        if current_cost > skill.cost_limit:
            raise CostLimitExceeded(f"Cost limit exceeded for {skill_name}")

    # 4. Execute with tracking
    execution_id = str(uuid4())
    result = None

    try:
        # Execute skill function
        result = await SKILL_FUNCTIONS[skill_name](**parameters)

        # Record success
        memory.record_skill_execution(
            execution_id=execution_id,
            skill_id=skill.id,
            agent_id=agent_id,
            status="success",
            result=result
        )

        return result

    except Exception as e:
        # Record failure
        memory.record_skill_execution(
            execution_id=execution_id,
            skill_id=skill.id,
            agent_id=agent_id,
            status="error",
            error=str(e)
        )

        # Check if error pattern is known
        error_pattern = memory.get_error_pattern(skill.id, type(e).__name__)
        if error_pattern:
            # Try known solution
            return await apply_solution(error_pattern, parameters)

        raise
```

---

## Summary

The autonomous skill acquisition architecture enables Kurultai to:

1. **Self-identify capability gaps** through task analysis
2. **Autonomously research** solutions using web search and documentation
3. **Practice safely** in sandboxed environments with cost limits
4. **Validate mastery** through automated test suites
5. **Encode skills** in Neo4j for future retrieval
6. **Continuously monitor** skill health and re-validate as needed

The design builds on the existing Neo4j memory architecture and integrates seamlessly with the 6-agent system, with each agent playing to their strengths:
- **Mongke (Researcher)**: Discovers and documents capabilities
- **Temujin (Developer)**: Implements and practices technical skills
- **Jochi (Analyst)**: Validates and scores mastery
- **Kublai (Orchestrator)**: Coordinates the learning loop
- **Ogedei (Ops)**: Manages learning schedules and resources
- **Chagatai (Writer)**: Documents skills for knowledge sharing
