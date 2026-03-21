# Harness Engineering - Key Learnings

**Source**: Danny, March 20, 2026
**Article**: "The model is almost irrelevant. The harness is everything."

---

## Core Thesis

The difference between teams shipping a million lines of code and teams struggling is NOT the model. It's the environment design (the harness).

A harness is NOT a system prompt, API wrapper, or eval framework. It's the **complete designed environment**:
- Tools the agent can call
- Format of information it receives
- How history is compressed and managed
- Guardrails that catch mistakes before they cascade
- Scaffolding for handoffs to future self

---

## SWE-agent Paper (Princeton NLP, 2024)

### Agent-Computer Interface (ACI)
- Abstraction layer between LM and computer environment
- **64% relative improvement** from interface design alone (same model!)
- Standard bash: 3.97% issues resolved → ACI: 12.47% resolved

### Key ACI Components
1. **Capped Search** (50 results max) - prevents context flooding
2. **Stateful File Viewer** (100 lines) - Goldilocks number, explicit line numbers
3. **File Editor with Linting** - immediate feedback, reject syntax errors
4. **Context Management** - compress observations beyond 5 turns

### Critical Insight
Context window is NOT RAM - it's **working consciousness**. Every irrelevant token competes for attention and degrades reasoning.

---

## Anthropic's Harness Engineering

### Two-Agent Architecture
1. **Initializer Agent** - sets up environment, does NOT write features
2. **Coding Agent** - works on one feature at a time

### Initializer Outputs
- `init.sh` - reliable dev environment startup
- Feature list (JSON, 200+ specific features, all marked failing initially)
- Progress file + initial git commit

### Key Patterns
- **Feature list as cognitive anchor** - prevents "declare victory too early"
- **Clean state requirement** - every session ends with git commit + progress update
- **Puppeteer MCP** for browser automation - catch bugs invisible from code
- **Startup sequence**: pwd → progress file → feature list → init.sh → basic test

---

## OpenAI's Codex Team (Zero Manual Code)

### Results
- 1M lines of code in 5 months
- 3 engineers → 7 engineers
- 3.5 PRs/engineer/day (increased with team size!)

### Engineering Job Changed
- Design environments, not code
- Specify intent
- Build feedback loops
- Ask: "what capability is missing from the environment?"

### Key Decisions
- **Repository as system of record** - if agent can't read it, it doesn't exist
- **Progressive disclosure** - short AGENTS.md (~100 lines) pointing to deeper docs
- **Application legibility** - bootable per worktree, Chrome DevTools, observability
- **Mechanical enforcement** - custom linters with agent-friendly error messages
- **Minimal blocking merge gates** - corrections cheap, waiting expensive

---

## Seven Layers of Harness Ecosystem

1. **Human Oversight** - approve, review, prioritize
2. **Planning/Requirements** - Spec Tools, task DAGs
3. **Full Lifecycle Platforms** - end-to-end management
4. **Task Runners** - issue tracker → workspace → PR
5. **Agent Orchestrators** - parallel execution, git worktree isolation
6. **Frameworks & Runtimes** - composable primitives, persistent infrastructure
7. **Coding Agents** - execution layer (commodity)

---

## Five Design Patterns

1. **Progressive Disclosure** - minimum to orient, pointers to find more
2. **Git Worktree Isolation** - one agent, one worktree
3. **Spec First, Repository as System of Record**
4. **Mechanical Architecture Enforcement** - linters, structural tests
5. **Integrated Feedback Loops** - catch errors at point of introduction

---

## The Shift in Questions

| Naive | Harness Engineering |
|-------|---------------------|
| "How do I write a better prompt?" | "What information does the agent need that it currently cannot access?" |
| "Why is the model making this mistake?" | "What feedback loop is missing that would catch this mistake?" |
| "Why is the agent not doing what I told it to?" | "What constraint in the environment is preventing the agent?" |

---

## Minimal Harness Components

1. **Persistent progress file** - read at start, write at end
2. **Structured task list** - verifiable completion criteria
3. **Version control** - descriptive commits as first-class requirement
4. **Browser automation** (for web apps) - see what user would see

---

## Application to Kurultai

Our current architecture aligns with harness principles:
- **AGENTS.md** = spec/feature list + routing rules
- **MEMORY.md** = progress file + known issues
- **Task routing system** = orchestrator layer
- **Heartbeat system** = feedback loops
- **Specialist agents** = isolated execution contexts

Potential improvements:
- Feature list in JSON (more resistant to casual modification)
- Init.sh for each agent workspace
- More mechanical enforcement (linters for agent outputs)
- Browser automation for UI testing

---

## Key Quotes

> "The model is what thinks. The harness is what thinks about."

> "Every failure is a signal about what the environment needs."

> "The interface is not a convenience layer. For an LM agent, the interface is the mind."

> "Getting the harness right is not a prompt engineering problem. It is a systems engineering problem."
