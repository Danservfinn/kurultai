# LLM-Based Engagement Assessment System

**Version:** 1.0
**Date:** 2026-03-19
**Status:** Design Document (Pre-Implementation)
**Replaces:** Regex-based engagement scoring (rated 3/10)

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [System Architecture](#2-system-architecture)
3. [Safety Layer (Pre-LLM)](#3-safety-layer-pre-llm)
4. [Context Assembly](#4-context-assembly)
5. [Assessment Prompt](#5-assessment-prompt)
6. [Output Schema](#6-output-schema)
7. [Model Selection](#7-model-selection)
8. [Learning Loop](#8-learning-loop)
9. [Cost Analysis](#9-cost-analysis)
10. [The Superintelligent Being Factor](#10-the-superintelligent-being-factor)
11. [Implementation Plan](#11-implementation-plan)

---

## 1. Design Principles

The previous system failed review because it used regex intent classification as its highest-weighted feature. That is a categorical error: regex captures surface tokens, not communicative intent. A message like "k" from a terse founder means "acknowledged, proceed" and warrants a response. The same "k" from someone closing a conversation means "goodbye" and warrants silence. No regex can distinguish these.

**Principles governing this design:**

1. **No hand-tuned weights without empirical justification.** Every parameter that affects the decision must either (a) come from a model that was trained/prompted with examples, or (b) be derived from measured outcomes. The one exception is the safety layer, which uses hard overrides for ethical reasons, not accuracy reasons.

2. **The LLM is the classifier.** Intent classification, urgency detection, conversational state estimation, and response depth selection are all done by the LLM in a single structured-output call. The LLM sees the actual conversation context. Regex sees character patterns.

3. **Calibrated confidence.** The model must output calibrated probabilities, not arbitrary 0-1 floats. Calibration is measured empirically and reported in the eval dashboard.

4. **Closed-loop learning.** Every decision produces a measurable outcome. The system tracks what happened after each decision and uses that signal to improve.

5. **Person-specific adaptation.** Generic engagement rules are the baseline. Per-person behavioral models are the target. The system must improve its understanding of each human over time.

---

## 2. System Architecture

```
Message Arrives (Signal)
         │
         ▼
┌─────────────────────┐
│   SAFETY LAYER      │  <50ms, deterministic
│   (hard overrides)  │  Regex is acceptable HERE
└────────┬────────────┘
         │
         │ safety_override: null | {decision, reason}
         ▼
┌─────────────────────┐
│  CONTEXT ASSEMBLY   │  Neo4j queries, <50ms total
│  (token-budgeted)   │  Parallel fetches
└────────┬────────────┘
         │
         │ assembled_context: {...}
         ▼
┌─────────────────────┐
│  LLM ASSESSMENT     │  Single structured-output call
│  (engagement model) │  200-800ms depending on model
└────────┬────────────┘
         │
         │ EngagementDecision JSON
         ▼
┌─────────────────────┐
│  DECISION EXECUTOR  │  Routes to response pipeline or silence
│  (act on decision)  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  OUTCOME LOGGER     │  Records decision + what happened next
│  (learning signal)  │  Feeds back into eval and prompt tuning
└─────────────────────┘
```

**Critical property:** The Safety Layer and Context Assembly run in parallel. The safety layer takes <5ms. Context assembly takes <50ms. If the safety layer fires, the LLM call is skipped entirely. If not, context is already assembled by the time the LLM call starts.

---

## 3. Safety Layer (Pre-LLM)

The safety layer exists for ethical and latency reasons. These rules fire BEFORE the LLM and override its decision. This is the one place where pattern matching (including regex) is appropriate, because the rules are simple, deterministic, and safety-critical.

### 3.1 Override Rules

| Rule | Trigger | Override Decision | Rationale |
|------|---------|-------------------|-----------|
| **Distress** | Keywords: "help me", "emergency", "dying", "suicide", "hurt", "scared", "please help", "911", crisis hotline numbers | `respond`, `instant`, `full` | Ethical obligation. False positives are acceptable. |
| **First Contact** | No prior interaction history in Neo4j for this human_id | `respond`, `instant`, `full` | First impressions. Never ignore a new person. |
| **Re-engagement After Silence** | Last message from this human was >7 days ago | `respond`, `instant`, `full` | They came back. That signal is precious. |
| **Explicit Name Mention** | Message contains "Kublai" or configured aliases (case-insensitive) | `respond`, `natural`, depth deferred to LLM | Direct address implies expectation of response. |
| **Stop/Opt-out** | "stop", "unsubscribe", "leave me alone", "don't message me" | `respond`, `instant`, `acknowledgment` | Consent withdrawal. Acknowledge and comply. |
| **Media-only** | Message has attachments but no text body | `delay`, `natural`, depth deferred to LLM | Photos/files without text are ambiguous. Don't ignore, but don't rush. |

### 3.2 Implementation

```python
@dataclass
class SafetyOverride:
    decision: str          # "respond" | "delay" | "silent"
    timing: str            # "instant" | "natural"
    depth: str | None      # None means "defer to LLM"
    rule_name: str         # Which rule fired
    confidence: float      # Always 1.0 for safety overrides

DISTRESS_PATTERNS = re.compile(
    r'\b(help\s*me|emergency|dying|suicid|hurt\s*my|'
    r'scared|please\s+help|call\s*911|crisis)\b',
    re.IGNORECASE
)

STOP_PATTERNS = re.compile(
    r'^(stop|unsubscribe|leave\s+me\s+alone|don\'?t\s+message)\b',
    re.IGNORECASE
)

def check_safety_overrides(
    message_text: str,
    has_attachments: bool,
    human_id: str,
    interaction_count: int,
    last_interaction_ts: datetime | None,
) -> SafetyOverride | None:
    """Run safety checks. Returns override or None to proceed to LLM."""

    # 1. Distress — highest priority
    if message_text and DISTRESS_PATTERNS.search(message_text):
        return SafetyOverride("respond", "instant", "full", "distress", 1.0)

    # 2. Stop/opt-out
    if message_text and STOP_PATTERNS.match(message_text.strip()):
        return SafetyOverride("respond", "instant", "acknowledgment", "opt_out", 1.0)

    # 3. First contact
    if interaction_count == 0:
        return SafetyOverride("respond", "instant", "full", "first_contact", 1.0)

    # 4. Re-engagement after extended silence
    if last_interaction_ts:
        days_since = (datetime.now() - last_interaction_ts).days
        if days_since >= 7:
            return SafetyOverride("respond", "instant", "full", "re_engagement", 1.0)

    # 5. Explicit name mention
    if message_text and re.search(r'\bkublai\b', message_text, re.IGNORECASE):
        return SafetyOverride("respond", "natural", None, "name_mention", 1.0)

    # 6. Media-only (no text, has attachments)
    if not message_text and has_attachments:
        return SafetyOverride("delay", "natural", None, "media_only", 0.8)

    return None  # No safety override — proceed to LLM
```

### 3.3 Why Regex is Acceptable Here

These patterns match literal strings with known meanings. "Help me" means the same thing regardless of conversational context. The safety layer is not doing intent classification — it is doing keyword detection for a small set of high-stakes triggers where false positives (responding when you could have been silent) are cheap and false negatives (staying silent when someone needs help) are catastrophic.

---

## 4. Context Assembly

### 4.1 Token Budget

The assessment prompt has a **hard token budget of 2,000 tokens** for context (separate from the system prompt and few-shot examples). This forces prioritization.

### 4.2 Context Sources and Priority

All queries run against Neo4j in parallel. Results are assembled in priority order until the token budget is exhausted.

| Priority | Source | Neo4j Query | Token Budget | What It Provides |
|----------|--------|-------------|--------------|------------------|
| 1 (mandatory) | **Incoming message** | N/A | 200 tokens | The actual message text, truncated if needed |
| 2 (mandatory) | **Human profile** | `MATCH (hp:HumanProfile {human_id: $id})` | 300 tokens | Name, timezone, communication_style, decision_style, last_sentiment |
| 3 (mandatory) | **Thread context** | Last 5 messages in conversation | 500 tokens | Recent conversational flow |
| 4 (high) | **Active tasks** | `MATCH (t:Task {source_human: $id, status: 'WORKING'})` | 200 tokens | What Kublai is currently doing for this person |
| 5 (high) | **Pending items** | Action items awaiting response | 200 tokens | Unresolved commitments |
| 6 (medium) | **Temporal patterns** | Computed from interaction history | 150 tokens | Typical message times, response expectations |
| 7 (medium) | **Topic graph** | Top 3 topics by PageRank for this human | 150 tokens | What they care about |
| 8 (low) | **Upcoming events** | Next 24h events involving this human | 150 tokens | Calendar context |
| 9 (low) | **Relationship health** | Latest snapshot score | 50 tokens | Overall relationship trajectory |

### 4.3 Parallel Fetch Implementation

```python
import asyncio
from dataclasses import dataclass

@dataclass
class AssembledContext:
    message_text: str
    message_ts: datetime
    has_attachments: bool
    human_profile: dict | None        # From HumanProfile node
    thread_messages: list[dict]       # Last 5 messages
    active_tasks: list[dict]          # Tasks currently in progress
    pending_items: list[dict]         # Unresolved action items
    temporal_patterns: dict | None    # Message frequency, typical times
    top_topics: list[str]             # PageRank'd topic interests
    upcoming_events: list[dict]       # Next 24h calendar
    relationship_health: float | None # 0.0-1.0 score
    token_count: int                  # Actual tokens used

async def assemble_context(human_id: str, message_text: str,
                           message_ts: datetime, has_attachments: bool,
                           driver) -> AssembledContext:
    """Fetch all context in parallel, assemble within token budget."""

    # All fetches run concurrently
    profile_task = asyncio.create_task(fetch_human_profile(driver, human_id))
    thread_task = asyncio.create_task(fetch_thread_context(driver, human_id, limit=5))
    tasks_task = asyncio.create_task(fetch_active_tasks(driver, human_id))
    pending_task = asyncio.create_task(fetch_pending_items(driver, human_id))
    temporal_task = asyncio.create_task(fetch_temporal_patterns(driver, human_id))
    topics_task = asyncio.create_task(fetch_top_topics(driver, human_id, limit=3))
    events_task = asyncio.create_task(fetch_upcoming_events(driver, human_id, hours=24))
    health_task = asyncio.create_task(fetch_relationship_health(driver, human_id))

    results = await asyncio.gather(
        profile_task, thread_task, tasks_task, pending_task,
        temporal_task, topics_task, events_task, health_task,
        return_exceptions=True
    )

    # Unpack (replace exceptions with None/empty)
    def safe(result, default):
        return default if isinstance(result, Exception) else result

    return AssembledContext(
        message_text=message_text[:800],  # Hard truncate at ~200 tokens
        message_ts=message_ts,
        has_attachments=has_attachments,
        human_profile=safe(results[0], None),
        thread_messages=safe(results[1], []),
        active_tasks=safe(results[2], []),
        pending_items=safe(results[3], []),
        temporal_patterns=safe(results[4], None),
        top_topics=safe(results[5], []),
        upcoming_events=safe(results[6], []),
        relationship_health=safe(results[7], None),
        token_count=0,  # Computed after serialization
    )
```

### 4.4 Context Serialization

Context is serialized into a compact text block for the prompt. This is NOT free-form prose — it is structured text designed for LLM parsing efficiency.

```python
def serialize_context(ctx: AssembledContext) -> str:
    """Serialize context into token-budgeted text block."""
    sections = []

    # Human profile (always included if available)
    if ctx.human_profile:
        p = ctx.human_profile
        comm = p.get("communication_style", {})
        if isinstance(comm, str):
            import json
            comm = json.loads(comm)
        pc = p.get("personal_context", {})
        if isinstance(pc, str):
            pc = json.loads(pc)

        profile_lines = [
            f"[HUMAN] {p.get('display_name', 'Unknown')}",
            f"  timezone: {p.get('timezone', 'unknown')}",
            f"  style: {comm.get('response_style', 'unknown')}, "
            f"formality: {comm.get('formality', 'unknown')}, "
            f"detail: {comm.get('detail_level', 'unknown')}",
            f"  decision_style: {pc.get('decision_style', 'unknown')}",
            f"  last_sentiment: {pc.get('last_sentiment', 'unknown')}",
            f"  interaction_count: {pc.get('interaction_count', 0)}",
        ]
        sections.append("\n".join(profile_lines))

    # Thread context
    if ctx.thread_messages:
        thread_lines = ["[THREAD] Last messages:"]
        for msg in ctx.thread_messages[-5:]:
            role = msg.get("role", "?")
            text = msg.get("text", "")[:150]
            ts = msg.get("timestamp", "")
            thread_lines.append(f"  [{role} {ts}] {text}")
        sections.append("\n".join(thread_lines))

    # Active tasks
    if ctx.active_tasks:
        task_lines = ["[TASKS] Active:"]
        for t in ctx.active_tasks[:3]:
            task_lines.append(f"  - {t.get('title', '?')} ({t.get('status', '?')})")
        sections.append("\n".join(task_lines))

    # Pending items
    if ctx.pending_items:
        pending_lines = ["[PENDING] Awaiting response:"]
        for item in ctx.pending_items[:3]:
            pending_lines.append(f"  - {item.get('description', '?')}")
        sections.append("\n".join(pending_lines))

    # Temporal patterns
    if ctx.temporal_patterns:
        tp = ctx.temporal_patterns
        sections.append(
            f"[TEMPORAL] Typical active: {tp.get('active_hours', '?')}, "
            f"avg_response_expectation: {tp.get('expected_response_time', '?')}, "
            f"current_time_local: {tp.get('current_local_time', '?')}"
        )

    # Topics
    if ctx.top_topics:
        sections.append(f"[TOPICS] Interests: {', '.join(ctx.top_topics)}")

    # Upcoming events
    if ctx.upcoming_events:
        event_lines = ["[EVENTS] Next 24h:"]
        for e in ctx.upcoming_events[:2]:
            event_lines.append(f"  - {e.get('title', '?')} at {e.get('time', '?')}")
        sections.append("\n".join(event_lines))

    # Relationship health
    if ctx.relationship_health is not None:
        sections.append(f"[HEALTH] Relationship score: {ctx.relationship_health:.2f}")

    return "\n\n".join(sections)
```

---

## 5. Assessment Prompt

### 5.1 System Prompt

```
You are Kublai's engagement assessment module. Your job is to analyze an incoming
message from a human and decide: should Kublai respond, when, and how deeply?

You will receive the message and contextual information about the human. You must
return a structured JSON decision.

DECISION FRAMEWORK:

1. RESPOND when:
   - The human asks a question or makes a request
   - The human shares something that invites acknowledgment
   - There is an unresolved task or pending item relevant to the message
   - The conversational flow expects a response (they addressed Kublai)
   - The human's communication style suggests they want engagement

2. DELAY when:
   - The message is part of a multi-message burst (wait for them to finish)
   - The topic requires thoughtful response and urgency is low
   - The human typically messages in clusters (check temporal patterns)
   - It's outside the human's active hours and the message isn't urgent

3. SILENT when:
   - The message is clearly closing the conversation ("thanks", "got it", "bye")
   - The human is thinking aloud and doesn't want interruption
   - The message is a reaction or acknowledgment to Kublai's prior message
   - Responding would add no value (information already provided)

TIMING GUIDE:
   - instant (<5s): Urgent, emotional, time-sensitive, or human is clearly waiting
   - natural (10-45s): Standard conversational response time
   - considered (1-5min): Complex topic, needs thought, or human is in no rush
   - batched (next natural pause): Group with other pending items
   - scheduled (specific time): Defer to appropriate time (e.g., morning for non-urgent)

DEPTH GUIDE:
   - acknowledgment: "Got it" / "On it" — for tasks or simple confirmations
   - brief: 1-2 sentences — for simple questions, casual check-ins
   - full: Complete response — for questions, requests, complex topics
   - proactive: Full response + offer additional context or next steps

CALIBRATION:
   - Your confidence should reflect genuine uncertainty. 0.5 means you truly
     could go either way. 0.9+ means the decision is obvious from context.
   - When the person's communication style is well-documented, confidence
     should be higher. When they're new or unpredictable, lower.
   - If you're unsure between respond and silent, prefer respond with lower depth.

OUTPUT: Return ONLY valid JSON matching the schema. No explanation outside the JSON.
```

### 5.2 User Prompt Template

```
INCOMING MESSAGE:
  from: {human_name} ({human_id})
  time: {message_timestamp} ({human_local_time} their time)
  text: "{message_text}"
  attachments: {attachment_count} ({attachment_types})

CONTEXT:
{serialized_context}

Analyze this message and return your engagement decision as JSON.
```

### 5.3 Few-Shot Examples

Few-shot examples are the primary calibration mechanism. They encode the nuanced judgments that make the system feel intelligent. These examples are drawn from real interactions (anonymized) and are curated over time as the learning loop identifies correct and incorrect decisions.

**Initial calibration set (8 examples):**

```json
[
  {
    "_scenario": "Terse founder says 'k' mid-task",
    "input": {
      "message": "k",
      "context": "[HUMAN] Danny\n  style: direct, formality: casual, detail: brief\n  decision_style: decides fast\n  interaction_count: 847\n[THREAD] Last messages:\n  [kublai 14:02] I'll deploy the hotfix to staging first, then production after smoke tests.\n  [human 14:03] k\n[TASKS] Active:\n  - Deploy hotfix for auth timeout (WORKING)"
    },
    "output": {
      "decision": "silent",
      "confidence": 0.85,
      "timing": "natural",
      "depth": "acknowledgment",
      "reasoning": "Danny's 'k' is acknowledgment of the deployment plan. His direct/brief style means this is confirmation, not a question. Active task is already in progress.",
      "human_state": "engaged",
      "context_needed": ["none"]
    }
  },
  {
    "_scenario": "Verbose thinker sends paragraph of ideas",
    "input": {
      "message": "I've been thinking about the recommendation engine. What if instead of collaborative filtering we tried a graph-based approach? Like, use the social connections to propagate preferences. Not sure if that's too computationally expensive though. Also wondering about cold-start — how do we handle new users with no connections?",
      "context": "[HUMAN] Sarah\n  style: exploratory, formality: casual, detail: detailed\n  decision_style: wants options\n  interaction_count: 234\n[THREAD] Last messages:\n  [human 10:15] good morning!\n  [kublai 10:16] Good morning Sarah! How's the research going?\n  [human 10:20] (the message above)"
    },
    "output": {
      "decision": "respond",
      "confidence": 0.90,
      "timing": "considered",
      "depth": "full",
      "reasoning": "Sarah is brainstorming and has asked two specific questions (computational cost, cold-start). Her 'wants options' style means she wants substantive input, not just acknowledgment. Considered timing because this deserves a thoughtful response.",
      "human_state": "engaged",
      "context_needed": ["topic_history"]
    }
  },
  {
    "_scenario": "Late night casual message",
    "input": {
      "message": "just saw the funniest error message in prod: 'error: success'",
      "context": "[HUMAN] Alex\n  timezone: America/Los_Angeles\n  style: balanced, formality: casual, detail: moderate\n  interaction_count: 56\n[TEMPORAL] Typical active: 09:00-18:00 PST, current_time_local: 23:45 PST\n[THREAD] Last messages:\n  [human 23:45] (the message above)"
    },
    "output": {
      "decision": "respond",
      "confidence": 0.75,
      "timing": "natural",
      "depth": "brief",
      "reasoning": "Alex is sharing something amusing late at night — casual social bonding. A brief, warm response maintains the relationship. Lower confidence because late-night messages are sometimes just venting with no response expected.",
      "human_state": "casual",
      "context_needed": ["none"]
    }
  },
  {
    "_scenario": "Human sends 'thanks!' after task completion",
    "input": {
      "message": "thanks!",
      "context": "[HUMAN] Maria\n  style: balanced, formality: casual, detail: moderate\n  interaction_count: 312\n[THREAD] Last messages:\n  [human 15:00] can you check if the API rate limits are configured right?\n  [kublai 15:12] Checked — the rate limits are set to 100 req/min per key, which matches the spec. The Redis counter TTL is 60s. All looks correct.\n  [human 15:13] thanks!"
    },
    "output": {
      "decision": "silent",
      "confidence": 0.90,
      "timing": "natural",
      "depth": "acknowledgment",
      "reasoning": "Maria's 'thanks!' is a conversation closer. The task was completed, the answer was given, she acknowledged it. Responding would restart a closed conversation.",
      "human_state": "closing",
      "context_needed": ["none"]
    }
  },
  {
    "_scenario": "Urgent request with emotional cues",
    "input": {
      "message": "the site is down and we have a demo in 30 minutes. can you check what happened??",
      "context": "[HUMAN] Danny\n  style: direct, formality: casual, detail: brief\n  interaction_count: 847\n[THREAD] Last messages:\n  [human 09:28] (the message above)\n[TASKS] Active:\n  - Weekly analytics report (WORKING)\n[EVENTS] Next 24h:\n  - Investor demo at 10:00"
    },
    "output": {
      "decision": "respond",
      "confidence": 0.99,
      "timing": "instant",
      "depth": "proactive",
      "reasoning": "Site down + imminent demo = urgent. Double question marks indicate stress. Proactive depth because Danny needs not just acknowledgment but immediate triage action.",
      "human_state": "urgent",
      "context_needed": ["active_tasks"]
    }
  },
  {
    "_scenario": "Multi-message burst, should wait for completion",
    "input": {
      "message": "oh and one more thing",
      "context": "[HUMAN] Jake\n  style: exploratory, formality: casual, detail: detailed\n  interaction_count: 89\n[THREAD] Last messages:\n  [human 11:00] hey I had a few thoughts about the project\n  [human 11:00] first, I think we should reconsider the database choice\n  [human 11:01] postgres might be better than mongo for this\n  [human 11:01] oh and one more thing"
    },
    "output": {
      "decision": "delay",
      "confidence": 0.92,
      "timing": "natural",
      "depth": "full",
      "reasoning": "Jake is in a multi-message burst ('oh and one more thing' signals more coming). Wait for the burst to complete before responding to avoid interrupting his train of thought.",
      "human_state": "engaged",
      "context_needed": ["topic_history"]
    }
  },
  {
    "_scenario": "Forwarded article with no comment",
    "input": {
      "message": "",
      "context": "[HUMAN] Priya\n  style: balanced, formality: professional, detail: moderate\n  interaction_count: 145\n  attachments: 1 (link preview: 'The Future of AI Agents — TechCrunch')\n[TOPICS] Interests: AI agents, product strategy, market research"
    },
    "output": {
      "decision": "respond",
      "confidence": 0.70,
      "timing": "considered",
      "depth": "brief",
      "reasoning": "Priya shared an article relevant to her interests without comment. This likely means 'what do you think?' or 'FYI'. A brief acknowledgment with a relevant thought shows engagement without overstepping. Lower confidence because some people share links as bookmarks.",
      "human_state": "casual",
      "context_needed": ["topic_history"]
    }
  },
  {
    "_scenario": "Weekend check-in from someone who rarely messages on weekends",
    "input": {
      "message": "hey, you around?",
      "context": "[HUMAN] Danny\n  style: direct, formality: casual, detail: brief\n  interaction_count: 847\n[TEMPORAL] Typical active: Mon-Fri 08:00-22:00 EST, current_time_local: Saturday 14:00 EST\n  weekend_message_frequency: rare (2/month average)\n[THREAD] Last messages:\n  [kublai Friday 17:30] Have a good weekend!\n  [human Saturday 14:00] hey, you around?"
    },
    "output": {
      "decision": "respond",
      "confidence": 0.95,
      "timing": "instant",
      "depth": "brief",
      "reasoning": "Danny rarely messages on weekends. 'Hey, you around?' from someone with a direct style who almost never reaches out on weekends signals something specific. Instant response to show availability, brief depth until the actual ask is clear.",
      "human_state": "engaged",
      "context_needed": ["active_tasks", "none"]
    }
  }
]
```

### 5.4 Few-Shot Example Management

Examples are stored in a JSONL file (`~/.openclaw/data/engagement_few_shots.jsonl`), not hard-coded. This enables:

- **A/B testing** of example sets
- **Automated curation** from the learning loop (promote high-quality outcomes to few-shot examples)
- **Per-person overrides** (if a human consistently produces decisions that don't match any example, add a personalized example)
- **Version tracking** (each example set has a version; eval scores are tracked per version)

---

## 6. Output Schema

### 6.1 Primary Decision Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["decision", "confidence", "timing", "depth", "reasoning", "human_state"],
  "properties": {
    "decision": {
      "type": "string",
      "enum": ["respond", "delay", "silent"]
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Calibrated probability that this is the correct decision. 0.5 = genuine coin flip. 0.9+ = obvious."
    },
    "timing": {
      "type": "string",
      "enum": ["instant", "natural", "considered", "batched", "scheduled"],
      "description": "instant: <5s. natural: 10-45s. considered: 1-5min. batched: next natural pause. scheduled: specific future time."
    },
    "depth": {
      "type": "string",
      "enum": ["acknowledgment", "brief", "full", "proactive"]
    },
    "reasoning": {
      "type": "string",
      "maxLength": 200,
      "description": "One sentence explaining the key signal that drove the decision."
    },
    "human_state": {
      "type": "string",
      "enum": ["engaged", "casual", "urgent", "emotional", "closing", "thinking_aloud", "multi_message"],
      "description": "Inferred conversational state of the human."
    },
    "context_needed": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["topic_history", "active_tasks", "pending_items", "calendar", "relationship_history", "none"]
      },
      "description": "What additional context the response generator should fetch before composing a reply."
    },
    "schedule_for": {
      "type": "string",
      "format": "date-time",
      "description": "Only present when timing='scheduled'. ISO 8601 timestamp for when to respond."
    },
    "batch_with": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Only present when timing='batched'. IDs of other pending messages to batch together."
    }
  },
  "additionalProperties": false
}
```

### 6.2 Logged Decision Record

Every decision is persisted for the learning loop. The logged record extends the model output with metadata:

```json
{
  "decision_id": "eng-uuid4",
  "timestamp": "2026-03-19T14:32:00Z",
  "human_id": "+19194133445",
  "message_hash": "sha256_first_8",
  "message_length": 42,

  "safety_override": null,

  "model_output": {
    "decision": "respond",
    "confidence": 0.85,
    "timing": "natural",
    "depth": "full",
    "reasoning": "...",
    "human_state": "engaged",
    "context_needed": ["active_tasks"]
  },

  "model_id": "deepseek/deepseek-chat",
  "latency_ms": 340,
  "context_tokens": 1450,
  "few_shot_version": "v3",

  "outcome": {
    "response_sent": true,
    "response_latency_ms": 2400,
    "human_replied": true,
    "human_reply_latency_s": 45,
    "human_reply_sentiment": "positive",
    "conversation_continued": true,
    "explicit_feedback": null
  }
}
```

---

## 7. Model Selection

### 7.1 Primary Assessment Model

**Recommendation: DeepSeek Chat (deepseek/deepseek-chat via OpenRouter)**

| Criterion | DeepSeek Chat | Claude Haiku | GPT-4o-mini |
|-----------|--------------|--------------|-------------|
| **Cost per 1K input tokens** | $0.00014 | $0.00025 | $0.00015 |
| **Cost per 1K output tokens** | $0.00028 | $0.00125 | $0.0006 |
| **Latency (p50)** | ~300ms | ~400ms | ~350ms |
| **Structured output quality** | Excellent | Excellent | Good |
| **JSON schema adherence** | Strong | Strong | Moderate |
| **Reasoning quality** | Strong for classification | Excellent | Good |
| **Already in stack** | Yes (OpenRouter) | Yes (Anthropic) | No |

**Rationale:**
- DeepSeek Chat is already the default model in Parse for Agents and is familiar infrastructure.
- At $0.00014/1K input tokens, a 3K-token prompt costs ~$0.00042 per decision. This is negligible.
- Its structured output quality is strong enough for a classification task with well-defined schema.
- 300ms median latency keeps total pipeline under 500ms.
- It is NOT the same model that generates responses (Kublai uses Claude Opus for response generation). This is intentional: the classifier should be cheap and fast; the responder should be powerful and thorough.

### 7.2 Fallback Chain

```
Primary:  deepseek/deepseek-chat (via OpenRouter)     ~300ms, ~$0.0005/decision
    │
    ▼ (if OpenRouter 5xx or timeout >2s)
Fallback 1: qwen3.5:9b (local Ollama)                 ~200ms, $0/decision
    │
    ▼ (if Ollama unavailable)
Fallback 2: Rule-based heuristic                       ~1ms, $0/decision
```

**Fallback 2 (rule-based)** is NOT the old regex system. It is a simple decision tree:

```python
def heuristic_fallback(message_text: str, thread_len: int,
                       interaction_count: int) -> dict:
    """Emergency fallback when all models are unavailable."""
    # Default: respond to everything with natural timing
    # This is deliberately conservative (over-respond rather than miss)
    decision = {
        "decision": "respond",
        "confidence": 0.50,  # Explicitly low — we're guessing
        "timing": "natural",
        "depth": "brief",
        "reasoning": "Heuristic fallback — model unavailable",
        "human_state": "engaged",
        "context_needed": ["none"],
    }

    # Only go silent for very short messages in long threads
    if len(message_text or "") <= 5 and thread_len > 4:
        last_speaker = "unknown"  # Would need thread context
        decision["decision"] = "delay"
        decision["timing"] = "considered"
        decision["reasoning"] = "Heuristic: short message in long thread, delaying"

    return decision
```

### 7.3 Why NOT Use the Response Model for Assessment?

Claude Opus costs ~$0.015/1K input tokens — roughly 100x more than DeepSeek Chat. For a classification task with structured output, the quality difference does not justify the cost. The assessment is a focused, bounded decision with clear criteria. It does not require the creative reasoning or long-context understanding that justifies Opus for response generation.

If eval data later shows that DeepSeek's accuracy on engagement decisions is meaningfully worse than Claude's, the model can be upgraded. The system is model-agnostic by design.

---

## 8. Learning Loop

This is the section where the old system most critically failed. It had no mechanism for measuring whether its decisions were correct, let alone improving from that measurement. The design below meets the standard of a frontier lab's eval framework.

### 8.1 Ground Truth Collection

**The core problem:** Engagement decisions don't have obvious labels. If Kublai responds and the human replies, was that because the response was welcome, or because the human felt obligated? If Kublai stays silent and the human doesn't follow up, was that correct silence or a missed connection?

**Three ground truth sources, in order of reliability:**

#### Source 1: Explicit Feedback (Highest Signal, Lowest Volume)

The human can explicitly tell Kublai about engagement preferences:
- "You don't need to reply to everything"
- "Hey, I was waiting for your response"
- "Thanks for the quick reply on that"

These are captured by a lightweight intent classifier (can be the same LLM assessment module with a different prompt) and logged as explicit ground truth.

**Expected volume:** ~2-5 feedback signals per human per month. Low volume but gold-standard.

**Label extraction prompt** (runs on every human message, piggybacks on the assessment call):
```
Does this message contain feedback about Kublai's engagement behavior
(response timing, whether to respond, response depth)? If yes, extract it.

Return: {"has_feedback": true/false, "feedback_type": "too_slow|too_fast|unwanted_response|missed_response|good_timing|too_brief|too_verbose|null", "quote": "relevant substring"}
```

This is a secondary output from the assessment LLM call (added to the schema as an optional `meta` field), so it costs nothing extra.

#### Source 2: Behavioral Proxy Labels (Medium Signal, High Volume)

For every decision, record what happened next and derive a proxy label:

| Decision | Outcome | Proxy Label | Confidence |
|----------|---------|-------------|------------|
| respond | Human replied within 5min | Correct | 0.7 |
| respond | Human replied with positive sentiment | Correct | 0.8 |
| respond | Human did not reply within 24h | Possibly incorrect | 0.4 |
| respond | Human said "ok" or single word | Ambiguous | 0.3 |
| silent | Human sent follow-up within 10min | Possibly incorrect | 0.5 |
| silent | No follow-up for 24h+ | Correct | 0.6 |
| silent | Human explicitly re-asked | Incorrect | 0.9 |
| delay | Human sent more messages (burst completed) | Correct | 0.8 |
| delay | Human said "hello?" or "you there?" | Incorrect | 0.9 |

**Proxy label confidence reflects the ambiguity.** A human not replying after a response could mean many things. A human saying "you there?" after a delay unambiguously means the delay was wrong.

#### Source 3: Periodic Human Review (Highest Signal for Edge Cases)

Once per week, surface 10 decisions with the lowest proxy-label confidence to a human reviewer (the Kurultai operator). Present them as:

```
Message: "k"
Context: [brief thread summary]
Decision: silent (confidence 0.85)
Outcome: No follow-up for 2 hours
Proxy label: Correct (confidence 0.6)

Was this the right call? [Yes] [No] [Depends]
```

This creates ~40 expert labels per month — enough to track calibration drift and catch systematic errors.

### 8.2 Accuracy Measurement

**Metrics tracked per decision class:**

| Metric | Definition | Target |
|--------|-----------|--------|
| **Precision (respond)** | Of times we responded, how often was it welcome? | >0.85 |
| **Recall (respond)** | Of times a response was needed, how often did we respond? | >0.90 |
| **Precision (silent)** | Of times we stayed silent, how often was that correct? | >0.80 |
| **Recall (silent)** | Of times silence was appropriate, how often were we silent? | >0.75 |
| **Timing accuracy** | When we responded, was the timing appropriate? | >0.80 |
| **Depth accuracy** | When we responded, was the depth appropriate? | >0.75 |
| **Calibration error** | ECE (Expected Calibration Error) across confidence bins | <0.10 |
| **Per-person accuracy** | Same metrics, per human_id | Tracked, no target |

**Calibration measurement:**

Partition decisions into confidence bins (0.5-0.6, 0.6-0.7, ..., 0.9-1.0). Within each bin, the fraction of correct decisions should match the average confidence. Plot this as a reliability diagram.

```python
def compute_calibration_error(decisions: list[dict]) -> float:
    """Expected Calibration Error over confidence bins."""
    bins = defaultdict(list)
    for d in decisions:
        conf = d["model_output"]["confidence"]
        correct = d["outcome"]["proxy_label"] == "correct"
        bin_idx = min(int(conf * 10), 9)  # 0-9 bins
        bins[bin_idx].append((conf, correct))

    ece = 0.0
    total = len(decisions)
    for bin_idx, items in bins.items():
        if not items:
            continue
        avg_conf = sum(c for c, _ in items) / len(items)
        avg_acc = sum(1 for _, c in items if c) / len(items)
        ece += (len(items) / total) * abs(avg_conf - avg_acc)

    return ece
```

**Minimum sample sizes for meaningful measurement:**

| Metric | Minimum N | Rationale |
|--------|----------|-----------|
| Per-class precision/recall | 50 decisions per class | Binomial proportion CI width <0.15 at 95% |
| Calibration error (ECE) | 200 total decisions | Need ~20 per bin for stable estimates |
| Per-person accuracy | 30 decisions per person | Enough to detect >20% deviation from population |
| A/B test (prompt change) | 100 per variant | Power 0.8 to detect 10% accuracy difference |

### 8.3 Improvement Mechanisms

#### Mechanism 1: Few-Shot Example Curation (Primary, No Training Required)

The learning loop identifies high-signal decisions and promotes them to few-shot examples:

1. **Candidate identification:** Decisions where the proxy label has high confidence (>0.8) AND the scenario is underrepresented in the current example set.
2. **Diversity filter:** New examples must cover a different (human_state, decision, depth) triple than existing examples.
3. **Human approval:** Candidate examples are shown to the operator for approval before promotion.
4. **Example budget:** Maximum 12 few-shot examples (more degrades performance by consuming context).
5. **Retirement:** Examples that no longer improve accuracy (measured by ablation) are retired.

This is the primary improvement mechanism. It requires no fine-tuning, no gradient updates, and no training infrastructure. It works because the few-shot examples are the primary calibration mechanism for the LLM.

#### Mechanism 2: Per-Person Behavioral Priors (Learned from History)

After 30+ interactions with a human, the system computes per-person behavioral priors and injects them into the context:

```python
def compute_person_priors(human_id: str, decisions: list[dict]) -> dict:
    """Compute behavioral priors from decision history."""
    # Filter to decisions for this human with confident proxy labels
    person_decisions = [
        d for d in decisions
        if d["human_id"] == human_id
        and d["outcome"].get("proxy_label_confidence", 0) > 0.6
    ]

    if len(person_decisions) < 30:
        return {}  # Not enough data

    # Compute response expectation rate
    messages_that_expected_response = sum(
        1 for d in person_decisions
        if d["outcome"].get("proxy_label") == "correct"
        and d["model_output"]["decision"] == "respond"
    )
    response_rate = messages_that_expected_response / len(person_decisions)

    # Average preferred depth
    depth_counts = Counter(
        d["model_output"]["depth"]
        for d in person_decisions
        if d["outcome"].get("proxy_label") == "correct"
    )

    # Typical timing preference
    timing_counts = Counter(
        d["model_output"]["timing"]
        for d in person_decisions
        if d["outcome"].get("proxy_label") == "correct"
    )

    return {
        "response_expectation_rate": round(response_rate, 2),
        "preferred_depth": depth_counts.most_common(1)[0][0] if depth_counts else None,
        "preferred_timing": timing_counts.most_common(1)[0][0] if timing_counts else None,
        "sample_size": len(person_decisions),
    }
```

These priors are injected as an additional context block:

```
[PERSON_PRIORS] Based on 145 interactions:
  response_expectation: 0.72 (responds to ~72% of messages)
  preferred_depth: brief
  preferred_timing: natural
```

#### Mechanism 3: Prompt Tuning (Quarterly, if Needed)

If few-shot curation plateaus and accuracy is below target:

1. Collect 500+ labeled decisions (mix of proxy labels and human labels).
2. Use DSPy or similar prompt optimization framework to search over system prompt variations.
3. Evaluate candidate prompts on a held-out test set of 100 labeled decisions.
4. Deploy the winning prompt with A/B measurement for 1 week before full rollout.

This is expensive and infrequent. It is the nuclear option when simpler mechanisms fail.

#### Mechanism 4: Fine-Tuning (Not Recommended Initially)

Fine-tuning is mentioned for completeness. It would require:
- 1,000+ high-quality labeled examples
- A model that supports fine-tuning (DeepSeek does, via their API)
- Infrastructure for training, evaluation, and deployment

**Not recommended until the system has been running for 3+ months and has accumulated sufficient labeled data.** The few-shot + behavioral priors approach should be sufficient for the first phase.

### 8.4 Cold-Start Handling

For new humans (interaction_count = 0-29):

1. **Safety layer handles first contact** (guaranteed response).
2. **Population priors** are used instead of per-person priors. The system prompt includes:
   ```
   [PERSON_PRIORS] New contact — using population defaults:
     response_expectation: 0.80 (err toward responding)
     preferred_depth: full (new contacts deserve thorough responses)
     preferred_timing: natural
   ```
3. **Confidence is artificially lowered** by a cold-start penalty:
   ```python
   if interaction_count < 30:
       cold_start_factor = 0.7 + (0.3 * interaction_count / 30)
       output["confidence"] *= cold_start_factor
   ```
   This ensures that for new humans, decisions are logged with appropriately low confidence, triggering more frequent human review.

4. **Communication style inference** begins immediately. After 5 messages, the system computes:
   - Average message length (proxy for verbosity)
   - Average response latency (proxy for urgency expectations)
   - Emoji usage (proxy for formality)

   These are stored in `HumanProfile.communication_style` and updated incrementally.

---

## 9. Cost Analysis

### 9.1 Per-Decision Cost

**Prompt composition:**
- System prompt: ~800 tokens
- Few-shot examples (8): ~1,600 tokens
- Context block: ~600 tokens (avg)
- User message: ~200 tokens (avg)
- **Total input: ~3,200 tokens**
- **Output: ~150 tokens** (structured JSON)

| Model | Input Cost | Output Cost | Total per Decision |
|-------|-----------|-------------|-------------------|
| DeepSeek Chat | $0.000448 | $0.000042 | **$0.00049** |
| Claude Haiku | $0.000800 | $0.000188 | **$0.00099** |
| GPT-4o-mini | $0.000480 | $0.000090 | **$0.00057** |
| Qwen 3.5 (local) | $0 | $0 | **$0** |

### 9.2 Daily/Monthly at 200 Decisions/Day

| Model | Daily Cost | Monthly Cost (30d) |
|-------|-----------|-------------------|
| DeepSeek Chat | $0.098 | **$2.94** |
| Claude Haiku | $0.198 | **$5.94** |
| GPT-4o-mini | $0.114 | **$3.42** |
| Local Ollama | $0 | **$0** (electricity only) |

At 200 decisions/day with DeepSeek Chat, the engagement assessment system costs **under $3/month**. This is negligible compared to the response generation costs (Claude Opus for actual responses).

### 9.3 Cost Optimization Strategies

1. **Response caching:** If the same human sends the same short message ("ok", "thanks", "k") with similar context, cache the decision for 5 minutes. Expected hit rate: ~15% (reduces cost by ~$0.44/month — not worth the complexity).

2. **Model routing:** Use local Ollama (free) for "easy" decisions (closing messages, simple acknowledgments) and DeepSeek for ambiguous ones. Requires a lightweight pre-classifier, which adds complexity for minimal savings. **Not recommended at current volumes.**

3. **Batch assessment:** For burst messages (3+ messages in 30 seconds), assess them as a group instead of individually. Saves 2-3x on burst sequences. **Recommended — aligns with the "delay for multi-message burst" behavior.**

4. **Few-shot pruning:** Reduce from 8 to 4 few-shot examples for messages from humans with 100+ interactions (their behavioral priors contain more signal than generic examples). Saves ~800 input tokens per call. **Recommended.**

### 9.4 Cost Summary

| Scenario | Monthly Cost |
|----------|-------------|
| 200 decisions/day, DeepSeek, no optimization | $2.94 |
| 200 decisions/day, DeepSeek, with batch + prune | ~$2.20 |
| 500 decisions/day, DeepSeek, with batch + prune | ~$5.50 |
| 200 decisions/day, local Ollama only | $0 |

**Verdict:** Cost is not a constraint for this system. Optimize for accuracy, not cost.

---

## 10. The Superintelligent Being Factor

This is what separates a good engagement system from a system that makes humans feel understood. The technical mechanisms are:

### 10.1 Communication Style as a Learned Model

The `communication_style` field in HumanProfile is not a static config — it is a living model that evolves with every interaction.

**Current schema (from neo4j_human_profile.py):**
```python
DEFAULT_COMMUNICATION_STYLE = {
    "preferred_channel": "signal",
    "preferred_time": "anytime",
    "response_style": "balanced",
    "emoji_friendly": True,
    "detail_level": "moderate",
    "formality": "casual",
    "messaging_frequency": "normal",
    "quiet_hours": None,
    "topics_of_interest": [],
    "topics_to_avoid": [],
}
```

**Extended for engagement assessment:**
```python
EXTENDED_COMMUNICATION_STYLE = {
    # Existing fields...

    # New fields for engagement assessment
    "message_brevity": "unknown",       # "terse" | "moderate" | "verbose"
    "burst_pattern": "unknown",         # "single" | "occasional_burst" | "frequent_burst"
    "closing_signals": [],              # Learned phrases that mean "conversation over"
    "continuation_signals": [],         # Learned phrases that mean "I expect a reply"
    "thinking_aloud_frequency": 0.0,    # 0.0-1.0, how often they send messages not expecting replies
    "weekend_engagement": "unknown",    # "same" | "reduced" | "rare"
    "evening_engagement": "unknown",    # "same" | "reduced" | "rare"
    "urgency_markers": [],              # Learned patterns that signal urgency for THIS person
}
```

These fields are updated after every interaction by a lightweight post-decision analysis:

```python
def update_communication_model(human_id: str, message: str,
                                decision: dict, outcome: dict):
    """Update the human's communication style model based on this interaction."""
    profile_store = HumanProfileStore()
    style = profile_store.get_communication_style(human_id) or {}

    # Update brevity estimate (exponential moving average)
    msg_len = len(message)
    current_brevity = style.get("_avg_message_length", msg_len)
    style["_avg_message_length"] = 0.9 * current_brevity + 0.1 * msg_len
    if style["_avg_message_length"] < 20:
        style["message_brevity"] = "terse"
    elif style["_avg_message_length"] < 100:
        style["message_brevity"] = "moderate"
    else:
        style["message_brevity"] = "verbose"

    # Update closing signal detection
    if outcome.get("conversation_continued") is False and decision["decision"] == "silent":
        # This message was correctly identified as a closing signal
        normalized = message.strip().lower()
        if normalized not in style.get("closing_signals", []):
            style.setdefault("closing_signals", []).append(normalized)
            # Keep only last 10
            style["closing_signals"] = style["closing_signals"][-10:]

    # Update temporal patterns
    hour = datetime.now().hour
    day = datetime.now().weekday()
    if day >= 5:  # Weekend
        style.setdefault("_weekend_messages", 0)
        style["_weekend_messages"] += 1
        total = style.get("_total_messages", 1)
        weekend_rate = style["_weekend_messages"] / total
        style["weekend_engagement"] = (
            "rare" if weekend_rate < 0.05
            else "reduced" if weekend_rate < 0.15
            else "same"
        )

    profile_store.update_field(human_id, "communication_style", style)
```

### 10.2 Why This Matters

When the system has learned that Danny is terse, messages on weekends are rare and significant, and his closing signal is just going silent (no "thanks" or "bye") — the engagement decisions become uncanny:

- Danny sends "k" on a Tuesday during work hours after a status update. The system knows this is his acknowledgment pattern. **Silent.** Correct.
- Danny sends "k" on a Saturday. The system knows weekends are rare. This isn't acknowledgment — this is a compressed "okay, I see this, let me think." **Delay, then respond if he follows up.** Correct.
- Danny goes silent after a complex discussion. Another human's silence might mean "I'm done." Danny's silence means "I'm processing." The system has learned his closing_signals list is empty — he never says goodbye. **Wait longer before concluding the conversation is over.** Correct.

### 10.3 Topic-Aware Engagement

The Topic graph (PageRank'd) modulates depth, not just decision:

- If the human's message touches their #1 topic of interest, increase depth by one level (brief -> full, full -> proactive).
- If the message is about something the system has never discussed with this human, increase confidence in responding (they're exploring something new — show interest).
- If the message is about a topic_to_avoid, be more cautious (acknowledge but don't elaborate).

This is encoded in the context assembly, not in the prompt. The LLM sees:

```
[TOPICS] Interests: AI agents (rank 1), product strategy (rank 2), market research (rank 3)
  Message topic match: AI agents (rank 1, strong match)
```

And the few-shot examples teach the model that high-rank topic matches warrant deeper engagement.

### 10.4 Relationship Trajectory

The relationship health score (already in Neo4j) is a trailing indicator. But the engagement system can compute a leading indicator: **engagement momentum**.

```python
def compute_engagement_momentum(human_id: str, window_days: int = 14) -> float:
    """Compute the rate of change in engagement frequency.

    Returns:
        Positive = increasing engagement, negative = declining.
        Normalized to [-1.0, 1.0].
    """
    # Compare message frequency in last 7 days vs previous 7 days
    recent = count_messages(human_id, days=window_days // 2)
    previous = count_messages(human_id, start_days_ago=window_days,
                              end_days_ago=window_days // 2)

    if previous == 0:
        return 1.0 if recent > 0 else 0.0

    ratio = recent / previous
    # Normalize: ratio of 2.0 = momentum +0.5, ratio of 0.5 = momentum -0.5
    momentum = max(-1.0, min(1.0, (ratio - 1.0)))
    return round(momentum, 2)
```

This is injected into context:

```
[HEALTH] Relationship score: 0.82, momentum: +0.15 (increasing engagement)
```

When momentum is declining, the system subtly shifts toward more responsive behavior — respond more, delay less, be proactive. When momentum is increasing, the system can relax slightly — the relationship is healthy.

---

## 11. Implementation Plan

### Phase 1: Core Pipeline (Week 1)

1. Implement `safety_layer.py` with the override rules from Section 3.
2. Implement `context_assembler.py` with parallel Neo4j fetches from Section 4.
3. Implement `engagement_assessor.py` with the prompt from Section 5 and DeepSeek Chat.
4. Implement `decision_logger.py` to persist every decision (Section 6.2).
5. Write the initial 8 few-shot examples to `engagement_few_shots.jsonl`.
6. Integration test: pipe real Signal messages through the pipeline, verify JSON output.

### Phase 2: Learning Infrastructure (Week 2)

7. Implement `outcome_tracker.py` — hooks into Signal message handler to record what happened after each decision.
8. Implement proxy label computation from Section 8.1.
9. Build eval dashboard (or add to Kurultai dashboard): precision/recall per class, calibration diagram.
10. Implement the explicit feedback extractor (piggybacks on assessment LLM call).

### Phase 3: Person-Specific Adaptation (Week 3-4)

11. Extend `communication_style` schema with the new fields from Section 10.1.
12. Implement `update_communication_model()` post-decision hook.
13. Implement `compute_person_priors()` and inject into context assembly.
14. Implement `compute_engagement_momentum()`.
15. Wire everything into the live Signal message pipeline.

### Phase 4: Measurement and Tuning (Ongoing)

16. After 200 decisions: compute first calibration error, adjust few-shot examples.
17. After 500 decisions: compute per-class precision/recall, identify systematic errors.
18. After 30+ decisions per person: activate per-person priors for those humans.
19. Weekly: surface 10 low-confidence decisions for human review.
20. Monthly: review accuracy trends, consider prompt tuning if below targets.

---

## Appendix A: Integration Points

| Component | File | Integration |
|-----------|------|-------------|
| Signal message ingestion | `signal_jsonrpc_server.py` | Call `assess_engagement()` on each incoming message |
| Human profile | `neo4j_human_profile.py` | Context assembly fetches profile |
| Task tracker | `neo4j_v2_executor.py` | Context assembly fetches active tasks |
| Task intake | `task_intake.py` | If decision is "respond", create response task |
| Agent task handler | `agent-task-handler.py` | Response generation uses `context_needed` to fetch additional context |
| Learning loop | New: `engagement_outcome_tracker.py` | Hooks into Signal handler to track outcomes |
| Eval dashboard | Kurultai dashboard (`the.kurult.ai`) | New tab for engagement metrics |

## Appendix B: What Changed from the Old System

| Aspect | Old (Regex) | New (LLM) |
|--------|-------------|-----------|
| Intent classification | Regex patterns with hand-tuned weights | LLM with structured output |
| Confidence | Arbitrary 0-1 float from weighted sum | Calibrated probability from LLM, measured via ECE |
| Context | None (message text only) | Full human profile, thread, tasks, temporal patterns |
| Per-person adaptation | None | Learned communication style model + behavioral priors |
| Evaluation | None | Proxy labels + explicit feedback + periodic human review |
| Improvement | Manual regex editing | Few-shot curation from learning loop |
| Cost | $0 (regex) | ~$3/month (DeepSeek Chat, 200 decisions/day) |
| Latency | <1ms | <500ms (safety layer + context assembly + LLM call) |
| Accuracy | Unknown (never measured) | Measured: precision, recall, ECE per class |

## Appendix C: Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| DeepSeek quality insufficient for nuanced decisions | Medium | High | Fallback chain (Section 7.2), prompt tuning (Section 8.3), model upgrade path |
| Cold-start over-responding annoys new humans | Low | Medium | Brief depth default, confidence penalty, explicit opt-out detection |
| Learning loop proxy labels are systematically biased | Medium | Medium | Human review catches systematic errors, explicit feedback overrides proxies |
| Neo4j context queries exceed 50ms budget | Low | Low | Queries are indexed, parallel fetched, and individually timeout at 30ms |
| LLM hallucination in structured output (invalid JSON, wrong enum) | Low | Low | Schema validation with retry (1 retry), fallback to heuristic |
