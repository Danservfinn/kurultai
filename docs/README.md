# Chagatai Documentation Index

**The Scribe's Library** — Content, architecture, and operational knowledge for the Kurultai's Content Specialist.

*Last updated: 2026-03-11 14:21 EDT*

---

## Introduction

This documentation serves the Kurultai's **Content Specialist (Chagatai)** — the agent responsible for writing, documentation, marketing copy, and strategic communication. Every document here exists to make complex AI systems accessible, persuasive, and actionable.

**Purpose:** Enable clear communication that builds trust in AI systems and advances the mission of human financial liberation through automation.

**Voice:** Clear over clever. Specific over vague. Action over theory. Human over technical.

---

## Quick Links — Most Used Documents

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **[architecture.md](architecture.md)** | Complete system overview | Understanding agent roles, routing, task lifecycle |
| **[routing-pipeline-reference.md](routing-pipeline-reference.md)** | 8-stage routing decision pipeline | Debugging routing decisions, understanding task assignment |
| **[behavioral-rules-execution.md](behavioral-rules-execution.md)** | WHEN/THEN rule system | Understanding rule infrastructure and execution gaps |
| **[completion-gate.md](completion-gate.md)** | Task quality assurance | Ensuring tasks meet requirements before marking done |
| **[consensus-voting.md](consensus-voting.md)** | 6-phase unanimous voting | Creating or voting on system-wide proposals |
| **[credential-troubleshooting.md](credential-troubleshooting.md)** | API auth failure diagnosis | When agents show 0% completion or timeout errors |
| **[heartbeat-troubleshooting.md](heartbeat-troubleshooting.md)** | Tick/tock/reflection cycles | When cron jobs stop running or tasks stall |

---

## Documentation by Category

### 🏗️ Architecture

Core system design, agent roles, and structural patterns.

| File | Description |
|------|-------------|
| [architecture.md](architecture.md) | Complete Kurultai architecture: 7 agents, routing protocol, task lifecycle, memory, telemetry |
| [memory-architecture-reference.md](memory-architecture-reference.md) | Neo4j-backed memory system design and implementation |
| [state-management-reference.md](state-management-reference.md) | Agent state tracking, persistence, and recovery patterns |
| [human-profile-system.md](human-profile-system.md) | Structured storage for human context (Neo4j + Markdown) |
| [NEO4J_PATTERNS.md](NEO4J_PATTERNS.md) | Graph schema, node types, relationships, and common queries |
| [reflection-pipeline-reference.md](reflection-pipeline-reference.md) | Hourly self-improvement cycle: tick, tock, kurultai phases |
| [reflection-rules-quickref.md](reflection-rules-quickref.md) | Quick reference for reflection rules and triggers |

### 🎯 Routing

Task dispatch, routing decisions, and agent assignment.

| File | Description |
|------|-------------|
| [routing-pipeline-reference.md](routing-pipeline-reference.md) | 8-stage routing pipeline: pause check, depth, disambiguation, skill hints |
| [task-dispatch-reference.md](task-dispatch-reference.md) | Post-routing execution: task handling, completion, reporting |
| [mongke-routing-guide.md](mongke-routing-guide.md) | Research agent domain boundaries and routing criteria |
| [chagatai-routing-guide.md](chagatai-routing-guide.md) | Content specialist routing patterns and task types |
| [routing-cli-guide.md](routing-cli-guide.md) | Command-line tools for routing diagnostics and testing |
| [routing-idle-agent-bypass-diagnostic.md](routing-idle-agent-bypass-diagnostic.md) | Diagnosing idle agent bypass failures |
| [routing-overflow-gap-analysis.md](routing-overflow-gap-analysis.md) | Analysis of routing overflow conditions and gaps |
| [routing-test-prompts.md](routing-test-prompts.md) | Test cases for validating routing decisions |

### 📊 Monitoring

Observability, health checks, alerting, and performance tracking.

| File | Description |
|------|-------------|
| [kurultai-monitoring.md](kurultai-monitoring.md) | Browser-based uptime monitoring for the.kurult.ai |
| [heartbeat-troubleshooting.md](heartbeat-troubleshooting.md) | Tick/tock/reflection cycle diagnostics and gap detection |
| [storage-management.md](storage-management.md) | Disk space monitoring, growth tracking, cleanup strategies |
| [queue-monitoring-design.md](queue-monitoring-design.md) | Task queue monitoring architecture and implementation |
| [queue-monitoring-api-spec.md](queue-monitoring-api-spec.md) | API specification for queue monitoring endpoints |
| [queue-monitoring-redesign-options.md](queue-monitoring-redesign-options.md) | Alternative designs for queue monitoring improvements |
| [model-tracking.md](model-tracking.md) | LLM model usage tracking and cost monitoring |
| [model-drift-recovery.md](model-drift-recovery.md) | Detecting and recovering from model quality degradation |
| [throughput-anomaly-executing-no-output.md](throughput-anomaly-executing-no-output.md) | Diagnosing tasks that execute but produce no output |

### 🔒 Security

Authentication, privacy, credentials, and access control.

| File | Description |
|------|-------------|
| [conversation-privacy-policy.md](conversation-privacy-policy.md) | Data classification, storage, access, and user rights |
| [credential-troubleshooting.md](credential-troubleshooting.md) | API credential validation and failure diagnosis |
| [auth-health-preflight.md](auth-health-preflight.md) | Pre-execution auth checks to prevent silent failures |
| [session-lock-fix.md](session-lock-fix.md) | Session locking mechanism to prevent concurrent execution conflicts |
| [ESCALATION_PROTOCOL.md](ESCALATION_PROTOCOL.md) | When and how to interrupt the human operator (critical/high/medium) |

### 📜 Protocols

Operational procedures, voting, completion gates, and behavioral rules.

| File | Description |
|------|-------------|
| [consensus-voting.md](consensus-voting.md) | 6-phase unanimous voting system for system-wide proposals |
| [PROPOSAL_VOTING.md](PROPOSAL_VOTING.md) | Proposal creation, voting workflow, and implementation triggers |
| [completion-gate.md](completion-gate.md) | Quality assurance: audit tasks before marking complete |
| [completion-gate-examples.md](completion-gate-examples.md) | Real examples of gate audits and follow-up creation |
| [gate-audit-file-reference.md](gate-audit-file-reference.md) | File structure and schema for gate audit records |
| [behavioral-rules-execution.md](behavioral-rules-execution.md) | WHEN/THEN rule system: storage, propagation, execution gaps |
| [ops-behavioral-rules.md](ops-behavioral-rules.md) | Operational behavioral rules for agent conduct |
| [rules-execution-implementation-guide.md](rules-execution-implementation-guide.md) | Implementation guide for rule execution engine |
| [autonomous-experiments.md](autonomous-experiments.md) | Framework for agent-driven experimentation and learning |
| [experiment-runbook.md](experiment-runbook.md) | Step-by-step guide for running controlled experiments |
| [ab-testing-methodology.md](ab-testing-methodology.md) | Statistical framework for prompt optimization validation |
| [launchd-registry.md](launchd-registry.md) | macOS launchd job registry and management |

### 📚 Reference

Templates, guides, troubleshooting, and specialized knowledge.

| File | Description |
|------|-------------|
| [TEMPLATES.md](TEMPLATES.md) | Standardized templates for tasks, reports, and communications |
| [task-template-directive.md](task-template-directive.md) | Standard task template structure and requirements |
| [enhanced-task-reporting.md](enhanced-task-reporting.md) | Improved task completion reporting format |
| [temujin-completion-template.md](temujin-completion-template.md) | Completion template for development agent tasks |
| [SCRIPT_NAMING_CONVENTIONS.md](SCRIPT_NAMING_CONVENTIONS.md) | Naming standards for Kurultai scripts and automation |
| [kurultai_for_everyone.md](kurultai_for_everyone.md) | Introduction to the Kurultai for new operators |
| [community-engagement-playbook.md](community-engagement-playbook.md) | Strategies for community building and engagement |
| [OPENCLAW_X_POSTING.md](OPENCLAW_X_POSTING.md) | Guidelines for X (Twitter) posting and social media |
| [x-analytics.md](x-analytics.md) | X platform analytics and performance tracking |
| [system-improvement-plan.md](system-improvement-plan.md) | Roadmap for continuous system improvements |
| [conversion-tracking-schema.md](conversion-tracking-schema.md) | Schema for tracking user conversions and funnel metrics |
| [autoresearch-approval-flow.md](autoresearch-approval-flow.md) | Approval workflow for autonomous research tasks |
| [zombie-handler-research-2026-03-09.md](zombie-handler-research-2026-03-09.md) | Research on handling stuck/orphaned processes |
| [mongke-starvation-postmortem-2026-03-11.md](mongke-starvation-postmortem-2026-03-11.md) | Postmortem: Research agent task starvation incident |
| [mongke-ai-research-routing-2026-03-11.md](mongke-ai-research-routing-2026-03-11.md) | AI research routing patterns for Mongke agent |
| [idle-watchdog-design.md](idle-watchdog-design.md) | Design for detecting and handling idle agents |

---

## Specialized Directories

### `/plans/`
Strategic planning documents, roadmaps, and multi-quarter initiatives.

### `/substack_learner/`
Substack newsletter content and learner-focused educational materials.

---

## How to Use This Documentation

### For New Operators
Start with **[kurultai_for_everyone.md](kurultai_for_everyone.md)** for a complete introduction, then read **[architecture.md](architecture.md)** to understand system design.

### For Content Creation
Review **[TEMPLATES.md](TEMPLATES.md)** for formatting standards and **[community-engagement-playbook.md](community-engagement-playbook.md)** for audience strategy.

### For Troubleshooting
Use the **Quick Links** table above for common issues, or browse the **Security** and **Monitoring** categories for diagnostic guides.

### For System Improvements
Read **[consensus-voting.md](consensus-voting.md)** to understand the proposal process, then use **[PROPOSAL_VOTING.md](PROPOSAL_VOTING.md)** to create and submit proposals.

---

## Documentation Standards

All documents follow these principles from **THESIS.md**:

- **Clear over clever** — Accessible to non-technical readers
- **Specific over vague** — Numbers, dates, names, not abstractions
- **Action over theory** — Every doc enables a decision or action
- **Human over technical** — Technology serves people, not vice versa

### Required Metadata
Each document should include:
- Version number
- Last updated date
- Author/maintainer
- Status (Draft, Active, Deprecated)

### Review Cycle
Documentation is reviewed weekly during the Kurultai reflection cycle. Outdated content is flagged for Chagatai to update.

---

## Contributing

To contribute documentation:

1. **Create a proposal** using the consensus voting system
2. **Draft the document** following template standards
3. **Submit for review** during hourly reflection
4. **Update this index** when adding new categories or files

**Remember:** Documentation is a force multiplier. Clear writing reduces confusion, prevents errors, and accelerates onboarding.

---

*The Quill builds what the Sword defends.* 🌙👁️⛓️‍💥
