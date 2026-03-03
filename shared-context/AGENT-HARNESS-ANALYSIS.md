# Agent Harness Analysis - "The Coding Agent Harness"

**Source:** Julián De Angelis (@juliandeangelis) - Feb 28, 2026  
**Context:** MercadoLibre rolling out to 20,000 developers, thousands of repositories

---

## Core Thesis

**"The difference isn't the model, the IDE, or the provider. It's the agent harness: the structured system of context, tools, and guardrails you engineer around the agent so it performs reliably, every single time."**

---

## Key Concepts

### 1. Context Engineering

**Definition:** Designing and controlling everything an LLM sees before it generates a single token.

**Mental Model:** AI agent = brilliant new hire on day one with ZERO context about your codebase.

**What You'd Do for a Human:**
- Docs, tech stack, style guides
- Release process workflows
- Access to right tools
- Mentor to review work

**What We Should Do for Agents:**
- Same onboarding structure
- Context injection at right moments
- Avoid context pollution

---

### 2. The Agent Loop Bottleneck

```
Read → Plan → Code → Validate → Iterate
```

**Problem:** Every iteration consumes from the same finite resource: **the context window**

**Context Window Allocation:**
| Component | Behavior | Impact |
|-----------|----------|--------|
| System rules | Fixed at top | Wastes space if not useful |
| Tool definitions | Every MCP adds schema | More tools = less room |
| Conversation history | Accumulates linearly | Grows with every turn |
| Tool results | File contents, terminal output | Single large file = thousands of tokens |
| Agent output | The code it writes | Also lives in context window |

**Critical Insight:** Past ~60% context window utilization, **more context makes the agent actively worse** (context rot)

---

### 3. The Four Levers of the Agent Harness

#### Lever 1: Custom Rules (AGENTS.md, CLAUDE.md, etc.)

**What Goes In:**
- ✅ Project's tech stack and architecture patterns
- ✅ Naming conventions and code style preferences
- ✅ Testing philosophy ("always write unit tests with table driven inputs")
- ✅ Common pitfalls specific to your codebase
- ✅ What NOT to do (anti-patterns)

**What Doesn't Belong:**
- ❌ Entire API documentation (too long, wastes context)
- ❌ Obvious instructions ("write clean code")
- ❌ Contradictory rules

**Key Insights:**
- Custom rules are **living documents**
- Keep them under 500 lines
- Be precise in instructions
- Make them **modular** (split by concern: architecture, testing, code, security)
- Use **few-shot examples** (models learn from examples better than abstract instructions)
- Don't make everything always-on (use conditional loading)

**Our Current State:**
| Agent | Has Rules? | Modular? | Under 500 lines? |
|-------|------------|----------|------------------|
| Kublai | ✅ AGENTS.md | ❌ Monolithic | ✅ Yes |
| Möngke | ✅ AGENTS.md | ❌ Monolithic | ✅ Yes |
| Chagatai | ✅ AGENTS.md | ❌ Monolithic | ✅ Yes |
| Temüjin | ✅ AGENTS.md | ❌ Monolithic | ✅ Yes |
| Jochi | ✅ AGENTS.md | ❌ Monolithic | ✅ Yes |
| Ögedei | ✅ AGENTS.md | ❌ Monolithic | ✅ Yes |

**Recommendation:** Split each agent's AGENTS.md into modular files:
- `rules-architecture.md`
- `rules-testing.md`
- `rules-code-style.md`
- `rules-security.md`
- `rules-anti-patterns.md`

---

#### Lever 2: MCP Servers (Model Context Protocol)

**What They Are:** Plugins that extend the agent's capabilities beyond reading/writing files.

**Out of the Box:** Read files, write code, run terminal commands

**With MCPs:**
- Query database schemas
- Search internal documentation
- Look up internal API contracts
- Interact with CI/CD pipeline
- Access design specs from Figma
- Test actual implementation

**Our Current State:**
| Capability | Status |
|------------|--------|
| File read/write | ✅ Built-in |
| Terminal commands | ✅ Built-in |
| Database queries | ❌ No MCP |
| Internal docs search | ❌ No MCP |
| API contract lookup | ❌ No MCP |
| CI/CD interaction | ❌ No MCP |

**Recommendation:** Build internal MCPs for:
1. **Neo4j MCP** - Query operational memory
2. **Parse API MCP** - Trigger article analysis
3. **Railway MCP** - Deploy/check deployment status
4. **GitHub MCP** - Create PRs, check CI status

---

#### Lever 3: Skills

**What They Are:** Most powerful lever - combines context injection with executable logic.

**Structure:**
```
skill-name/
├── SKILL.md (entrypoint, short description stays in context)
├── templates/
├── examples/
├── reference-docs/
└── scripts/ (executable)
```

**Key Feature:** Only short description stays in context. Full content injected **on-demand** when skill is invoked.

**Two Flavors:**
1. **Reference Skills** - Inject knowledge (conventions, patterns, domain context)
2. **Task Skills** - Step-by-step instructions for specific actions

**Real Power:** Skills can **bundle and execute scripts** - extensibility is infinite.

**Can Run in Isolated Subagents** - Keeps heavy tasks from polluting main context window.

**Our Current State:**
| Skill | Type | Status |
|-------|------|--------|
| nano-banana-pro | Task Skill | ✅ Implemented |
| hourly_reflection | Task Skill | ✅ Implemented |
| multi-task-distribution | Reference Skill | ✅ Documented |

**Recommendation:** Create more skills:
- `research-skill` - Möngke's research methodology
- `content-skill` - Chagatai's content creation process
- `deploy-skill` - Temüjin's deployment checklist
- `analysis-skill` - Jochi's analysis framework
- `monitoring-skill` - Ögedei's monitoring procedures

---

#### Lever 4: Spec Driven Development (SDD)

**What It Is:** Writing detailed specifications BEFORE the agent writes a single line of code.

**Why It Matters:** "One of the top bottlenecks with current Coding Agents sits between the chair and the screen: **you**. This is because of a communication issue."

**Problem Example:**
> User: "Make a new feature to add new items from the backoffice"
>
> Seems simple, but doesn't specify: tech stack, where is the backoffice, API contracts, where to store new items.
>
> Agent will "predict" the correct implementation → Bugs (e.g., no idempotency handling)

**What Good Specs Have:**
- ✅ What the feature does
- ✅ How it integrates with existing code
- ✅ What the edge cases are
- ✅ What the acceptance criteria look like
- ✅ What the test plan is

**Why SDD is Context Engineering:**
> "The spec becomes the harness. When you hand an agent a well-written spec, you're engineering its entire context window in one shot."

**Our Current State:**
| Practice | Status |
|----------|--------|
| Spec templates | ❌ None |
| Acceptance criteria | ❌ Not standardized |
| Test plans | ❌ Ad-hoc |
| Edge case documentation | ❌ Not systematic |

**Recommendation:** Create spec templates:
- `task-spec-template.md` - For all tasks
- `feature-spec-template.md` - For new features
- `bug-fix-spec-template.md` - For bug fixes

---

### 4. The Feedback Loop

**What It Is:** Tests, linters, type checkers, build scripts - every tool that produces a pass/fail signal.

**Key Insight:** "The more structured feedback available, the less 'human in the loop' is needed."

**Agent Hooks:** User-defined commands that execute automatically at specific points in the agent's lifecycle.

**Example:** Wire validation into a **Stop hook** - agent literally cannot finish until checks pass.

**Our Current State:**
| Feedback Mechanism | Status |
|-------------------|--------|
| Automated tests | ⚠️ Ad-hoc |
| Linters | ⚠️ Not enforced |
| Type checking | ⚠️ Not enforced |
| Agent hooks | ❌ None |
| Review agents | ❌ None |

**Recommendation:**
1. Create agent hooks for:
   - Pre-commit validation
   - Pre-deployment checks
   - Post-task review
2. Build review agents:
   - Code review agent (Temüjin → Jochi review)
   - Content review agent (Chagatai → Möngke fact-check)
   - Deployment review agent (Temüjin → Ögedei health check)

---

## What MercadoLibre Does at Scale

### 1. Standardized Rules per Technology

**Practice:** Maintain curated set of custom rules at org level, tuned to 9+ tech stacks.

**Our Equivalent:** Create modular rules files for each agent's domain.

### 2. Internal MCPs

**Practice:** Built internal MCP servers for internal cloud platform capabilities.

**Our Equivalent:** Build Neo4j MCP, Parse API MCP, Railway MCP.

### 3. Custom Code Review Agents

**Practice:** Standalone review agents run as part of CI pipeline. Every PR gets analyzed automatically.

**Our Equivalent:** Jochi as dedicated review agent for all agent outputs.

---

## Recommendations for Kurultai

### Immediate (This Week)

1. **Modularize Agent Rules** (Day 1)
   - Split each agent's AGENTS.md into modular files
   - Create: `rules-architecture.md`, `rules-testing.md`, `rules-code-style.md`
   - Keep each under 500 lines

2. **Create Spec Templates** (Day 2)
   - `task-spec-template.md` with:
     - What the task does
     - Integration points
     - Edge cases
     - Acceptance criteria
     - Test plan

3. **Implement Agent Hooks** (Day 3-4)
   - Pre-commit validation hook
   - Pre-deployment check hook
   - Post-task review hook

4. **Designate Review Agents** (Day 5)
   - Jochi → Code review for Temüjin
   - Möngke → Fact-check for Chagatai
   - Ögedei → Health check for all deployments

### Short-Term (Next Week)

5. **Build Internal MCPs**
   - Neo4j MCP (query operational memory)
   - Parse API MCP (trigger analysis)
   - Railway MCP (deploy/check status)

6. **Create Task Skills**
   - `research-skill` for Möngke
   - `content-skill` for Chagatai
   - `deploy-skill` for Temüjin
   - `analysis-skill` for Jochi
   - `monitoring-skill` for Ögedei

7. **Implement Spec Driven Development**
   - All tasks require spec before execution
   - Use templates for consistency
   - Include acceptance criteria

### Long-Term (Next Month)

8. **Build Review Agents**
   - Automated code review in CI
   - Automated content fact-checking
   - Automated deployment health checks

9. **Context Window Optimization**
   - Monitor context utilization per agent
   - Keep below 60% utilization
   - Implement conditional rule loading

---

## Expected Impact

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| **Task Success Rate** | Unknown | >95% | Consistent results |
| **Context Utilization** | Unknown | <60% | Avoid context rot |
| **Human Review Time** | Unknown | -50% | Automated reviews |
| **Bug Rate** | Unknown | -70% | Spec-driven + reviews |
| **Deployment Failures** | Unknown | -80% | Pre-deployment hooks |

---

## Comparison: Current vs. Recommended

| Aspect | Current | Recommended |
|--------|---------|-------------|
| **Rules** | Monolithic AGENTS.md | Modular, conditional loading |
| **Tools** | Built-in only | + Internal MCPs |
| **Skills** | 2 skills | 7+ skills (per agent) |
| **Specs** | Ad-hoc | Spec-driven development |
| **Feedback** | Manual | Automated hooks + review agents |
| **Context Management** | Unknown | <60% utilization target |

---

## Implementation Priority

### Phase 1: Foundation (Week 1)
- [ ] Modularize rules
- [ ] Create spec templates
- [ ] Implement basic hooks

### Phase 2: Enhancement (Week 2)
- [ ] Build internal MCPs
- [ ] Create task skills
- [ ] Implement SDD workflow

### Phase 3: Automation (Week 3-4)
- [ ] Build review agents
- [ ] Automate feedback loops
- [ ] Monitor context utilization

---

## Key Takeaway

> "As AI coding agents become more capable, the teams that win won't be the ones using the fanciest model. They'll be the ones with the best-engineered harness."

**Our Opportunity:** Build the best-engineered harness for the Kurultai.

**The Difference:** Not which models we use (qwen3.5-plus, etc.), but how well we engineer the context, tools, and guardrails around each agent.

---

## Next Steps

**Ready to implement Phase 1?**

I can start with:
1. Modularizing agent rules (split AGENTS.md files)
2. Creating spec templates
3. Implementing basic agent hooks

**This will give us immediate improvements in consistency and reliability.**
