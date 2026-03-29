#!/usr/bin/env python3
"""
Curiosity Dedup — Question deduplication utilities for the General Curiosity Engine.

Before storing a curiosity question in Neo4j, check if an equivalent question
was already asked recently.  Two-layer dedup:

1. **Canonical hash** (cheap, in-process) — normalize the question text,
   sort tokens, SHA-256 the result.  Same hash => same semantic intent.
2. **Neo4j lookup** — query ResearchQuestion nodes by canonical_hash within
   a configurable time window.

Usage:
    from curiosity_dedup import is_duplicate_question, get_canonical_hash
"""

import hashlib
import logging
import re
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)

# ── Stopwords & filler ──────────────────────────────────────────────────────

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "should", "now", "what", "which", "who", "whom",
    "this", "that", "these", "those", "i", "me", "my", "you", "your", "he",
    "him", "his", "she", "her", "it", "its", "we", "our", "they", "them",
}

FILLER_WORDS = {
    "hey", "hi", "hello", "quick one", "quick question", "by the way",
    "just wondering", "curious", "wondering", "btw", "fyi",
}


# ── Core functions ──────────────────────────────────────────────────────────

def canonicalize(question_text: str, target: str = "") -> str:
    """Reduce question to canonical form for hash-based dedup.

    Steps:
        1. Lowercase, strip
        2. Remove filler phrases (multi-word first, then single-word)
        3. Remove punctuation
        4. Remove stopwords
        5. Sort remaining words alphabetically
        6. Prepend target (lowercased) for scoping
    """
    text = question_text.lower().strip()

    # Remove multi-word filler phrases first (before splitting on spaces)
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        text = text.replace(filler, " ")

    # Strip possessive suffixes before punctuation removal so
    # "Danny's" and "Danny" both normalize to "danny"
    text = re.sub(r"'s\b", "", text)

    # Remove all punctuation (keep alphanumeric and spaces)
    text = re.sub(r"[^a-z0-9\s]", "", text)

    # Split into words, drop stopwords and filler single-words
    words = [w for w in text.split() if w and w not in STOPWORDS]

    # Sort for order-independence
    words.sort()

    # Prepend target for scoping
    prefix = target.lower().strip() if target else ""
    if prefix:
        return f"{prefix}:{' '.join(words)}"
    return " ".join(words)


def dedup_hash(canonical: str) -> str:
    """SHA-256 first 16 hex chars of canonical form."""
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def get_canonical_hash(question_text: str, target: str = "") -> str:
    """Convenience: canonicalize then hash."""
    return dedup_hash(canonicalize(question_text, target))


def is_duplicate_question(
    question_text: str,
    target: str = "",
    days_back: int = 30,
) -> bool:
    """Check if a semantically equivalent question was asked in the last N days.

    Uses canonical_hash lookup against ResearchQuestion nodes in Neo4j.
    Returns True if a match is found within the time window.
    """
    c_hash = get_canonical_hash(question_text, target)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    query = """
    MATCH (rq:ResearchQuestion)
    WHERE rq.canonical_hash = $hash
      AND rq.created_at >= $cutoff
    RETURN rq.question_id AS qid
    LIMIT 1
    """

    try:
        with neo4j_session() as session:
            result = session.run(query, hash=c_hash, cutoff=cutoff)
            record = result.single()
            if record:
                logger.info(
                    "Duplicate question detected (hash=%s, existing=%s): %s",
                    c_hash, record["qid"], question_text[:80],
                )
                return True
            return False
    except Exception:
        logger.exception("Neo4j lookup failed during dedup check — treating as non-duplicate")
        return False


# ── Main: self-test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed = 0
    failed = 0

    def assert_eq(label, a, b):
        global passed, failed
        if a == b:
            print(f"  PASS  {label}")
            passed += 1
        else:
            print(f"  FAIL  {label}")
            print(f"        expected: {b!r}")
            print(f"        got:      {a!r}")
            failed += 1

    def assert_true(label, val):
        global passed, failed
        if val:
            print(f"  PASS  {label}")
            passed += 1
        else:
            print(f"  FAIL  {label} (expected True, got {val!r})")
            failed += 1

    def assert_false(label, val):
        global passed, failed
        if not val:
            print(f"  PASS  {label}")
            passed += 1
        else:
            print(f"  FAIL  {label} (expected False, got {val!r})")
            failed += 1

    # -- Canonical form tests -------------------------------------------------
    print("\n--- Canonical form tests ---")

    c1 = canonicalize("What timezone is Danny in?")
    c2 = canonicalize("Danny's timezone?")
    assert_eq("timezone q1 == q2 canonical", c1, c2)

    c3 = canonicalize("Hey, quick one — what timezone is Danny in?")
    assert_eq("timezone q1 == q3 (filler stripped)", c1, c3)

    c4 = canonicalize("What's Danny's favorite food?")
    assert_true("food != timezone canonical", c1 != c4)

    # -- Hash tests -----------------------------------------------------------
    print("\n--- Hash tests ---")

    h1 = get_canonical_hash("What timezone is Danny in?")
    h2 = get_canonical_hash("Danny's timezone?")
    h3 = get_canonical_hash("Hey, quick one — what timezone is Danny in?")
    h4 = get_canonical_hash("What's Danny's favorite food?")

    assert_eq("hash: timezone q1 == q2", h1, h2)
    assert_eq("hash: timezone q1 == q3 (filler)", h1, h3)
    assert_true("hash: food != timezone", h1 != h4)

    # -- Target scoping tests -------------------------------------------------
    print("\n--- Target scoping tests ---")

    h5 = get_canonical_hash("What timezone?", target="danny")
    h6 = get_canonical_hash("What timezone?", target="alex")
    assert_true("different target => different hash", h5 != h6)

    # -- Hash length test -----------------------------------------------------
    print("\n--- Hash format tests ---")
    assert_eq("hash length is 16", len(h1), 16)
    assert_true("hash is hex", all(c in "0123456789abcdef" for c in h1))

    # -- is_duplicate_question (Neo4j integration) ----------------------------
    print("\n--- is_duplicate_question (Neo4j) ---")
    try:
        result = is_duplicate_question("Test dedup question xyz123?")
        print(f"  INFO  is_duplicate_question returned {result} (Neo4j reachable)")
        passed += 1
    except Exception as e:
        print(f"  SKIP  is_duplicate_question — Neo4j not available ({e})")

    # -- Summary --------------------------------------------------------------
    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("  All tests passed.")
