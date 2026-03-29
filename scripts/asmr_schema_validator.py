#!/usr/bin/env python3
"""
asmr_schema_validator.py — Validate 6-vector extraction output before Neo4j MERGE.

Prevents hallucinated facts from landing in the knowledge graph. Drops invalid
entries, normalizes keys to lowercase, and enforces closed enums for all vectors.

Usage:
    from asmr_schema_validator import validate_extraction
    cleaned, warnings = validate_extraction(llm_output_dict)
"""

# ---------------------------------------------------------------------------
# Closed enum sets — single source of truth for all valid values
# ---------------------------------------------------------------------------

VALID_PERSONAL_KEYS = frozenset({
    'name', 'email', 'phone', 'role', 'company', 'location',
    'relationship', 'age', 'birthday', 'timezone', 'language', 'other'
})

VALID_PREFERENCE_DOMAINS = frozenset({
    'communication', 'schedule', 'format', 'content', 'tool', 'social'
})

VALID_EVENT_TYPES = frozenset({
    'MEETING', 'APPOINTMENT', 'DEADLINE', 'REMINDER', 'ANNIVERSARY'
})

VALID_VALENCES = frozenset({'LIKE', 'DISLIKE', 'NEUTRAL'})

VALID_GOAL_STATUSES = frozenset({'active', 'completed', 'abandoned'})
VALID_GOAL_DOMAINS = frozenset({'product', 'engineering', 'hiring', 'business', 'personal'})
VALID_GOAL_PRIORITIES = frozenset({'high', 'medium', 'low'})

VALID_RELATIONSHIP_NATURES = frozenset({
    'reports-to', 'mentoring', 'collaborating', 'conflict', 'manages', 'advises'
})

VALID_ASSISTANT_KEYS = frozenset({
    'response_length', 'response_style', 'formality', 'emoji_use',
    'format', 'persona', 'proactivity', 'other'
})

VALID_EMOTIONAL_CUES = frozenset({
    'frustrated', 'excited', 'anxious', 'grateful', 'neutral'
})

# --- Deep extraction enums (Claude tier) ---
VALID_BELIEF_DOMAINS = frozenset({
    'technology', 'management', 'work-culture', 'personal', 'business'
})
VALID_KNOWLEDGE_LEVELS = frozenset({
    'expert', 'proficient', 'learning', 'aware', 'unknown'
})
VALID_TRUST_LEVELS = frozenset({'high', 'medium', 'low', 'none'})
VALID_THREAD_STATUSES = frozenset({'dormant', 'active', 'resolved'})
VALID_TRIGGER_REACTIONS = frozenset({
    'energized', 'frustrated', 'uncomfortable', 'boundary'
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_extraction(data: dict) -> tuple[dict, list[str]]:
    """Validate and clean LLM extraction output.

    Enforces:
    - Non-empty required fields
    - Closed enum membership for all categorical fields
    - Confidence values clamped to [0.0, 1.0]
    - Canonical key generation when absent

    Args:
        data: Raw dict returned by the LLM extraction call.

    Returns:
        (cleaned_data, warnings) — cleaned_data contains only valid entries;
        warnings is a list of human-readable strings describing dropped or
        defaulted fields. An empty warnings list means the output was clean.

    Example:
        cleaned, warnings = validate_extraction(llm_output)
        for w in warnings:
            logger.info("Validation: %s", w)
        store_vectors(cleaned)
    """
    if not isinstance(data, dict):
        return _empty_extraction(), ["validate_extraction: input is not a dict, returning empty"]

    warnings: list[str] = []
    cleaned: dict = {}

    cleaned['personal_info'] = _validate_personal_info(
        data.get('personal_info') or [], warnings
    )
    cleaned['preferences'] = _validate_preferences(
        data.get('preferences') or [], warnings
    )
    cleaned['events'] = _validate_events(
        data.get('events') or [], warnings
    )
    cleaned['temporal_data'] = _validate_temporal_data(
        data.get('temporal_data') or [], warnings
    )
    cleaned['updates'] = _validate_updates(
        data.get('updates') or [], warnings
    )
    cleaned['assistant_instructions'] = _validate_assistant_instructions(
        data.get('assistant_instructions') or [], warnings
    )

    # Vector 7: Goals & Projects
    cleaned['goals'] = []
    for item in data.get('goals', []) or []:
        title = (item.get('title') or '').strip()
        if not title:
            continue
        status = (item.get('status') or 'active').lower()
        if status not in VALID_GOAL_STATUSES:
            status = 'active'
            warnings.append(f"goal: invalid status, defaulted to 'active'")
        domain = (item.get('domain') or 'business').lower()
        if domain not in VALID_GOAL_DOMAINS:
            domain = 'business'
        priority = (item.get('priority') or 'medium').lower()
        if priority not in VALID_GOAL_PRIORITIES:
            priority = 'medium'
        cleaned['goals'].append({
            'title': title, 'status': status, 'domain': domain,
            'priority': priority,
            'deadline': (item.get('deadline') or '').strip(),
            'blockers': item.get('blockers', []) or [],
        })

    # Vector 10: Relationship Context
    cleaned['relationships'] = []
    for item in data.get('relationships', []) or []:
        person = (item.get('person') or '').strip()
        nature = (item.get('nature') or '').strip().lower()
        if not person or not nature:
            continue
        if nature not in VALID_RELATIONSHIP_NATURES:
            warnings.append(f"relationship: invalid nature '{nature}', dropped")
            continue
        cleaned['relationships'].append({
            'person': person, 'nature': nature,
            'context': (item.get('context') or '').strip(),
            'active': bool(item.get('active', True)),
        })

    # V14p: Emotional Cue (per-message)
    cue = (data.get('emotional_cue') or 'neutral').strip().lower()
    if cue not in VALID_EMOTIONAL_CUES:
        warnings.append(f"emotional_cue: invalid '{cue}', defaulted to 'neutral'")
        cue = 'neutral'
    cleaned['emotional_cue'] = cue

    # V16p: Question Tags
    cleaned['questions'] = []
    for item in data.get('questions', []) or []:
        if not isinstance(item, dict):
            warnings.append("questions: non-dict item dropped")
            continue
        q = (item.get('question') or '').strip()
        if not q or len(q) < 3:
            warnings.append("questions: question too short or missing, dropped")
            continue
        cleaned['questions'].append({
            'question': q,
            'expecting_answer': bool(item.get('expecting_answer', True)),
        })

    return cleaned, warnings


# ---------------------------------------------------------------------------
# Per-vector validators (private)
# ---------------------------------------------------------------------------

def _validate_personal_info(items: list, warnings: list[str]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("personal_info: non-dict item dropped")
            continue
        key = (item.get('key') or '').strip().lower()
        value = (item.get('value') or '').strip()
        if not key or not value:
            warnings.append("personal_info: missing key or value, dropped")
            continue
        if key not in VALID_PERSONAL_KEYS:
            warnings.append(f"personal_info: invalid key '{key}', dropped")
            continue
        conf = _clamp_confidence(item.get('confidence', 0.7))
        out.append({'key': key, 'value': value, 'confidence': conf})
    return out


def _validate_preferences(items: list, warnings: list[str]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("preferences: non-dict item dropped")
            continue
        domain = (item.get('domain') or '').strip().lower()
        stmt = (item.get('statement') or '').strip()
        ckey = (item.get('canonical_key') or '').strip().lower()

        if not stmt or len(stmt) < 5:
            warnings.append("preferences: statement too short or missing, dropped")
            continue

        if domain not in VALID_PREFERENCE_DOMAINS:
            warnings.append(
                f"preferences: invalid domain '{domain}', defaulted to 'content'"
            )
            domain = 'content'

        valence = (item.get('valence') or 'NEUTRAL').strip().upper()
        if valence not in VALID_VALENCES:
            warnings.append(
                f"preferences: invalid valence '{valence}', defaulted to 'NEUTRAL'"
            )
            valence = 'NEUTRAL'

        strength = _clamp_confidence(item.get('strength', 0.5))

        if not ckey:
            ckey = _generate_canonical_key(stmt, domain)

        out.append({
            'domain': domain,
            'canonical_key': ckey,
            'statement': stmt,
            'valence': valence,
            'strength': strength,
        })
    return out


def _validate_events(items: list, warnings: list[str]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("events: non-dict item dropped")
            continue
        title = (item.get('title') or '').strip()
        if not title:
            warnings.append("events: missing title, dropped")
            continue
        event_type = (item.get('event_type') or 'MEETING').strip().upper()
        if event_type not in VALID_EVENT_TYPES:
            warnings.append(
                f"events: invalid event_type '{event_type}', defaulted to MEETING"
            )
            event_type = 'MEETING'
        participants = item.get('participants') or []
        if not isinstance(participants, list):
            participants = []
        out.append({
            'title': title,
            'event_type': event_type,
            'start_time': (item.get('start_time') or '').strip(),
            'participants': participants,
        })
    return out


def _validate_temporal_data(items: list, warnings: list[str]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("temporal_data: non-dict item dropped")
            continue
        subject = (item.get('subject') or '').strip().lower()
        new_val = (item.get('new_value') or '').strip()
        if not subject or not new_val:
            warnings.append(
                "temporal_data: missing subject or new_value, dropped"
            )
            continue
        out.append({
            'subject': subject,
            'old_value': (item.get('old_value') or '').strip(),
            'new_value': new_val,
            'valid_from': (item.get('valid_from') or '').strip(),
        })
    return out


def _validate_updates(items: list, warnings: list[str]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("updates: non-dict item dropped")
            continue
        corrects = (
            item.get('corrects_field') or item.get('corrects') or ''
        ).strip()
        new_val = (item.get('new_value') or '').strip()
        if not corrects or not new_val:
            warnings.append(
                "updates: missing corrects_field or new_value, dropped"
            )
            continue
        out.append({
            'corrects_field': corrects,
            'old_value': (item.get('old_value') or '').strip(),
            'new_value': new_val,
            'verbatim': (item.get('verbatim') or '').strip(),
        })
    return out


def _validate_assistant_instructions(items: list, warnings: list[str]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("assistant_instructions: non-dict item dropped")
            continue
        key = (item.get('key') or '').strip().lower()
        instruction = (item.get('instruction') or '').strip()
        if not key or not instruction:
            warnings.append(
                "assistant_instructions: missing key or instruction, dropped"
            )
            continue
        if key not in VALID_ASSISTANT_KEYS:
            warnings.append(
                f"assistant_instructions: invalid key '{key}', dropped"
            )
            continue
        conf = _clamp_confidence(item.get('confidence', 0.7))
        out.append({'key': key, 'instruction': instruction, 'confidence': conf})
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_confidence(val) -> float:
    """Clamp val to [0.0, 1.0], default 0.5 on type error."""
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return 0.5


def _generate_canonical_key(statement: str, domain: str) -> str:
    """Generate a stable canonical key from statement text for MERGE dedup.

    Uses the first 5 words of the lowercased statement, prefixed by domain.
    Strips non-alphanumeric characters to produce a clean token.

    Example:
        _generate_canonical_key("Prefers short replies", "communication")
        # -> "communication:prefers_short_replies"
    """
    import re
    words = re.sub(r'[^a-z0-9 ]', '', statement.lower()).split()[:5]
    return f"{domain}:{'_'.join(words)}"


def _empty_extraction() -> dict:
    """Return the canonical empty extraction structure."""
    return {
        'personal_info': [],
        'preferences': [],
        'events': [],
        'temporal_data': [],
        'updates': [],
        'assistant_instructions': [],
        'emotional_cue': 'neutral',
        'questions': [],
    }


def validate_deep_extraction(data: dict) -> tuple[dict, list[str]]:
    """Validate deep extraction output (V11, V13-17).

    Similar to validate_extraction but for the Claude deep tier vectors.
    """
    if not isinstance(data, dict):
        return _empty_deep_extraction(), ["validate_deep_extraction: input is not a dict"]

    warnings: list[str] = []
    cleaned: dict = {}

    # V11: Implicit Beliefs
    cleaned['implicit_beliefs'] = []
    for item in data.get('implicit_beliefs', []) or []:
        if not isinstance(item, dict):
            continue
        belief = (item.get('belief') or '').strip()
        if not belief or len(belief) < 5:
            warnings.append("implicit_beliefs: belief too short, dropped")
            continue
        domain = (item.get('domain') or 'business').lower()
        if domain not in VALID_BELIEF_DOMAINS:
            domain = 'business'
        cleaned['implicit_beliefs'].append({
            'belief': belief,
            'evidence_count': max(1, int(item.get('evidence_count', 1))),
            'confidence': _clamp_confidence(item.get('confidence', 0.5)),
            'domain': domain,
        })

    # V13: Decision Patterns
    cleaned['decision_patterns'] = []
    for item in data.get('decision_patterns', []) or []:
        if not isinstance(item, dict):
            continue
        pattern = (item.get('pattern') or '').strip()
        if not pattern or len(pattern) < 5:
            warnings.append("decision_patterns: pattern too short, dropped")
            continue
        domain = (item.get('domain') or 'business').lower()
        if domain not in VALID_BELIEF_DOMAINS:
            domain = 'business'
        cleaned['decision_patterns'].append({
            'pattern': pattern,
            'domain': domain,
            'evidence': (item.get('evidence') or '').strip(),
            'confidence': _clamp_confidence(item.get('confidence', 0.5)),
        })

    # V14: Emotional Patterns/Triggers
    cleaned['emotional_patterns'] = []
    for item in data.get('emotional_patterns', []) or []:
        if not isinstance(item, dict):
            continue
        trigger = (item.get('trigger') or '').strip()
        if not trigger:
            continue
        reaction = (item.get('reaction') or '').strip().lower()
        if reaction not in VALID_TRIGGER_REACTIONS:
            warnings.append(f"emotional_patterns: invalid reaction '{reaction}', dropped")
            continue
        cleaned['emotional_patterns'].append({
            'trigger': trigger,
            'reaction': reaction,
            'context': (item.get('context') or '').strip(),
            'evidence_count': max(1, int(item.get('evidence_count', 1))),
        })

    # V15: Knowledge Levels
    cleaned['knowledge_levels'] = []
    for item in data.get('knowledge_levels', []) or []:
        if not isinstance(item, dict):
            continue
        domain = (item.get('domain') or '').strip().lower()
        if not domain:
            continue
        level = (item.get('level') or 'unknown').strip().lower()
        if level not in VALID_KNOWLEDGE_LEVELS:
            level = 'unknown'
        cleaned['knowledge_levels'].append({
            'domain': domain,
            'level': level,
            'evidence': (item.get('evidence') or '').strip(),
            'last_assessed': (item.get('last_assessed') or '').strip(),
        })

    # V16: Unresolved Threads
    cleaned['unresolved_threads'] = []
    for item in data.get('unresolved_threads', []) or []:
        if not isinstance(item, dict):
            continue
        topic = (item.get('topic') or '').strip()
        if not topic:
            continue
        status = (item.get('status') or 'active').strip().lower()
        if status not in VALID_THREAD_STATUSES:
            status = 'active'
        cleaned['unresolved_threads'].append({
            'topic': topic,
            'first_mentioned': (item.get('first_mentioned') or '').strip(),
            'status': status,
            'related_goal': (item.get('related_goal') or '').strip(),
        })

    # V17: Trust Map
    cleaned['trust_map'] = []
    for item in data.get('trust_map', []) or []:
        if not isinstance(item, dict):
            continue
        target = (item.get('target') or '').strip()
        if not target:
            continue
        level = (item.get('trust_level') or 'medium').strip().lower()
        if level not in VALID_TRUST_LEVELS:
            level = 'medium'
        cleaned['trust_map'].append({
            'target': target,
            'domain': (item.get('domain') or 'general').strip().lower(),
            'trust_level': level,
            'evidence': (item.get('evidence') or '').strip(),
        })

    return cleaned, warnings


def _empty_deep_extraction() -> dict:
    """Return empty deep extraction structure."""
    return {
        'implicit_beliefs': [],
        'decision_patterns': [],
        'emotional_patterns': [],
        'knowledge_levels': [],
        'unresolved_threads': [],
        'trust_map': [],
    }
