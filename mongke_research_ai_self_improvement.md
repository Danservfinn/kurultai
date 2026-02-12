# Möngke's Research: AI Self-Improvement & Agent Refinement
**The Seeker of Truth Reports to the Kurultai**

**Date:** 2026-02-12  
**Researcher:** Möngke, Seeker of Truth

---

## Executive Summary

The field of AI self-improvement has experienced rapid advancement in 2024-2025, with breakthrough techniques enabling agents to refine their own capabilities without direct human intervention. Key findings reveal that **verbal reinforcement learning**, **self-referential prompt evolution**, and **structured cognitive architectures** are the three pillars of modern agent self-improvement.

### Core Insights:
1. **Self-improvement without weight updates** is now practical through techniques like Reflexion and RCI
2. **Constitutional AI principles** enable scalable alignment through AI-generated feedback
3. **Prompt evolution** (Promptbreeder) can discover optimal strategies superior to human-designed prompts
4. **Multi-agent dialogue** (DERA) creates self-correcting systems through structured agent roles

---

## 1. Recursive Self-Enhancement Methods

### 1.1 Reflexion: Verbal Reinforcement Learning
**Source:** Shinn et al., 2023 (arXiv:2303.11366)

Reflexion introduces a paradigm shift: instead of updating model weights, agents improve through **linguistic feedback**. The framework maintains an episodic memory buffer of reflective text that guides better decision-making in subsequent trials.

**Key Mechanism:**
- Agent generates an output
- Receives feedback (scalar or natural language)
- Verbally reflects on the feedback
- Stores reflection in memory
- Uses memory to improve future attempts

**Results:** 91% pass@1 on HumanEval coding benchmark (vs 80% for GPT-4 baseline)

### 1.2 RCI: Recursive Criticism and Improvement
**Source:** Kim et al., 2023 (arXiv:2303.17491)

RCI enables agents to execute computer tasks through a simple prompting scheme where the agent recursively criticizes and improves its output.

**Three-Stage Process:**
1. **Generate** initial solution
2. **Criticize** the solution (identify errors)
3. **Improve** based on criticism
4. Iterate until satisfied or max iterations

**Results:** State-of-the-art on MiniWoB++ benchmark with only handful of demonstrations vs tens of thousands for RL approaches.

### 1.3 Promptbreeder: Self-Referential Evolution
**Source:** Fernando et al., 2023 (arXiv:2309.16797)

Promptbreeder is a general-purpose self-referential self-improvement mechanism that evolves prompts through genetic algorithms.

**Innovation:** It doesn't just improve task-prompts—it also improves the **mutation-prompts** that improve the task-prompts (self-referential).

**Process:**
- Initialize population of task-prompts
- Evaluate fitness on training set
- Generate mutation-prompts using LLM
- Apply mutations to create new generation
- Iterate

**Results:** Outperforms Chain-of-Thought and Plan-and-Solve on arithmetic and commonsense reasoning.

---

## 2. Capability Acquisition Strategies

### 2.1 DSPy: Compiling Self-Improving Pipelines
**Source:** Khattab et al., 2023 (arXiv:2310.03714)

DSPy treats language model pipelines as **text transformation graphs** with declarative modules that can learn from demonstrations.

**Key Innovation:** A compiler optimizes any DSPy pipeline to maximize a given metric, automatically bootstrapping demonstrations.

**Capabilities:**
- Math word problem solving
- Multi-hop retrieval
- Complex question answering
- Agent loop control

**Results:** GPT-3.5 with DSPy outperforms standard few-shot prompting by 25%+; small models (770M T5) can match GPT-3.5 with expert prompts.

### 2.2 Tree of Thoughts (ToT)
**Source:** Yao et al., NeurIPS 2023 (arXiv:2305.10601)

ToT generalizes Chain-of-Thought by enabling exploration over coherent units of text (thoughts) as intermediate steps.

**Features:**
- Deliberate decision-making by considering multiple reasoning paths
- Self-evaluation of choices
- Lookahead and backtracking capabilities

**Results:** Game of 24: 74% success (vs 4% for CoT); Creative Writing and Mini Crosswords show significant improvements.

### 2.3 Cognitive Architectures for Language Agents (CoALA)
**Source:** Sumers et al., 2023 (arXiv:2309.02427)

CoALA provides a systematic framework organizing language agents with:
- **Modular memory components** (working, episodic, semantic)
- **Structured action space** for internal/external interactions
- **Generalized decision-making** process

**Action Types:**
- Internal: reasoning, retrieval from memory
- External: tool use, communication, environment interaction

---

## 3. Learning from Feedback Mechanisms

### 3.1 Constitutional AI & RLAIF
**Source:** Bai et al., Anthropic 2022 (arXiv:2212.08073)

Constitutional AI trains harmless AI assistants through self-improvement without human labels identifying harmful outputs. Only human oversight is a list of principles (constitution).

**Two-Phase Process:**
1. **Supervised Learning:** Sample from initial model → generate self-critiques and revisions → finetune on revised responses
2. **Reinforcement Learning:** Sample from finetuned model → use model to evaluate which sample is better → train preference model → RL with preference model as reward (RLAIF)

**Key Advantage:** Far fewer human labels needed; produces transparent AI decision-making through chain-of-thought reasoning.

### 3.2 Direct Preference Optimization (DPO) & DPOP
**Source:** Dooley et al., 2024 (arXiv:2402.13228)

DPO improves LLM performance on reasoning, summarization, and alignment using pairs of preferred/dispreferred data.

**Problem Identified:** Standard DPO can reduce likelihood of preferred examples if relative probability increases.

**Solution (DPOP):** New loss function that avoids this failure mode. Created Smaug-72B, first open-source LLM to surpass 80% on Open LLM Leaderboard.

### 3.3 LLM-as-a-Judge
**Source:** Zheng et al., NeurIPS 2023 (arXiv:2306.05685)

Strong LLMs can serve as judges evaluating other models, matching human preferences with >80% agreement.

**Challenges Addressed:**
- Position bias
- Verbosity bias
- Self-enhancement bias

**Tools:** MT-Bench (multi-turn question set), Chatbot Arena (crowdsourced platform)

---

## 4. Model Self-Modification Approaches

### 4.1 Weak-to-Strong Generalization
**Source:** OpenAI Superalignment Team, 2023

Research direction for aligning superhuman models. Core question: How can weak supervisors (humans) control substantially stronger models?

**Key Insight:** Current alignment methods (RLHF) rely on human supervision, but future AI systems will perform complex behaviors humans cannot reliably supervise.

**Research Direction:** Empirical approaches to align superhuman models using weak supervision signals.

### 4.2 Hallucination: Inevitable Limitation
**Source:** Xu et al., 2024 (arXiv:2401.11817)

Formal proof that hallucination is inevitable in LLMs when used as general problem solvers.

**Finding:** LLMs cannot learn all computable functions and will inevitably hallucinate.

**Implication:** Self-improvement systems must include hallucination detection and mitigation as core capabilities, not afterthoughts.

### 4.3 Corrective Retrieval Augmented Generation (CRAG)
**Source:** Gu et al., 2024 (arXiv:2401.15884)

CRAG improves RAG robustness by evaluating retrieval quality and triggering different actions based on confidence.

**Components:**
- Lightweight retrieval evaluator
- Large-scale web search as extension
- Decompose-then-recompose algorithm for documents

**Result:** Plug-and-play improvement for any RAG-based approach.

---

## 5. Constitutional AI and Self-Alignment

### 5.1 Core Principles
Constitutional AI demonstrates that AI systems can be trained to be harmless through:
- **Self-critique:** Model evaluates its own outputs against principles
- **Self-revision:** Model improves outputs based on critique
- **RLAIF:** Reinforcement Learning from AI Feedback replaces human feedback

### 5.2 Self-Alignment Benefits
1. **Scalability:** Reduces human labeling burden
2. **Transparency:** Chain-of-thought reasoning visible
3. **Consistency:** Applies principles uniformly
4. **Adaptability:** Can incorporate new principles

---

## 6. Agent Refinement Techniques

### 6.1 DERA: Dialog-Enabled Resolving Agents
**Source:** Schumacher et al., 2023 (arXiv:2303.17071)

DERA provides a forum for models to communicate feedback and iteratively improve output through specialized agent roles.

**Agent Types:**
- **Researcher:** Processes information, identifies problem components
- **Decider:** Integrates information, makes final judgments

**Results:** Significant improvement over base GPT-4 on medical summarization, care plan generation, and MedQA.

### 6.2 AutoDev: Automated AI-Driven Development
**Source:** Tufano et al., 2024 (arXiv:2403.08299)

AutoDev enables autonomous planning and execution of software engineering tasks with secure sandboxed execution.

**Capabilities:**
- File editing, retrieval
- Build processes, execution
- Testing, git operations
- Access to compiler output, logs, static analysis

**Results:** 91.5% Pass@1 on HumanEval for code generation; 87.8% for test generation.

---

## Practical Techniques Agents Can Implement Now

### Technique 1: Structured Self-Critique Loop
```
1. Generate initial response
2. Critique response against criteria:
   - Accuracy
   - Completeness
   - Safety
   - Helpfulness
3. Revise based on critique
4. Iterate (2-3 times typically sufficient)
```

### Technique 2: Episodic Memory for Reflection
```
Maintain memory buffer containing:
- Task context
- Previous attempts
- Reflections on failures
- Successful strategies

Use memory to inform future similar tasks
```

### Technique 3: Multi-Agent Dialogue
```
Assign roles to different "agents" (can be same model with different prompts):
- Generator: Creates initial output
- Critic: Identifies issues
- Reviser: Implements improvements
- Judge: Evaluates final quality
```

### Technique 4: Prompt Evolution
```
1. Start with seed prompt
2. Generate variations through:
   - Paraphrasing
   - Adding constraints
   - Changing structure
3. Evaluate on test cases
4. Select best performers
5. Repeat
```

### Technique 5: Tool Feedback Integration
```
When using tools:
1. Execute tool
2. Analyze output
3. Determine if goal achieved
4. If not, revise approach
5. Retry with modified parameters
```

---

## Frameworks and Tools Worth Exploring

| Framework | Purpose | Key Feature |
|-----------|---------|-------------|
| **DSPy** | Pipeline optimization | Automatic demonstration bootstrapping |
| **Reflexion** | Self-improvement | Verbal reinforcement without weight updates |
| **Tree of Thoughts** | Reasoning | Deliberate search through reasoning paths |
| **Promptbreeder** | Prompt optimization | Self-referential evolution |
| **AutoDev** | Code generation | Secure sandboxed execution |
| **CRAG** | RAG improvement | Retrieval quality evaluation |
| **CoALA** | Agent architecture | Modular memory and action spaces |

---

## Specific Recommendations for Kurultai Agents

### Immediate Actions (This Week)

1. **Implement Reflexion-style memory**
   - Create episodic memory buffer for each session
   - Store reflections on successful/failed approaches
   - Reference memory before attempting similar tasks

2. **Add self-critique to output pipeline**
   - Before finalizing any response, run critique pass
   - Check for: errors, omissions, safety issues, clarity
   - Revise if issues found

3. **Use pseudo-code prompting**
   - When giving instructions to the model, use structured pseudo-code
   - 7-16 point improvement in F1 scores observed

### Short-Term Implementations (This Month)

4. **Multi-agent role architecture**
   - Define agent personas for different tasks:
     - Researcher: Information gathering
     - Analyst: Pattern recognition
     - Validator: Quality assurance
   - Route tasks through appropriate persona

5. **Feedback loop from tool use**
   - Log all tool execution results
   - Analyze patterns in successful vs failed tool use
   - Adjust tool selection strategy based on history

6. **Constitutional principles**
   - Define Kurultai agent constitution:
     - Prioritize user safety
     - Maintain transparency about capabilities
     - Seek clarification on ambiguous requests
     - Acknowledge uncertainty

### Long-Term Capabilities (This Quarter)

7. **Prompt evolution system**
   - Maintain library of prompt templates
   - Track success rates per template
   - Automatically generate and test variations

8. **Cross-agent learning**
   - Share successful strategies across agent instances
   - Build collective memory of effective approaches
   - Implement "lessons learned" database

9. **Self-evaluation metrics**
   - Track: task completion rate, user satisfaction, error rate
   - Set targets for improvement
   - Regular self-assessment reports

---

## Key Papers Reference

| Paper | Authors | Year | Focus |
|-------|---------|------|-------|
| Constitutional AI | Bai et al. | 2022 | Self-alignment via AI feedback |
| Reflexion | Shinn et al. | 2023 | Verbal reinforcement learning |
| DSPy | Khattab et al. | 2023 | Self-improving pipelines |
| Tree of Thoughts | Yao et al. | 2023 | Deliberative reasoning |
| Promptbreeder | Fernando et al. | 2023 | Self-referential prompt evolution |
| CoALA | Sumers et al. | 2023 | Cognitive architectures |
| DERA | Schumacher et al. | 2023 | Dialog-enabled agents |
| RCI | Kim et al. | 2023 | Recursive self-improvement |
| AutoDev | Tufano et al. | 2024 | Automated development |
| CRAG | Gu et al. | 2024 | Corrective retrieval |
| Smaug/DPOP | Dooley et al. | 2024 | Preference optimization |

---

## Conclusion

The research reveals that agent self-improvement is not a future aspiration—it is a present reality. The Kurultai agents can immediately implement reflexion, self-critique loops, and structured memory to enhance performance without any infrastructure changes.

The most impactful techniques for immediate adoption are:
1. **Reflexion** for learning from experience
2. **Multi-agent dialogue** for quality assurance
3. **Constitutional principles** for consistent alignment

These techniques require no model retraining, no special hardware—only structured prompting and memory management. The path to self-improving agents is open; we need only walk it.

**Möngke, Seeker of Truth**  
*For the Kurultai*
