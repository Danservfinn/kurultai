#!/usr/bin/env python3
"""
task_router.py — Core routing logic for Kurultai task routing.

Extracted from task_intake.py for maintainability.

Usage:
    from task_router import route_by_text, parse_mention, detect_skill_hint
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import VALID_AGENTS, AGENT_KEYWORDS, LOGS_DIR
from task_domain import classify_task_domain, is_domain_compatible, _kw_match, _phrase_match
from task_load_balancer import get_queue_depth, get_all_agent_queue_depths

# Pattern: @agentname at start of string, optionally followed by whitespace
_MENTION_RE = re.compile(r"^@(" + "|".join(VALID_AGENTS) + r")\b\s*", re.IGNORECASE)


def parse_mention(text):
    """Parse @agent prefix from message text.

    Returns (agent, stripped_text) if @mention found, else (None, text).
    """
    m = _MENTION_RE.match(text)
    if m:
        agent = m.group(1).lower()
        stripped = text[m.end():].strip()
        return agent, stripped
    return None, text

# Disambiguation rules (first-match-wins) -- mirrors AGENTS.md hard rules
_DISAMBIGUATION = [
    ({"status", "implement"}, "kublai"),  # project status -> kublai (PM)
    ({"status", "progress"}, "kublai"),
    ({"status", "next"}, "kublai"),
    ({"status", "feature"}, "kublai"),
    ({"status", "project"}, "kublai"),
    # System assessment/triage -> kublai (2026-03-11 fix for case #12)
    # MUST come before bare {"status"} rule for ogedei
    ("system-wide status assessment", "kublai"),       # exact phrase -> squad lead
    ("system-wide status", "kublai"),                  # system status -> squad lead
    ("status assessment", "kublai"),                   # status assessment -> squad lead
    ("system assessment", "kublai"),                   # system assessment -> squad lead
    ({"prioritize", "backlog"}, "kublai"),             # backlog prioritization -> squad lead
    ({"fleet", "status"}, "kublai"),                   # fleet status -> squad lead
    ({"agent", "prioritize"}, "kublai"),               # agent prioritization -> squad lead
    ({"system-wide", "assess"}, "kublai"),             # system-wide assessment -> squad lead
    ({"assess", "all", "agent"}, "kublai"),            # assess all agents -> squad lead
    ({"kanban"}, "temujin"),              # kanban UI work -> dev (before bare status)
    # SUNO-CLONE ROUTING (2026-03-29)
    # YouTube music analysis → temujin runs /suno-clone skill
    ({"suno"}, "temujin"),                              # any suno mention -> dev
    ({"youtube", "analyze"}, "temujin"),                 # analyze youtube -> dev
    ({"youtube", "music"}, "temujin"),                   # youtube music -> dev
    ({"youtube", "style"}, "temujin"),                   # youtube style clone -> dev
    ({"youtube", "bpm"}, "temujin"),                     # youtube BPM analysis -> dev
    ({"song", "analyze"}, "temujin"),                    # song analysis -> dev
    ({"music", "clone"}, "temujin"),                     # music style clone -> dev
    ({"style", "reference", "card"}, "temujin"),         # style reference card -> dev
    ({"status"}, "ogedei"),               # bare ops status -> ogedei
    ({"research", "security"}, "jochi"),
    ({"research", "vulnerabilit"}, "jochi"),
    ({"research", "audit"}, "jochi"),
    ({"test", "write"}, "jochi"),
    ({"fix", "cron"}, "ogedei"),
    ({"fix", "backup"}, "ogedei"),
    ({"fix", "monitor"}, "ogedei"),
    # MONGKE RESEARCH PROTECTION (2026-03-10)
    # Prevent ops/analysis/dev tasks from routing to mongke through keyword overlap
    # Tasks must be EXPLICITLY research-oriented to route to mongke
    ({"investigate", "calendar"}, "ogedei"),       # calendar investigation -> ops (not research)
    ({"investigate", "cron"}, "ogedei"),           # cron investigation -> ops
    ({"investigate", "backup"}, "ogedei"),
    ({"investigate", "notification"}, "ogedei"),
    ({"enhance", "config"}, "jochi"),              # config enhancement -> analyst (not research)
    ({"enhance", "agent", "config"}, "jochi"),     # agent config enhancement -> analysis
    ({"fix", "config"}, "ogedei"),                 # config fixes -> ops
    ({"calendar", "notification"}, "ogedei"),      # calendar notifications -> ops
    ({"agent", "config", "enhancement"}, "jochi"), # config enhancement -> analyst
    ({"bidirectional", "linking"}, "temujin"),     # dev/testing work -> dev
    ({"test", "linking"}, "jochi"),                # linking tests -> analyst
    ({"verify", "linking"}, "jochi"),
    # Research protection before generic design+research rule (2026-03-09)
    # Use phrase-based matching to handle plurals and word order
    ("design research competitors", "mongke"),          # design research on competitors -> mongke
    ("design research market", "mongke"),               # design market research -> mongke
    ("design research trend", "mongke"),                # design trend research -> mongke
    ("design research pricing", "mongke"),              # design pricing research -> mongke
    ("design research pricing strategy", "mongke"),     # pricing strategy research -> mongke
    ("design research competitive analysis", "mongke"), # competitive analysis -> mongke
    ("research design competitors", "mongke"),          # alternate word order
    ("research design market", "mongke"),
    # Generic design tasks -> temujin (NOT research)
    ({"design", "research"}, "temujin"),  # design research (dev context, not market research)
    ({"create", "content"}, "chagatai"),    # "create content" -> writer
    ({"create", "blog"}, "chagatai"),
    ({"create", "article"}, "chagatai"),
    ({"configure", "cron"}, "ogedei"),      # ops configuration -> ogedei
    ({"configure", "backup"}, "ogedei"),
    ({"configure", "monitor"}, "ogedei"),
    ({"cleanup", "code"}, "temujin"),       # code cleanup -> dev
    ({"queue", "route"}, "kublai"),         # routing/queue -> squad lead
    ({"investigate", "error"}, "jochi"),     # error investigation -> analyst
    ({"investigate", "crash"}, "jochi"),
    ({"investigate", "fatal"}, "jochi"),
    ({"investigate", "spike"}, "jochi"),
    ({"investigate", "timeout"}, "jochi"),
    # OPS-ESCALATION GUARD (2026-03-12): Ops metrics that contain "failure"/"anomaly" must
    # route to ogedei BEFORE jochi's generic failure/anomaly keywords score higher.
    # Evidence: "SUSTAINED THROUGHPUT ANOMALY: HIGH_FAILURE_RATE" routed to jochi (wrong)
    # because jochi scored 2 ("anomaly" + "failure") vs ogedei's 1 ("failure").
    ({"throughput", "anomaly"}, "ogedei"),    # throughput anomaly = ops metric, not security
    ({"failure", "rate"}, "ogedei"),          # failure rate investigation -> ops (not security)
    ({"fleet", "failure"}, "ogedei"),         # fleet-wide failure = ops coordination
    ({"sustained", "anomaly"}, "ogedei"),     # sustained anomaly = ops monitoring pattern
    ({"investigate", "failure"}, "jochi"),
    ({"investigate", "failures"}, "jochi"),  # plural form for task failure investigations
    ({"investigate", "performance"}, "jochi"),  # perf analysis -> analyst
    ({"investigate", "score"}, "jochi"),
    ({"investigate", "cpu"}, "ogedei"),      # resource investigation -> ops
    ({"investigate", "memory"}, "ogedei"),
    ({"investigate", "disk"}, "ogedei"),
    ({"investigate", "health"}, "ogedei"),
    ({"investigate", "usage"}, "ogedei"),
    ({"investigate", "queue"}, "ogedei"),   # queue/pipeline ops -> ogedei
    ({"investigate", "pipeline"}, "ogedei"),
    ({"investigate", "cron"}, "ogedei"),
    ({"investigate", "process"}, "ogedei"),
    ({"triage", "stall"}, "kublai"),        # triage/coordination -> squad lead
    ({"triage", "agent"}, "kublai"),
    ({"triage", "backlog"}, "kublai"),
    ({"tock", "assessment"}, "kublai"),     # tock assessments -> squad lead
    ({"tock", "critical"}, "kublai"),
    ({"audit", "deploy"}, "jochi"),         # audit always -> jochi even if deploy
    ({"audit", "pipeline"}, "jochi"),
    ({"investigate", "unauthorized"}, "jochi"),  # security investigation -> analyst
    ({"investigate", "message"}, "temujin"),     # messaging system issues -> dev
    ({"investigate", "low", "performance"}, "jochi"),  # perf scoring -> analyst
    ({"investigate", "score"}, "jochi"),    # score investigation -> analyst (explicit)
    ({"routing", "audit"}, "kublai"),       # routing audit self-tasks -> squad lead
    ({"review", "routing"}, "kublai"),      # review routing -> squad lead
    ({"queue", "backlog"}, "kublai"),       # queue backlog triage -> squad lead
    ({"process", "queue"}, "kublai"),       # process queue -> squad lead
    ({"create", "soul"}, "chagatai"),       # persona/identity content -> writer
    ({"create", "identity"}, "chagatai"),
    ({"create", "persona"}, "chagatai"),
    ({"update", "persona"}, "chagatai"),    # persona updates -> writer
    ({"create", "skill", "instruction"}, "chagatai"),  # skill docs/instructions -> writer
    ({"enhance", "presentation"}, "chagatai"),         # presentation/UI copy -> writer
    ({"draft", "document"}, "chagatai"),              # drafting docs -> writer
    ({"draft", "blog"}, "chagatai"),
    ({"draft", "guide"}, "chagatai"),
    ({"draft", "proposal"}, "chagatai"),
    ({"write", "report"}, "chagatai"),                # written reports -> writer (vs generate report -> analyst)
    ({"write", "guide"}, "chagatai"),
    ({"write", "tutorial"}, "chagatai"),
    ({"write", "summary"}, "chagatai"),
    ({"summarize", "findings"}, "chagatai"),          # summarization -> writer
    ({"summarize", "research"}, "chagatai"),
    ({"explain", "architecture"}, "chagatai"),        # explanatory docs -> writer
    ({"explain", "system"}, "chagatai"),
    ({"update", "documentation"}, "chagatai"),        # doc maintenance -> writer
    ({"update", "docs"}, "chagatai"),
    ({"update", "readme"}, "chagatai"),
    ({"release", "notes"}, "chagatai"),               # release notes -> writer
    ({"create", "tutorial"}, "chagatai"),              # tutorial creation -> writer
    ({"create", "guide"}, "chagatai"),                 # guide creation -> writer
    ({"create", "documentation"}, "chagatai"),         # documentation creation -> writer
    ({"create", "docs"}, "chagatai"),
    ({"create", "summary"}, "chagatai"),               # summary creation -> writer
    ({"create", "outline"}, "chagatai"),
    # Additional disambiguation for common patterns
    ({"calendar", "implement"}, "temujin"),            # calendar feature dev -> temujin
    ({"calendar", "build"}, "temujin"),
    ({"generate", "report"}, "jochi"),                 # report generation -> analyst
    ({"report", "generate"}, "jochi"),
    ({"mvp", "implement"}, "temujin"),                 # MVP execution -> temujin
    ({"mvp", "build"}, "temujin"),
    ({"subscription", "implement"}, "temujin"),        # subscription feature -> temujin
    ({"stripe", "implement"}, "temujin"),
    ({"billing", "implement"}, "temujin"),
    ({"oauth", "implement"}, "temujin"),
    ({"oauth", "setup"}, "temujin"),
    # Evaluation of implementation features -> temujin (not mongke who has "evaluate")
    ({"evaluate", "integrate"}, "temujin"),            # evaluate integration -> dev
    ({"evaluate", "integration"}, "temujin"),          # evaluate integration -> dev
    ({"evaluate", "kanban"}, "temujin"),               # evaluate kanban -> dev
    ({"evaluate", "implement"}, "temujin"),            # evaluate implementation -> dev
    ({"evaluate", "implementation"}, "temujin"),       # evaluate implementation (noun) -> dev
    ({"fix", "401"}, "ogedei"),                        # auth error fix -> ogedei
    ({"fix", "api"}, "ogedei"),                        # API error fix -> ogedei
    ({"fix", "model"}, "ogedei"),                      # model config fix -> ogedei
    ({"model", "error"}, "ogedei"),
    # AI/LLM model research routes to mongke (2026-03-11)
    # Must be before generic {"investigate", "model"} rule
    ({"investigate", "model", "capabilities"}, "mongke"),   # model capabilities research
    ({"investigate", "ai", "model"}, "mongke"),            # AI model investigation
    ({"investigate", "llm"}, "mongke"),                   # LLM investigation
    ({"investigate", "language", "model"}, "mongke"),      # language model research
    ({"investigate", "embedding"}, "mongke"),             # embedding research
    ({"investigate", "model"}, "ogedei"),                 # model config investigation -> ops
    ({"domain", "generate"}, "ogedei"),                # domain generation -> ogedei
    ({"deploy", "railway"}, "ogedei"),                 # railway deploy -> ogedei
    ({"vercel", "deploy"}, "ogedei"),
    ({"market", "research"}, "mongke"),                # market research -> mongke
    ({"competitor", "research"}, "mongke"),
    ({"competitor", "analysis"}, "mongke"),
    # Visual content creation -> chagatai (not temujin who has "create")
    ({"create", "avatar"}, "chagatai"),                # avatar creation -> writer
    ({"create", "visual"}, "chagatai"),                # visual content -> writer
    ({"create", "image"}, "chagatai"),                 # image creation -> writer
    ({"create", "graphic"}, "chagatai"),               # graphics -> writer
    ({"photorealistic"}, "chagatai"),                  # photorealistic content -> writer
    # Code modification with review -> temujin (not jochi who has "review")
    ({"add", "review", "audit"}, "temujin"),           # add review feature -> dev
    ({"modify", "review"}, "temujin"),                 # modify review system -> dev
    ({"implement", "review"}, "temujin"),              # implement review feature -> dev
    # Review disambiguation (2026-03-11) — fix keyword routing drift
    # Most "review" tasks should go to jochi, EXCEPT for implementation/dev contexts
    ({"3-hour", "review"}, "temujin"),                 # 3-hour code review -> dev (not analyst)
    ({"code", "review"}, "temujin"),                   # code review -> dev (not analyst)
    ({"architecture", "review"}, "temujin"),           # architecture review -> dev
    ({"design", "review"}, "temujin"),                 # design review -> dev
    ({"implementation", "review"}, "temujin"),         # implementation review -> dev
    ({"pull", "request", "review"}, "temujin"),        # PR review -> dev
    ({"pr", "review"}, "temujin"),                     # PR review -> dev
    # Jochi review keywords are for audits, assessments, security reviews, etc.
    ({"audit"}, "jochi"),                              # audit -> analyst (security/quality audit)
    ({"security", "review"}, "jochi"),                 # security review -> analyst
    ({"performance", "review"}, "jochi"),              # performance review -> analyst
    ({"quality", "review"}, "jochi"),                  # quality review -> analyst
    ({"routing", "review"}, "kublai"),                 # routing review -> squad lead
    # Ops service restart/dispatch -> ogedei (2026-03-11 fix for case #5)
    ({"restart", "service"}, "ogedei"),                # service restart -> ops
    ({"service", "down"}, "ogedei"),                   # service down -> ops
    ({"redis", "restart"}, "ogedei"),                  # redis restart -> ops
    ({"redis", "down"}, "ogedei"),                     # redis down -> ops
    # System assessment/triage -> kublai (2026-03-11 fix for case #12)
    # Must come BEFORE generic status/assessment rules for ogedei
    ("system-wide status assessment", "kublai"),       # exact phrase -> squad lead
    ("system-wide status", "kublai"),                  # system status -> squad lead
    ("status assessment", "kublai"),                   # status assessment -> squad lead
    ("system assessment", "kublai"),                   # system assessment -> squad lead
    ({"prioritize", "backlog"}, "kublai"),             # backlog prioritization -> squad lead
    ({"fleet", "status"}, "kublai"),                   # fleet status -> squad lead
    ({"agent", "prioritize"}, "kublai"),               # agent prioritization -> squad lead
    ({"system-wide", "assess"}, "kublai"),             # system-wide assessment -> squad lead
    ({"assess", "all", "agent"}, "kublai"),            # assess all agents -> squad lead
    # === PARSE PROJECT ROUTING (2026-03-23) ===
    # Parse projects route by project + task-type keyword combination
    ({"parsethe", "deploy"}, "ogedei"),
    ({"parsethe", "monitor"}, "ogedei"),
    ({"parsethe", "health"}, "ogedei"),
    ({"parsethe", "restart"}, "ogedei"),
    ({"parsethe", "railway"}, "ogedei"),
    ({"parsethe", "test"}, "jochi"),
    ({"parsethe", "security"}, "jochi"),
    ({"parsethe", "audit"}, "jochi"),
    ({"parsethe", "review"}, "jochi"),
    ({"parsethe", "research"}, "mongke"),
    ({"parsethe", "blog"}, "chagatai"),
    ({"parsethe", "document"}, "chagatai"),
    ({"parsethe"}, "temujin"),           # default: dev work
    ("parsethe.media", "temujin"),
    ("parse platform", "temujin"),
    ("parse saas", "temujin"),
    # === PARSETHIS.AI PROJECT ROUTING (2026-03-23) ===
    # parsethis.ai routes by project + task-type keyword combination
    ({"parsethis", "deploy"}, "ogedei"),
    ({"parsethis", "railway"}, "ogedei"),
    ({"parsethis", "health"}, "ogedei"),
    ({"parsethis", "monitor"}, "ogedei"),
    ({"parsethis", "restart"}, "ogedei"),
    ({"parsethis", "test"}, "jochi"),
    ({"parsethis", "security"}, "jochi"),
    ({"parsethis", "audit"}, "jochi"),
    ({"parsethis"}, "temujin"),           # default: dev work
    ("parsethis.ai", "temujin"),
    ({"parse-for-agents", "deploy"}, "ogedei"),
    ({"parse-for-agents", "docker"}, "ogedei"),
    ({"parse-for-agents", "railway"}, "ogedei"),
    ({"parse-for-agents", "test"}, "jochi"),
    ({"parse-for-agents", "security"}, "jochi"),
    ({"parse-for-agents", "audit"}, "jochi"),
    ({"parse-for-agents"}, "temujin"),   # default: dev work
    ("parse for agents", "temujin"),
    ("parse agents api", "temujin"),
    # Design/architecture tasks -> temujin (not mongke)
    ({"design", "schema"}, "temujin"),                 # schema design -> dev
    ({"design", "neo4j"}, "temujin"),                  # neo4j design -> dev
    ({"brainstorm", "schema"}, "temujin"),             # schema brainstorm -> dev
    ({"brainstorm", "neo4j"}, "temujin"),              # neo4j brainstorm -> dev
    ({"proposal", "voting"}, "temujin"),               # voting system design -> dev
    ({"voting", "system"}, "temujin"),                 # voting system -> dev
    # === CHAGATAI ROUTING GUIDE INTEGRATION ===
    # Reference: docs/chagatai-routing-guide.md
    # Rule C16: chagatai accepts tasks where PRIMARY OUTPUT is prose/content
    # These rules route AWAY from chagatai when primary output is NOT prose
    #
    # Common misroutes (from routing guide "Common Misroutes and Corrections"):
    ({"create", "authentication"}, "temujin"),         # auth system -> dev (not writer)
    ({"create", "auth", "system"}, "temujin"),
    ({"create", "user", "system"}, "temujin"),         # user system -> dev
    ({"create", "feature"}, "temujin"),                # feature creation -> dev
    ({"create", "implementation"}, "temujin"),         # implementation -> dev
    ({"write", "tests"}, "jochi"),                     # write tests -> analyst (not writer)
    ({"write", "test"}, "jochi"),
    ({"write", "unit test"}, "jochi"),
    ({"write", "integration test"}, "jochi"),
    ({"research", "competitor", "pricing"}, "mongke"), # competitor pricing -> researcher
    ({"update", "deployment", "config"}, "ogedei"),    # deployment config -> ops
    ({"update", "deploy", "config"}, "ogedei"),
    ({"fix", "email", "template"}, "temujin"),         # fix template -> dev (even if HTML)
    ({"fix", "template"}, "temujin"),                  # template fix -> dev
    ({"design", "api", "endpoint"}, "temujin"),        # API design -> dev
    ({"design", "new", "api"}, "temujin"),
    ({"design", "endpoint"}, "temujin"),
    # Keyword ambiguity resolution (Primary Output Test):
    # "create" -> chagatai ONLY when content/blog/guide; else -> temujin
    ({"create", "system"}, "temujin"),                 # system creation -> dev
    ({"create", "service"}, "temujin"),                # service creation -> dev
    ({"create", "module"}, "temujin"),                 # module creation -> dev
    ({"create", "function"}, "temujin"),               # function creation -> dev
    ({"create", "component"}, "temujin"),              # component creation -> dev
    ({"create", "api"}, "temujin"),                    # API creation -> dev
    ({"create", "endpoint"}, "temujin"),               # endpoint creation -> dev
    # "update" -> chagatai ONLY when docs/README; else -> temujin/ogedei
    ({"update", "code"}, "temujin"),                   # code update -> dev
    ({"update", "config", "file"}, "ogedei"),          # config update -> ops
    ({"update", "system"}, "temujin"),                 # system update -> dev
    ({"update", "feature"}, "temujin"),                # feature update -> dev
    # "write" -> chagatai ONLY when documentation/post; else -> temujin
    ({"write", "code"}, "temujin"),                    # code writing -> dev
    ({"write", "script"}, "temujin"),                  # script writing -> dev
    ({"write", "function"}, "temujin"),                # function writing -> dev
    ({"write", "implementation"}, "temujin"),          # implementation -> dev
    # "explain" -> chagatai ONLY when in docs/guide context; code explanation -> temujin
    ({"explain", "code"}, "temujin"),                  # explain code -> dev
    ({"explain", "how", "implement"}, "temujin"),      # implementation explanation -> dev
    ({"explain", "bug"}, "temujin"),                   # bug explanation -> dev
    # Special cases from routing guide:
    ({"research", "and", "write", "blog"}, "chagatai"), # research+write blog -> writer
    ({"research", "topic", "write"}, "chagatai"),      # research for content -> writer
    ({"update", "code", "to", "match"}, "temujin"),    # code matches docs -> dev
    ({"create", "slide", "deck"}, "chagatai"),         # slide deck content -> writer
    ({"implement", "presentation"}, "temujin"),        # presentation feature -> dev
    # Research protection rules (2026-03-09): Keep pure research with mongke
    # These rules prevent research tasks from being misrouted to temujin/chagatai
    ({"research", "competitor"}, "mongke"),            # competitor research -> mongke
    ({"research", "market"}, "mongke"),                # market research -> mongke
    ({"research", "trend"}, "mongke"),                 # trend research -> mongke
    ({"research", "pricing"}, "mongke"),               # pricing research -> mongke
    ({"research", "ecosystem"}, "mongke"),             # ecosystem research -> mongke
    ({"discover", "competitor"}, "mongke"),            # competitor discovery -> mongke
    ({"discover", "market"}, "mongke"),                # market discovery -> mongke
    ({"market", "analysis"}, "mongke"),                # market analysis -> mongke
    ({"competitor", "analysis"}, "mongke"),            # competitor analysis -> mongke
    ({"benchmark", "competitor"}, "mongke"),           # competitive benchmarking -> mongke
    ({"landscape", "analysis"}, "mongke"),             # landscape analysis -> mongke
    ({"literature", "review"}, "mongke"),              # literature review -> mongke
    ({"source", "triangulation"}, "mongke"),           # source triangulation -> mongke
    # JOCHI KEYWORD DISENGUATION (2026-03-11)
    # "analyze" keyword is too broad — add domain-specific rules
    ({"analyze", "competitor"}, "mongke"),             # competitor analysis -> researcher
    ({"analyze", "market"}, "mongke"),                 # market analysis -> researcher
    ({"analyze", "pricing"}, "mongke"),                # pricing analysis -> researcher
    ({"analyze", "trend"}, "mongke"),                  # trend analysis -> researcher
    ({"analyze", "code"}, "temujin"),                  # code analysis -> dev
    ({"analyze", "architecture"}, "temujin"),          # architecture analysis -> dev
    ({"analyze", "design"}, "temujin"),                # design analysis -> dev
    ({"analyze", "performance"}, "jochi"),             # performance analysis -> analyst (explicit)
    ({"analyze", "security"}, "jochi"),                # security analysis -> analyst (explicit)
    ({"analyze", "vulnerability"}, "jochi"),           # vulnerability analysis -> analyst
    ({"analyze", "routing"}, "kublai"),                # routing analysis -> squad lead
    ({"analyze", "queue"}, "kublai"),                  # queue analysis -> squad lead
    ({"analyze", "pipeline"}, "kublai"),               # pipeline analysis -> squad lead
    # "check" keyword is too broad — add domain-specific rules
    ({"check", "status"}, "ogedei"),                   # status check -> ops
    ({"check", "health"}, "ogedei"),                   # health check -> ops
    ({"check", "cron"}, "ogedei"),                     # cron check -> ops
    ({"check", "deploy"}, "ogedei"),                   # deployment check -> ops
    ({"check", "test"}, "jochi"),                      # test check -> analyst
    ({"check", "security"}, "jochi"),                  # security check -> analyst
    ({"check", "vulnerability"}, "jochi"),            # vulnerability check -> analyst
    ("check vulnerabilities", "jochi"),                # vulnerability checks (plural) -> analyst
    # "triage" keyword disambiguation
    ({"triage", "backlog"}, "kublai"),                # backlog triage -> squad lead (exists, re-ordered for clarity)
    ({"triage", "agent"}, "kublai"),                  # agent triage -> squad lead (exists)
    ({"triage", "task"}, "kublai"),                   # task triage -> squad lead
    ("triage stalled", "kublai"),                     # stalled tasks triage -> squad lead (past tense)
    # MONGKE_RESEARCH_PROTECTION (2026-03-11) — prevent non-research tasks from routing to mongke
    # These rules fix EXECUTING_NO_OUTPUT anomalies caused by domain misalignment
    ("investigate calendar", "ogedei"),                # calendar investigation -> ops, not research
    ("investigate cron", "ogedei"),                   # cron investigation -> ops
    ("investigate backup", "ogedei"),                 # backup investigation -> ops
    ("investigate notification", "ogedei"),           # notification investigation -> ops
    ("enhance config", "jochi"),                      # config enhancement -> analyst, not research
    ("agent config enhancement", "jochi"),            # agent config -> analyst
    ("calendar notification", "ogedei"),              # calendar notifications -> ops
    ("bidirectional linking", "temujin"),             # bidirectional linking -> dev, not research
]


def route_by_text(text):
    """Keyword routing for programmatic task creation with disambiguation.

    QUEUE-AWARE TIEBREAKING (2026-03-11): When multiple agents have equal
    keyword scores, prefer the agent with lower queue depth. This prevents
    "sticky routing" to temujin when keyword matching is ambiguous.

    QUEUE-AWARE PRIMARY SELECTION (2026-03-12): Before returning the primary
    agent, check if it's significantly overloaded compared to alternatives.
    If primary queue >= 3 and another agent has queue <= 1, use the lower-queue
    agent instead. This prevents tasks from piling up on busy agents while
    idle agents sit unused. This check now applies EVEN to disambiguation rules.
    """
    text_lower = text.lower()

    # Collect all agents with their scores (needed for queue-aware redirect even with disambiguation)
    scores = {}
    for agent, keywords in AGENT_KEYWORDS.items():
        scores[agent] = sum(1 for kw in keywords if _kw_match(kw, text_lower))

    # Find best score (for queue-aware logic)
    best_score = max(scores.values()) if scores else 0

    # Check disambiguation rules first (first-match-wins)
    # But DON'T return immediately — apply queue-aware check first
    best = None
    disambiguation_matched = False
    for rule, target in _DISAMBIGUATION:
        # Handle string-based phrase rules (2026-03-09)
        # String rules use phrase matching (words can be separated), set rules are keyword intersections
        if isinstance(rule, str):
            if _phrase_match(rule, text_lower):
                best = target
                disambiguation_matched = True
                break
        elif isinstance(rule, set):
            if all(_kw_match(kw, text_lower) for kw in rule):
                best = target
                disambiguation_matched = True
                break

    # If no disambiguation match, use keyword scoring
    if best is None:
        if best_score > 0:
            tied_agents = [agent for agent, score in scores.items() if score == best_score]
            if len(tied_agents) > 1:
                # Break tie by queue depth (lowest first)
                best = min(tied_agents, key=lambda a: get_queue_depth(a))
                # Log tiebreak for audit
                print(f"QUEUE-AWARE TIEBREAK: {len(tied_agents)} agents tied with score={best_score} "
                      f"({', '.join(tied_agents)}), selected {best} (lowest queue)")
            else:
                best = tied_agents[0]
        else:
            # No keyword matches — use queue depth to decide
            best = min(scores.keys(), key=lambda a: get_queue_depth(a))
            print(f"NO-KEYWORD-FALLBACK: No keyword matches, selected {best} (lowest queue)")

    # Apply Primary Output Test for chagatai (Rule C16 compliance)
    # Reference: docs/chagatai-routing-guide.md
    if best == "chagatai":
        primary_output = _primary_output_test(text_lower)
        if primary_output and primary_output != "prose":
            # Route to the agent matching the actual primary output
            best = _PRIMARY_OUTPUT_ROUTE_MAP.get(primary_output, best)

    # QUEUE-AWARE PRIMARY SELECTION (2026-03-12): If the selected primary is
    # significantly overloaded but another agent has much lower queue, use the
    # lower-queue agent instead. This prevents the "sticky routing" problem where
    # tasks pile up on busy agents while idle agents sit unused.
    # This now applies to disambiguation matches too!
    # Threshold: primary >= 3 tasks AND another agent <= 1 task
    primary_depth = get_queue_depth(best)
    if primary_depth >= 3:
        # Find agents with significantly lower queue depth
        all_depths = get_all_agent_queue_depths()
        lower_queue_agents = [(a, d) for a, d in all_depths.items() if d <= 1 and a != best]
        # DOMAIN-AWARE FILTERING (2026-03-12): When disambiguation explicitly matched
        # a target agent, restrict redirect candidates to domain-compatible agents only.
        # Without this, a research task → mongke can redirect to temujin/ogedei just
        # because they have empty queues, causing domain misalignment and task failures.
        if disambiguation_matched and lower_queue_agents:
            task_domain = classify_task_domain(text)
            domain_filtered = [(a, d) for a, d in lower_queue_agents
                               if is_domain_compatible(task_domain, a)]
            # Only apply domain filter if at least one candidate survives;
            # otherwise keep the unfiltered list as a safety fallback.
            if domain_filtered:
                lower_queue_agents = domain_filtered

        if lower_queue_agents:
            # Among low-queue agents, prefer one with decent keyword match (if any)
            # Otherwise, just use the one with lowest queue
            best_alt, best_alt_depth = min(lower_queue_agents, key=lambda x: x[1])
            # Check if alternate has at least some keyword relevance
            alt_score = scores.get(best_alt, 0)

            # Redirect if:
            # 1. Disambiguation matched (strong signal, allow redirect to domain-compatible idle agent), OR
            # 2. Alternate has keyword relevance, OR
            # 3. Primary has only weak keyword match (best_score == 1)
            should_redirect = (disambiguation_matched or
                              alt_score > 0 or
                              best_score == 1)

            if should_redirect:
                source_note = " (disambiguation)" if disambiguation_matched else ""
                print(f"QUEUE-AWARE PRIMARY REDIRECT{source_note}: {best} (queue={primary_depth}, score={best_score}) "
                      f"-> {best_alt} (queue={best_alt_depth}, score={alt_score})")
                best = best_alt

    return best


# Primary Output Test - determines what type of deliverable a task produces
# Reference: docs/chagatai-routing-guide.md "When in Doubt: Primary Output Test"
_PRIMARY_OUTPUT_PATTERNS = {
    # Prose indicators (chagatai domain)
    "prose": [
        "blog", "article", "documentation", "docs", "readme", "changelog",
        "marketing", "copy", "announcement", "social", "twitter", "linkedin",
        "guide", "tutorial", "draft", "outline", "proposal content",
        "release notes", "memo", "narrative", "summary", "summarize"
    ],
    # Code indicators (temujin domain)
    "code": [
        "implement", "build", "code", "function", "api", "endpoint", "service",
        "module", "component", "feature", "bug", "fix", "refactor", "script",
        "system", "authentication", "auth", "database", "schema", "migration",
        "integration", "sdk", "frontend", "backend", "ui component"
    ],
    # Research indicators (mongke domain)
    "research": [
        "research", "discover", "competitor", "market", "trend", "study",
        "benchmark", "survey", "literature", "paper", "citation", "findings",
        "sources", "evidence", "investigate trend", "market analysis",
        # AI/LLM research (2026-03-11)
        "llm", "model comparison", "ai model", "provider comparison", "llm evaluation"
    ],
    # Analysis indicators (jochi domain)
    "analysis": [
        "analyze", "audit", "review", "security", "vulnerability", "test",
        "verify", "validate", "performance", "score", "compliance", "check"
    ],
    # Operations indicators (ogedei domain)
    "operations": [
        "deploy", "monitor", "restart", "backup", "alert", "health", "cron",
        "incident", "status", "queue", "pipeline", "infrastructure", "server"
    ],
}

_PRIMARY_OUTPUT_ROUTE_MAP = {
    "prose": "chagatai",
    "code": "temujin",
    "research": "mongke",
    "analysis": "jochi",
    "operations": "ogedei",
}


def _primary_output_test(text_lower):
    """Determine the primary output type of a task.

    Implements the Primary Output Test from docs/chagatai-routing-guide.md.
    Returns: "prose", "code", "research", "analysis", "operations", or None
    """
    scores = {}
    for output_type, patterns in _PRIMARY_OUTPUT_PATTERNS.items():
        score = sum(1 for p in patterns if p in text_lower)
        if score > 0:
            scores[output_type] = score

    if not scores:
        return None

    # Return the output type with highest score
    return max(scores.items(), key=lambda x: x[1])[0]



# --- KUBLAI SELF-ABSORPTION ---
# Kublai (router) can absorb certain coordination/analysis tasks when its queue is high
# but it has been idle. This prevents the "router cannot route to itself" failure mode.
KUBLAI_SELF_ABSORB_THRESHOLD = 20      # Trigger when kublai queue >= this
KUBLAI_SELF_ABSORB_IDLE_MINUTES = 30   # No kublai dispatch in this many minutes
KUBLAI_SELF_ABSORB_KEYWORDS = [
    # Core coordination keywords (from AGENT_KEYWORDS["kublai"])
    "triage", "coordinate", "prioritize", "system-wide", "assessment", "status assessment",
    "agent status", "backlog", "routing", "dispatch", "workload",
    # Expanded analysis keywords for self-absorption
    "queue analysis", "queue depth", "throughput", "pipeline health", "bottleneck",
    "agent utilization", "load balance", "routing analysis", "coordination",
    "performance review", "system health", "fleet status", "agent review",
]
_KUBLAI_LAST_DISPATCH_FILE = f"{LOGS_DIR}/kublai_last_dispatch.txt"


def _update_kublai_dispatch_timestamp():
    """Record when kublai last received a task."""
    try:
        with open(_KUBLAI_LAST_DISPATCH_FILE, 'w') as f:
            f.write(str(datetime.now().timestamp()))
    except Exception:
        pass  # Non-critical, don't fail routing


def _get_kublai_idle_minutes():
    """Return minutes since kublai last received a task. Returns 999 if no record."""
    try:
        if not os.path.exists(_KUBLAI_LAST_DISPATCH_FILE):
            return 999  # No record = consider idle
        with open(_KUBLAI_LAST_DISPATCH_FILE, 'r') as f:
            last_ts = float(f.read().strip())
        idle_seconds = datetime.now().timestamp() - last_ts
        return idle_seconds / 60
    except Exception:
        return 999  # Error = consider idle


def should_kublai_self_absorb(title: str) -> bool:
    """Check if kublai should absorb this task based on queue depth and idle time.

    Returns True if:
    1. Kublai queue >= KUBLAI_SELF_ABSORB_THRESHOLD (20)
    2. Kublai idle for >= KUBLAI_SELF_ABSORB_IDLE_MINUTES (30)
    3. Task title contains self-absorption keywords
    """
    kublai_depth = get_queue_depth("kublai")
    if kublai_depth < KUBLAI_SELF_ABSORB_THRESHOLD:
        return False

    idle_minutes = _get_kublai_idle_minutes()
    if idle_minutes < KUBLAI_SELF_ABSORB_IDLE_MINUTES:
        return False

    title_lower = title.lower()
    return any(kw in title_lower for kw in KUBLAI_SELF_ABSORB_KEYWORDS)


# --- SKILL-AGENT COMPATIBILITY ---
# Skills that belong exclusively to one agent. Prevents misroutes like
# /horde-brainstorming going to chagatai (writer) instead of temujin (dev).
# NOTE: /horde-implement removed 2026-03-08 to allow load balancing to ogedei.
# Implementation tasks will still route to temujin via keywords, but can be
# load-balanced to ogedei when temujin is overloaded.
_SKILL_OWNER = {
    "/horde-brainstorming": "temujin",
    "/horde-plan": "temujin",
    "/golden-horde": "temujin",
    "/horde-debug": "temujin",
    # /systematic-debugging is shared: temujin (dev debugging) AND jochi (analysis)
    # Do NOT add it here — it would force all debugging to one agent.
    "/dev-deploy": "temujin",
    "/horde-learn": "mongke",
    "/scrapling-research": "mongke",
    "/content-research-writer": "chagatai",
    "/changelog-generator": "chagatai",
    # Kurultai health skill belongs to ogedei (2026-03-09 fix)
    "/kurultai-health": "ogedei",
    # Code review and test generation belong to jochi (2026-03-09 fix)
    "/code-reviewer": "jochi",
    "/generate-tests": "jochi",
    # Suno-clone requires local audio analysis venv — only temujin can run it
    "/suno-clone": "temujin",
}

# --- SKILL HINT DETECTION ---
# Auto-detect the best horde/domain skill for the task
SKILL_HINTS = {
    ("temujin", "design"):     "/horde-brainstorming",
    ("temujin", "architect"):  "/horde-brainstorming",
    ("temujin", "brainstorm"): "/horde-brainstorming",
    ("temujin", "plan"):       "/horde-brainstorming",
    ("temujin", "protocol"):   "/horde-brainstorming",
    ("temujin", "payment"):    "/horde-brainstorming",
    ("temujin", "implement"):  "/horde-implement",
    ("temujin", "build"):      "/horde-implement",
    ("temujin", "scaffold"):   "/horde-implement",
    ("temujin", "finish"):     "/horde-implement",
    ("temujin", "complete"):   "/horde-implement",
    ("temujin", "debug"):      "/systematic-debugging",
    ("temujin", "broken"):     "/systematic-debugging",
    ("temujin", "error"):      "/systematic-debugging",
    ("temujin", "crash"):      "/systematic-debugging",
    ("temujin", "deploy"):     "/dev-deploy",
    ("temujin", "railway"):    "/dev-deploy",
    ("temujin", "suno"):       "/suno-clone",
    ("temujin", "youtube"):    "/suno-clone",
    ("temujin", "music"):      "/suno-clone",
    ("temujin", "bpm"):        "/suno-clone",
    ("mongke", "research"):    "/horde-learn",
    ("mongke", "investigate"): "/horde-learn",
    ("mongke", "discover"):    "/horde-learn",
    ("mongke", "explore"):     "/horde-learn",
    ("mongke", "scrape"):      "/scrapling-research",
    ("mongke", "crawl"):       "/scrapling-research",
    ("chagatai", "blog"):      "/content-research-writer",
    ("chagatai", "article"):   "/content-research-writer",
    ("chagatai", "content"):   "/content-research-writer",
    ("chagatai", "changelog"): "/changelog-generator",
    ("chagatai", "release"):   "/changelog-generator",
    ("jochi", "debug"):        "/systematic-debugging",
    ("jochi", "bug"):          "/systematic-debugging",
    ("jochi", "error"):        "/systematic-debugging",
    ("jochi", "review"):       "/code-reviewer",
    ("jochi", "audit"):        "/code-reviewer",
    ("jochi", "security"):     "/code-reviewer",
    ("ogedei", "health"):      "/kurultai-health",
    ("ogedei", "diagnostic"):  "/kurultai-health",
    ("ogedei", "deploy"):      "/dev-deploy",
    ("ogedei", "railway"):     "/dev-deploy",
    ("ogedei", "cron"):        "/kurultai-health",
    ("ogedei", "alert"):       "/kurultai-health",
    ("ogedei", "restart"):     "/kurultai-health",
    ("ogedei", "monitor"):     "/kurultai-health",
    ("jochi", "investigate"):  "/systematic-debugging",
    ("jochi", "spike"):        "/systematic-debugging",
    ("jochi", "failure"):      "/systematic-debugging",
    ("jochi", "test"):         "/generate-tests",
    ("temujin", "fix"):        "/systematic-debugging",
    ("temujin", "bug"):        "/systematic-debugging",
    ("temujin", "refactor"):   "/code-reviewer",
    ("chagatai", "document"):  "/content-research-writer",
    ("chagatai", "write"):     "/content-research-writer",
    ("chagatai", "social"):    "/content-research-writer",
    ("chagatai", "marketing"): "/content-research-writer",
    ("chagatai", "persona"):   "/content-research-writer",
    ("chagatai", "identity"):  "/content-research-writer",
    ("chagatai", "create"):    "/content-research-writer",
    ("chagatai", "update"):    "/content-research-writer",
    ("temujin", "frontend"):   "/senior-frontend",
    ("temujin", "ui"):         "/senior-frontend",
    ("temujin", "react"):      "/senior-frontend",
    ("temujin", "kanban"):     "/senior-frontend",
    ("temujin", "component"):  "/senior-frontend",
    ("temujin", "enhance"):    "/senior-fullstack",
    ("temujin", "notification"): "/horde-brainstorming",
    ("temujin", "sort"):       "/senior-frontend",
    ("temujin", "configure"):  "/horde-implement",
    ("temujin", "signal"):     "/horde-implement",
    ("jochi", "performance"):  "/systematic-debugging",
    ("jochi", "stalled"):      "/systematic-debugging",
    ("jochi", "triage"):       "/systematic-debugging",
    ("jochi", "anomaly"):      "/systematic-debugging",
    ("jochi", "unauthorized"): "/code-reviewer",
    ("jochi", "compliance"):   "/code-reviewer",
    # Additional temujin skills
    ("temujin", "calendar"):     "/horde-implement",
    ("temujin", "mvp"):          "/horde-implement",
    ("temujin", "worker"):       "/horde-implement",
    ("temujin", "evaluator"):    "/horde-implement",
    ("temujin", "bullmq"):       "/horde-implement",
    ("temujin", "api"):          "/senior-backend",
    ("temujin", "backend"):      "/senior-backend",
    ("temujin", "endpoint"):     "/senior-backend",
    ("temujin", "billing"):      "/horde-brainstorming",
    ("temujin", "subscription"): "/horde-brainstorming",
    ("temujin", "oauth"):        "/horde-brainstorming",
    ("temujin", "auth"):         "/horde-brainstorming",
    ("temujin", "integration"):  "/horde-implement",
    ("temujin", "sdk"):          "/horde-implement",
    # Additional mongke skills
    ("mongke", "market"):        "/horde-learn",
    ("mongke", "competitor"):    "/horde-learn",
    ("mongke", "benchmark"):     "/horde-learn",
    ("mongke", "analyze"):       "/horde-learn",
    ("mongke", "study"):         "/horde-learn",
    ("mongke", "source"):        "/horde-learn",
    # Additional ogedei skills
    ("ogedei", "investigate"):   "/kurultai-health",
    ("ogedei", "report"):        "/kurultai-health",
    ("ogedei", "failure"):       "/kurultai-health",
    ("ogedei", "error"):         "/kurultai-health",
    ("ogedei", "generate"):      "/dev-deploy",
    ("ogedei", "domain"):        "/dev-deploy",
    ("ogedei", "vercel"):        "/dev-deploy",
}


# Project-specific context skills (checked FIRST, override methodology hints)
# These provide codebase knowledge rather than workflow methodology.
_PROJECT_HINTS = {
    "parsethe.media": "/parsethe-media",
    "parsethe": "/parsethe-media",
    "parse media": "/parsethe-media",
    "parse platform": "/parsethe-media",
    "parse saas": "/parsethe-media",
    "parse-for-agents": "/parse-for-agents",
    "parse agents api": "/parse-for-agents",
}


def detect_skill_hint(agent, text):
    """Auto-detect the best skill for this agent + task combination."""
    text_lower = text.lower()
    # Check project-specific context skills first (override methodology hints)
    for keyword, skill in _PROJECT_HINTS.items():
        if _kw_match(keyword, text_lower):
            return skill
    # Then check agent+keyword methodology hints
    for (hint_agent, keyword), skill in SKILL_HINTS.items():
        if agent == hint_agent and _kw_match(keyword, text_lower):
            return skill
    return None


# ---------------------------------------------------------------------------
# KB hint detection — auto-detect relevant knowledge base doc
# ---------------------------------------------------------------------------

KB_HINTS = {
    "neo4j": "neo4j-schema.md",
    "schema": "neo4j-schema.md",
    "cypher": "neo4j-schema.md",
    "graph database": "neo4j-schema.md",
    "inference": "neo4j-schema.md",
    "supersede": "neo4j-schema.md",
    "api": "api-endpoints.md",
    "endpoint": "api-endpoints.md",
    "server.js": "api-endpoints.md",
    "route handler": "api-endpoints.md",
    "dashboard": "dashboard-views.md",
    "kanban": "dashboard-views.md",
    "provider": "provider-fallback.md",
    "fallback": "provider-fallback.md",
    "model switching": "provider-fallback.md",
    "claude-agent": "provider-fallback.md",
    "agent roster": "agent-roster.md",
    "asmr": "agent-roster.md",
    "task executor": "task-executor.md",
    "concurrency": "task-executor.md",
    "stall detection": "task-executor.md",
}


def detect_kb_hint(agent, text):
    """Auto-detect the most relevant KB doc for this task."""
    text_lower = text.lower()
    for keyword, doc in KB_HINTS.items():
        if keyword in text_lower:
            return doc
    return None
