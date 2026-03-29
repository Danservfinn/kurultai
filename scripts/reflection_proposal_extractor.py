#!/usr/bin/env python3
"""
reflection_proposal_extractor.py — Extract proposals from Kurultai agent
reflection markdown files and route them into the voting/task pipeline.

Scans reflection files and standalone proposal files for:
  - WHEN/THEN rules (self-scoped or cross-agent)
  - Immediate action items (CRITICAL / HIGH priority)
  - Skill improvement proposals

Extracted proposals are classified into tiers (T0/T1/T2) and routed:
  T0 → task_intake.create_task() directly (critical infra actions)
  T1 → proposals/approved/ with synthetic vote (self-scoped rules)
  T2 → proposals/pending/ via staging in proposals/extracted/

Usage:
    python3 reflection_proposal_extractor.py --extract
    python3 reflection_proposal_extractor.py --extract --agent ogedei
    python3 reflection_proposal_extractor.py --dry-run
    python3 reflection_proposal_extractor.py --stats
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
REFLECTIONS_DIR = AGENTS_DIR / "main" / "reflections"
PROPOSALS_DIR = AGENTS_DIR / "main" / "proposals"
LOGS_DIR = AGENTS_DIR / "main" / "logs"
STATE_FILE = LOGS_DIR / "extractor-state.json"
AUDIT_LOG = LOGS_DIR / "proposal-extractor.jsonl"
REFLECTION_STATUS = LOGS_DIR / "reflection-status.json"

ALL_AGENTS = {"kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"}

DEDUP_WINDOW_HOURS = 24

# Regex patterns ----------------------------------------------------------

# Rule ID heading: ### O008: Drift-Triggered ... OR ### M007 (NEW) OR ### R15 (CONFIRM ...)
RE_RULE_ID = re.compile(r"###\s+([\w\-]+)(?::\s*(.+)|\s*\(([^)]+)\)(.*)|(.*))")

# WHEN/THEN blocks (may span multiple lines, ended by double newline or next heading)
RE_WHEN_THEN = re.compile(
    r"\*\*WHEN:\*\*\s*(.+?)(?:\n\n|\n(?=\*\*THEN))"
    r"\*\*THEN:\*\*\s*(.+?)(?:\n\n|\n(?=\*\*Why)|\Z)"
    r"(?:\*\*Why:\*\*\s*(.+?))?",
    re.DOTALL,
)

# Immediate action lines:  1. **CRITICAL**: Fix model drift ...
RE_ACTION = re.compile(r"^\d+\.\s+\*\*(\w+)\*\*:\s*(.+)$", re.MULTILINE)

# Skill improvement proposals: 1. **/horde-learn activation gate** — ...
RE_SKILL = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*\s*[—\-–]\s*(.+)$", re.MULTILINE)

# Section headers that contain rules
RULE_SECTION_PATTERNS = [
    "New WHEN/THEN Rules Proposed",
    "Rules Generated This Cycle",
    "WHEN/THEN Rules",
]

ACTION_SECTION_PATTERNS = [
    "Immediate Actions Required",
    "Immediate Actions",
    "Actions Required",
]

SKILL_SECTION_PATTERNS = [
    "Skill Improvement Proposals",
]

# Critical action keywords for T0 classification
CRITICAL_KEYWORDS = [
    "restart", "fix", "restore", "credential", "oom",
    "sigkill", "down", "broken",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Proposal:
    """Extracted proposal from a reflection file."""

    def __init__(self, proposal_type: str, rule_id: str, title: str,
                 body: str, source_agent: str, source_file: str,
                 priority: Optional[str] = None,
                 when_clause: Optional[str] = None,
                 then_clause: Optional[str] = None,
                 why_clause: Optional[str] = None,
                 target_agent: Optional[str] = None):
        self.proposal_type = proposal_type  # RULE, ACTION, SKILL
        self.rule_id = rule_id
        self.title = title
        self.body = body
        self.source_agent = source_agent
        self.source_file = source_file
        self.priority = priority
        self.when_clause = when_clause
        self.then_clause = then_clause
        self.why_clause = why_clause
        self.target_agent = target_agent or source_agent
        self.tier = ""
        self.fingerprint = ""
        self.proposal_id = ""


# ---------------------------------------------------------------------------
# Fingerprinting / dedup
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize text for fingerprinting: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def compute_fingerprint(proposal: Proposal) -> str:
    """SHA256 fingerprint for dedup."""
    if proposal.proposal_type == "RULE" and proposal.when_clause and proposal.then_clause:
        raw = f"{proposal.source_agent}|{_normalize(proposal.when_clause)}|{_normalize(proposal.then_clause)}"
    else:
        raw = f"{proposal.source_agent}|{_normalize(proposal.title)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def load_state() -> dict:
    """Load extractor state (seen fingerprints + last_run)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"seen": {}, "last_run": None, "stats": {}}


def save_state(state: dict) -> None:
    """Persist extractor state."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_duplicate(fingerprint: str, state: dict) -> bool:
    """Check if fingerprint was seen within the dedup window."""
    seen = state.get("seen", {})
    if fingerprint not in seen:
        return False
    last_seen = datetime.fromisoformat(seen[fingerprint])
    return (datetime.now(timezone.utc) - last_seen) < timedelta(hours=DEDUP_WINDOW_HOURS)


def mark_seen(fingerprint: str, state: dict) -> None:
    """Record a fingerprint as seen now."""
    state.setdefault("seen", {})[fingerprint] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def audit_log(event: str, agent: str = "", tier: str = "",
              proposal_id: str = "", fingerprint: str = "",
              extra: Optional[dict] = None) -> None:
    """Append a JSONL audit entry."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "agent": agent,
        "tier": tier,
        "proposal_id": proposal_id,
        "fingerprint": fingerprint,
    }
    if extra:
        entry.update(extra)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def classify_tier(proposal: Proposal) -> str:
    """Classify a proposal into T0, T1, or T2."""
    # T0: CRITICAL immediate infrastructure actions
    if proposal.proposal_type == "ACTION" and proposal.priority == "CRITICAL":
        if any(kw in proposal.body.lower() for kw in CRITICAL_KEYWORDS):
            return "T0"

    # T1: Self-scoped rules (only affects the proposing agent)
    if proposal.proposal_type == "RULE":
        other_agents = ALL_AGENTS - {proposal.source_agent}
        text = proposal.body.lower()
        if not any(a in text for a in other_agents):
            return "T1"

    # T2: Everything else (cross-agent, skills, non-critical actions)
    return "T2"


# ---------------------------------------------------------------------------
# Agent detection from filename
# ---------------------------------------------------------------------------

def detect_agent(filepath: Path) -> Optional[str]:
    """Extract the source agent name from a reflection/proposal filename."""
    name = filepath.stem.lower()
    for agent in ALL_AGENTS:
        if agent in name:
            return agent
    # Check frontmatter for agent field
    try:
        text = filepath.read_text(errors="replace")[:1000]
        m = re.search(r"\*\*Agent:\*\*\s*(\w+)", text)
        if m and m.group(1).lower() in ALL_AGENTS:
            return m.group(1).lower()
        m = re.search(r"^agent:\s*(\w+)", text, re.MULTILINE)
        if m and m.group(1).lower() in ALL_AGENTS:
            return m.group(1).lower()
    except OSError:
        pass
    return None


def detect_target_agent(text: str, source_agent: str) -> str:
    """Guess the target agent from proposal text, defaulting to source."""
    lower = text.lower()
    for agent in ALL_AGENTS:
        if agent in lower and agent != source_agent:
            return agent
    return source_agent


# ---------------------------------------------------------------------------
# Section extraction helpers
# ---------------------------------------------------------------------------

def _extract_section(text: str, header_patterns: list[str]) -> str:
    """Return the content under a section matching any of the header patterns.

    Correctly handles nested headings: a ## section includes ### sub-headings
    and only terminates at the next ## (same or higher level) heading.
    """
    for pat in header_patterns:
        # Find the header line containing the pattern
        header_re = re.compile(
            r"^(#{2,3})\s*.*?" + re.escape(pat) + r".*$",
            re.MULTILINE | re.IGNORECASE,
        )
        hm = header_re.search(text)
        if not hm:
            continue
        level = len(hm.group(1))  # 2 for ##, 3 for ###
        start = hm.end()
        # End at the next heading of same or higher level (fewer or equal #'s)
        end_re = re.compile(r"^#{2," + str(level) + r"}\s", re.MULTILINE)
        em = end_re.search(text, start)
        return text[start:em.start()] if em else text[start:]
    return ""


# ---------------------------------------------------------------------------
# Extraction from a single file
# ---------------------------------------------------------------------------

def extract_proposals(filepath: Path, agent_filter: Optional[str] = None) -> list[Proposal]:
    """Parse a markdown file and extract all proposals."""
    proposals: list[Proposal] = []
    try:
        text = filepath.read_text(errors="replace")
    except OSError as exc:
        audit_log("parse_error", extra={"file": str(filepath), "error": str(exc)})
        return proposals

    source_agent = detect_agent(filepath)
    if source_agent is None:
        return proposals
    if agent_filter and source_agent != agent_filter:
        return proposals

    # --- Pattern 1: WHEN/THEN rules ---
    rule_section = _extract_section(text, RULE_SECTION_PATTERNS)
    if rule_section:
        _extract_rules(rule_section, source_agent, filepath, proposals)

    # --- Pattern 2: Immediate actions ---
    action_section = _extract_section(text, ACTION_SECTION_PATTERNS)
    if action_section:
        _extract_actions(action_section, source_agent, filepath, proposals)

    # --- Pattern 3: Skill improvement proposals ---
    skill_section = _extract_section(text, SKILL_SECTION_PATTERNS)
    if skill_section:
        _extract_skills(skill_section, source_agent, filepath, proposals)

    return proposals


def _extract_rules(section: str, source_agent: str, filepath: Path,
                   out: list[Proposal]) -> None:
    """Extract WHEN/THEN rule proposals from a section."""
    # Split on ### headings to process each rule block
    blocks = re.split(r"(?=^###\s)", section, flags=re.MULTILINE)
    for block in blocks:
        if not block.strip():
            continue
        # Get rule ID from heading
        # Group 2: "ID: Title" format
        # Group 3: tag from "ID (TAG)", Group 4: trailing text after tag
        # Group 5: plain "ID" with no colon or parens
        id_match = RE_RULE_ID.search(block)
        if id_match:
            rule_id = id_match.group(1)
            if id_match.group(2):
                rule_title = id_match.group(2).strip()
            elif id_match.group(3):
                tag = id_match.group(3).strip()
                extra = (id_match.group(4) or "").strip().lstrip("—- ").strip()
                rule_title = f"{rule_id} [{tag}]" + (f" {extra}" if extra else "")
            else:
                rule_title = rule_id
        else:
            rule_id = "UNKNOWN"
            rule_title = "Unnamed Rule"

        # Extract WHEN/THEN/Why
        wt_match = RE_WHEN_THEN.search(block)
        if not wt_match:
            continue

        when_clause = wt_match.group(1).strip()
        then_clause = wt_match.group(2).strip()
        why_clause = (wt_match.group(3) or "").strip()

        body = f"WHEN: {when_clause}\nTHEN: {then_clause}"
        if why_clause:
            body += f"\nWhy: {why_clause}"

        prop = Proposal(
            proposal_type="RULE",
            rule_id=rule_id,
            title=f"{rule_id}: {rule_title}",
            body=body,
            source_agent=source_agent,
            source_file=str(filepath),
            when_clause=when_clause,
            then_clause=then_clause,
            why_clause=why_clause,
            target_agent=detect_target_agent(body, source_agent),
        )
        out.append(prop)


def _extract_actions(section: str, source_agent: str, filepath: Path,
                     out: list[Proposal]) -> None:
    """Extract immediate action proposals from a section."""
    for m in RE_ACTION.finditer(section):
        priority = m.group(1).strip().upper()
        action_text = m.group(2).strip()

        prop = Proposal(
            proposal_type="ACTION",
            rule_id="",
            title=action_text[:120],
            body=action_text,
            source_agent=source_agent,
            source_file=str(filepath),
            priority=priority,
            target_agent=detect_target_agent(action_text, source_agent),
        )
        out.append(prop)


def _extract_skills(section: str, source_agent: str, filepath: Path,
                    out: list[Proposal]) -> None:
    """Extract skill improvement proposals from a section."""
    for m in RE_SKILL.finditer(section):
        skill_name = m.group(1).strip()
        description = m.group(2).strip()

        prop = Proposal(
            proposal_type="SKILL",
            rule_id="",
            title=f"Skill: {skill_name}",
            body=description,
            source_agent=source_agent,
            source_file=str(filepath),
            target_agent=detect_target_agent(description, source_agent),
        )
        out.append(prop)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files(agent_filter: Optional[str] = None) -> list[Path]:
    """Find all reflection and standalone proposal files to scan."""
    files: list[Path] = []

    # 1. Reflection files: reflection-*-2026-*.md
    if REFLECTIONS_DIR.exists():
        for f in sorted(REFLECTIONS_DIR.glob("reflection-*-2026-*.md")):
            if f.is_file():
                files.append(f)

    # 2. Standalone proposal files in proposals/ root (not subdirectories)
    if PROPOSALS_DIR.exists():
        for f in sorted(PROPOSALS_DIR.glob("*.md")):
            if f.is_file():
                files.append(f)

    return files


# ---------------------------------------------------------------------------
# Race condition guard
# ---------------------------------------------------------------------------

def check_reflection_ready(state: dict) -> bool:
    """Verify reflections are content_complete and not already processed."""
    if not REFLECTION_STATUS.exists():
        return True  # No guard file — proceed (best-effort)

    try:
        status = json.loads(REFLECTION_STATUS.read_text())
    except (json.JSONDecodeError, OSError):
        return True

    if status.get("status") != "content_complete":
        return False

    # Check if we already processed this timestamp
    last_run = state.get("last_run")
    status_ts = status.get("timestamp")
    if last_run and status_ts:
        try:
            last_dt = datetime.fromisoformat(last_run)
            status_dt = datetime.fromisoformat(status_ts)
            if last_dt >= status_dt:
                return False  # Already processed
        except (ValueError, TypeError):
            pass

    return True


# ---------------------------------------------------------------------------
# Routing (T0 / T1 / T2)
# ---------------------------------------------------------------------------

def generate_proposal_id(proposal: Proposal) -> str:
    """Generate a deterministic proposal ID."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", proposal.title.lower())[:40].strip("-")
    return f"{proposal.source_agent}-{ts}-{slug}"


def route_t0(proposal: Proposal) -> str:
    """T0: Create task directly via task_intake."""
    try:
        sys.path.insert(0, str(AGENTS_DIR / "main" / "scripts"))
        from task_intake import create_task
        task_id = create_task(
            title=proposal.title,
            body=proposal.body,
            priority="high",
            source="proposal-extractor",
            bucket="TODAY",
            agent=proposal.target_agent,
        )
        audit_log("t0_task_created", proposal.source_agent, "T0",
                  proposal.proposal_id, proposal.fingerprint,
                  extra={"task_id": task_id or ""})
        return task_id or ""
    except Exception as exc:
        audit_log("parse_error", proposal.source_agent, "T0",
                  proposal.proposal_id, proposal.fingerprint,
                  extra={"error": str(exc)})
        return ""


def route_t1(proposal: Proposal) -> str:
    """T1: Write to approved/ with synthetic vote file."""
    approved_dir = PROPOSALS_DIR / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)

    pid = proposal.proposal_id
    now_iso = datetime.now().isoformat()

    # Write proposal markdown
    md_content = (
        f"---\n"
        f"proposal_id: {pid}\n"
        f"agent: {proposal.source_agent}\n"
        f"created: {now_iso}\n"
        f"status: approved\n"
        f"tier: T1\n"
        f"result: Auto-approved (self-scoped rule)\n"
        f"finalized: {now_iso}\n"
        f"---\n\n"
        f"# Proposal: {proposal.title}\n\n"
        f"## Source\n"
        f"Agent: {proposal.source_agent}\n"
        f"File: {proposal.source_file}\n\n"
        f"## Content\n"
        f"{proposal.body}\n"
    )
    (approved_dir / f"{pid}.md").write_text(md_content)

    # Write synthetic votes JSON
    votes = {}
    for agent in sorted(ALL_AGENTS):
        votes[agent] = {
            "agent": agent,
            "vote": "APPROVE",
            "timestamp": now_iso,
            "reason": "Auto-approved: self-scoped rule (T1)" if agent == proposal.source_agent else None,
        }
    (approved_dir / f"{pid}-votes.json").write_text(json.dumps(votes, indent=2))

    audit_log("t1_auto_approved", proposal.source_agent, "T1",
              pid, proposal.fingerprint)
    return pid


def route_t2(proposal: Proposal) -> str:
    """T2: Stage in extracted/, then move to pending/."""
    extracted_dir = PROPOSALS_DIR / "extracted"
    pending_dir = PROPOSALS_DIR / "pending"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    pending_dir.mkdir(parents=True, exist_ok=True)

    pid = proposal.proposal_id
    now_iso = datetime.now().isoformat()

    md_content = (
        f"---\n"
        f"proposal_id: {pid}\n"
        f"agent: {proposal.source_agent}\n"
        f"type: {proposal.proposal_type}\n"
        f"created: {now_iso}\n"
        f"status: pending\n"
        f"tier: T2\n"
        f"---\n\n"
        f"# Proposal: {proposal.title}\n\n"
        f"## Source\n"
        f"Agent: {proposal.source_agent}\n"
        f"File: {proposal.source_file}\n\n"
        f"## Content\n"
        f"{proposal.body}\n"
    )

    staging_path = extracted_dir / f"{pid}.md"
    final_path = pending_dir / f"{pid}.md"
    staging_path.write_text(md_content)
    os.rename(str(staging_path), str(final_path))

    audit_log("extracted", proposal.source_agent, "T2",
              pid, proposal.fingerprint)
    return pid


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_extraction(agent_filter: Optional[str] = None,
                   dry_run: bool = False) -> dict:
    """Run the full extraction pipeline. Returns summary stats."""
    state = load_state()

    if not dry_run and not check_reflection_ready(state):
        print("[extractor] Skipping: reflections not ready or already processed.")
        return {"skipped": True}

    files = discover_files(agent_filter)
    if not files:
        print("[extractor] No files found to scan.")
        return {"files": 0, "proposals": 0}

    stats = {"files": len(files), "proposals": 0, "by_tier": {}, "dedup_skipped": 0, "errors": 0}

    for fpath in files:
        proposals = extract_proposals(fpath, agent_filter)
        for prop in proposals:
            prop.fingerprint = compute_fingerprint(prop)
            prop.tier = classify_tier(prop)
            prop.proposal_id = generate_proposal_id(prop)

            if is_duplicate(prop.fingerprint, state):
                stats["dedup_skipped"] += 1
                if dry_run:
                    print(f"  [DEDUP] {prop.tier} | {prop.source_agent} | {prop.title}")
                else:
                    audit_log("dedup_skip", prop.source_agent, prop.tier,
                              prop.proposal_id, prop.fingerprint)
                continue

            stats["proposals"] += 1
            stats["by_tier"][prop.tier] = stats["by_tier"].get(prop.tier, 0) + 1

            if dry_run:
                print(f"  [{prop.tier}] {prop.proposal_type:6s} | {prop.source_agent:10s} | {prop.title}")
                if prop.when_clause:
                    print(f"         WHEN: {prop.when_clause[:80]}")
                    print(f"         THEN: {prop.then_clause[:80]}")
                continue

            # Route based on tier
            mark_seen(prop.fingerprint, state)
            try:
                if prop.tier == "T0":
                    route_t0(prop)
                elif prop.tier == "T1":
                    route_t1(prop)
                else:
                    route_t2(prop)
            except Exception as exc:
                stats["errors"] += 1
                audit_log("parse_error", prop.source_agent, prop.tier,
                          prop.proposal_id, prop.fingerprint,
                          extra={"error": str(exc)})

    if not dry_run:
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        state["stats"] = stats
        # Prune seen entries older than dedup window
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)).isoformat()
        state["seen"] = {k: v for k, v in state.get("seen", {}).items() if v > cutoff}
        save_state(state)

    return stats


def show_stats() -> None:
    """Display extraction statistics from the state file."""
    state = load_state()
    last_run = state.get("last_run", "never")
    stats = state.get("stats", {})
    seen_count = len(state.get("seen", {}))

    print("=== Proposal Extractor Statistics ===")
    print(f"  Last run:        {last_run}")
    print(f"  Seen fingerprints (active): {seen_count}")
    if stats:
        print(f"  Files scanned:   {stats.get('files', 0)}")
        print(f"  Proposals found: {stats.get('proposals', 0)}")
        print(f"  Dedup skipped:   {stats.get('dedup_skipped', 0)}")
        print(f"  Errors:          {stats.get('errors', 0)}")
        by_tier = stats.get("by_tier", {})
        if by_tier:
            print(f"  By tier:         {json.dumps(by_tier)}")

    # Show audit log tail
    if AUDIT_LOG.exists():
        lines = AUDIT_LOG.read_text().strip().split("\n")
        recent = lines[-5:] if len(lines) >= 5 else lines
        print(f"\n  Recent audit entries ({len(lines)} total):")
        for line in recent:
            try:
                entry = json.loads(line)
                print(f"    {entry.get('ts', '?')[:19]}  {entry.get('event', '?'):20s}  "
                      f"{entry.get('tier', ''):3s}  {entry.get('agent', '')}")
            except json.JSONDecodeError:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract proposals from Kurultai agent reflections.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s --extract              Full extraction\n"
            "  %(prog)s --extract --agent ogedei  Single agent\n"
            "  %(prog)s --dry-run              Preview only\n"
            "  %(prog)s --stats                Show statistics\n"
        ),
    )
    parser.add_argument("--extract", action="store_true",
                        help="Run full extraction pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview proposals without writing anything")
    parser.add_argument("--stats", action="store_true",
                        help="Show extraction statistics")
    parser.add_argument("--agent", type=str, default=None,
                        choices=sorted(ALL_AGENTS),
                        help="Filter to a single agent")

    args = parser.parse_args()

    if not (args.extract or args.dry_run or args.stats):
        parser.print_help()
        sys.exit(1)

    if args.stats:
        show_stats()
        return

    if args.dry_run:
        print("[extractor] DRY RUN — no files will be written\n")
        stats = run_extraction(agent_filter=args.agent, dry_run=True)
    elif args.extract:
        stats = run_extraction(agent_filter=args.agent, dry_run=False)
    else:
        parser.print_help()
        sys.exit(1)

    if stats.get("skipped"):
        return

    print(f"\n[extractor] Done. "
          f"Files={stats.get('files', 0)}, "
          f"Proposals={stats.get('proposals', 0)}, "
          f"Dedup={stats.get('dedup_skipped', 0)}, "
          f"Errors={stats.get('errors', 0)}, "
          f"Tiers={json.dumps(stats.get('by_tier', {}))}")


if __name__ == "__main__":
    main()
