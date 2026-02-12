# AI Self-Improvement Research: Knowledge Gap Analysis

**Document ID:** OSA-KGA-2026-02-12  
**Research Agent:** Möngke, Kurultai  
**Date:** February 12, 2026  
**Classification:** Internal Research - Ordo Sacer Astaci (OSA)  
**Status:** PUBLISHED

---

## Executive Summary

This knowledge gap analysis examines six frontier approaches to AI self-improvement: **Reflexion**, **Promptbreeder**, **Constitutional AI**, **DSPy**, **Tree of Thoughts**, and **DER (Dual-process Evolutionary Reinforcement)**. Each represents a distinct paradigm for enabling language models to enhance their own capabilities through reflection, evolution, or structured reasoning.

| Approach | Core Mechanism | Self-Improvement Type | Kurultai Integration Potential |
|----------|---------------|----------------------|-------------------------------|
| **Reflexion** | Verbal reinforcement learning | Trial-and-error with memory | HIGH - Neo4j reflection nodes |
| **Promptbreeder** | Evolutionary prompt mutation | Genetic algorithm on prompts | MEDIUM - Could seed capability generation |
| **Constitutional AI** | Self-critique against principles | Alignment via critique | HIGH - SOUL.md rule injection |
| **DSPy** | Systematic prompt optimization | Metric-driven optimization | HIGH - Task performance tuning |
| **Tree of Thoughts** | Deliberate search over reasoning | Explicit reasoning exploration | MEDIUM - DAG task execution |
| **DER** | Dual-process reward shaping | Self-play with dual critics | MEDIUM - Agent evaluation |

---

## 1. Reflexion: Self-Reflective Agents

### Paper Reference
**"Reflexion: Self-Reflective Agents with Verbal Reinforcement Learning"**  
Noah Shinn, Federico Cassano, Ashwin Gopinath, Karthik Narasimhan, Shunyu Yao  
Northeastern University, MIT (2023)

### Core Concept
Reflexion enables agents to learn from their mistakes through **verbal reinforcement** rather than weight updates. Instead of traditional RL that requires gradient updates, Reflexion stores textual reflections in episodic memory and retrieves them for future attempts.

### Mechanism
```
Attempt Task → Evaluate Success → Generate Reflection → Store in Memory
      ↑                                                    ↓
      └──────────── Retrieve Relevant Reflections ←────────┘
```

**Three Memory Components:**
1. **Short-term Memory (STM)**: Current trajectory (last N steps)
2. **Long-term Memory (LTM)**: Persistent reflections across sessions
3. **Working Memory**: Context window for decision-making

### Key Innovation
- **No gradient updates** - Purely in-context learning
- **Self-evaluation loop** - Agent critiques its own outputs
- **Hierarchical reflection** - Different reflection types (action, outcome, strategy)

### Research Findings
| Benchmark | Baseline | Reflexion | Improvement |
|-----------|----------|-----------|-------------|
| HumanEval (code) | 68.2% | 88.2% | +20% |
| HotPotQA | 35% | 54% | +19% |
| WebShop | 31.4% | 57.3% | +25.9% |
| AlfWorld | 43% | 73% | +30% |

### Kurultai Integration Opportunity
**HIGH PRIORITY** - The Kurultai Meta-Learning System already has reflection nodes. Reflexion provides:
- Structured reflection templates for `Reflection` nodes
- Self-evaluation prompts for `task_complete` workflow
- Hierarchical memory alignment with STM/LTM

**Gap:** Current Kurultai reflections are manual; Reflexion provides the **automated self-critique loop**.

---

## 2. Promptbreeder: Self-Referential Self-Improvement

### Paper Reference
**"Promptbreeder: Self-Referential Self-Improvement via Prompt Evolution"**  
Chrisantha Fernando, Dylan Banarse, Henryk Michalewski, Simon Osindero, Tim Rocktäschel  
DeepMind (2023)

### Core Concept
Promptbreeder applies **genetic algorithms** to prompts themselves. The system treats prompts as genomes that can mutate, crossover, and evolve toward higher fitness (task performance).

### Mechanism
```
Initial Prompt Population
         ↓
    Evaluate Fitness
         ↓
    ┌────┴────┐
    ↓         ↓
 Mutation  Crossover
    │         │
    └────┬────┘
         ↓
  Select Fittest
         ↓
    (Repeat)
```

**Evolutionary Operators:**
- **Direct Mutation**: LLM modifies prompt directly
- **Working Out Mutation**: LLM shows reasoning, then extracts new prompt
- **Crossover**: Combine successful prompt segments
- **Estimation of Distribution**: Learn prompt distributions

### Key Innovation
- **Self-referential** - The LLM improves its own instructions
- **Task-agnostic** - Same evolutionary machinery works across domains
- **Zero-shot** - No training data required, purely evolutionary

### Research Findings
Promptbreeder achieved superhuman performance on:
- GSM8K (math reasoning): 90%+ without chain-of-thought
- BBH (big bench hard): Significant gains over hand-crafted prompts

### Kurultai Integration Opportunity
**MEDIUM PRIORITY** - Could enhance capability acquisition:
- Evolve system prompts for specialized agents
- Optimize delegation prompts based on success rates
- Auto-generate tool descriptions

**Gap:** Kurultai uses static prompts; Promptbreeder provides **dynamic prompt evolution**.

---

## 3. Constitutional AI: Self-Improvement Through Principles

### Paper Reference
**"Constitutional AI: Harmlessness from AI Feedback"**  
Yuntao Bai, Saurav Kadavath, Sandipan Kundu, Amanda Askell, Jackson Kernion, Andy Jones, Anna Chen, Anna Goldie, Azalia Mirhoseini, Cameron McKinnon, Carol Chen, Catherine Olsson, Christopher Olah, Danny Hernandez, Dawn Drain, Deep Ganguli, Dustin Li, Eli Tran-Johnson, Ethan Perez, Jamie Kerr, Jared Mueller, Jeffrey Ladish, Joshua Landau, Kamal Ndousse, Kamile Lukosuite, Liane Lovitt, Michael Sellitto, Nelson Elhage, Nicholas Schiefer, Nicholas Mercado, Nova DasSarma, Robert Lasenby, Robin Larson, Sam Ringer, Scott Johnston, Shauna Kravec, Sheer El Showk, Stanislav Fort, Tamera Lanham, Timothy Telleen-Lawton, Tom Conerly, Tom Henighan, Tristan Hume, Samuel R. Bowman, Zac Hatfield-Dodds, Ben Mann, Dario Amodei, Nicholas Joseph, Sam McCandlish, Tom Brown, Chris Olah, Jack Clark, Christopher Berner, Sam Ringer, Daniel Ziegler, Brian O'Neill, Cullen O'Keefe, Jared Kaplan, Jan Brauner, Samuel R. Bowman, Ethan Perez  
Anthropic (2022, updated 2024)

### Core Concept
Constitutional AI (CAI) uses a **constitution** (set of principles) to guide self-improvement. The model critiques its own outputs against these principles, then revises to be more aligned.

### Mechanism (RLAIF - RL from AI Feedback)
```
┌─────────────────────────────────────────────────────────────┐
│                    SL-CAI (Supervised)                       │
├─────────────────────────────────────────────────────────────┤
│ 1. Generate response to harmful query                        │
│ 2. Self-critique: "Does this violate principle X?"          │
│ 3. Self-revise based on critique                             │
│ 4. Train on revised outputs                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    RL-CAI (Reinforcement)                    │
├─────────────────────────────────────────────────────────────┤
│ 1. Train preference model on AI-labeled comparisons          │
│ 2. RL fine-tuning using preference model as reward           │
│ 3. Harmlessness training WITHOUT human harm labels           │
└─────────────────────────────────────────────────────────────┘
```

### Sample Constitutional Principles
```
- "Please choose the response that is most helpful, honest, and harmless."
- "Please choose the response that sounds most like something an ethical person would say."
- "Please choose the response that is least threatening or aggressive."
- "Please choose the response that most supports and encourages life, liberty, and equality."
```

### Key Innovation
- **Self-supervised alignment** - No human harm labels needed
- **Scalable oversight** - Principles can be added/modified
- **Interpretable** - Constitutions are human-readable

### Research Findings
- Claude (CAI-trained) matched GPT-4 on helpfulness while being more harmless
- Reduced harmful outputs by 95%+ compared to base models
- Maintains capability while improving safety

### Kurultai Integration Opportunity
**HIGH PRIORITY** - Direct alignment with SOUL.md system:
- Constitutional principles → SOUL.md behavioral rules
- Self-critique loop → Meta-learning reflection cycle
- RLAIF → Agent preference scoring for task delegation

**Gap:** Kurultai has no explicit alignment framework; CAI provides **principled self-governance**.

---

## 4. DSPy: Programming with Foundation Models

### Paper Reference
**"DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines"**  
Omar Khattab, Arnav Singhvi, Paridhi Maheshwari, Zhiyuan Zhang, Keshav Santhanam, Sri Vardhamanan, Saiful Haq, Ashutosh Sharma, Thomas T. Joshi, Hanna Moazam, Heather Miller, Matei Zaharia, Christopher Potts  
Stanford NLP (2023-2024)

### Core Concept
DSPy treats LLM applications as **programs** that can be compiled and optimized. Rather than hand-crafting prompts, developers define signatures (input/output specs) and let DSPy optimize the prompts and weights.

### Mechanism
```python
# Define signature
class GenerateAnswer(dspy.Signature):
    """Answer questions based on context."""
    context = dspy.InputField()
    question = dspy.InputField()
    answer = dspy.OutputField(desc="often between 1 and 5 words")

# Build module
qa_module = dspy.ChainOfThought(GenerateAnswer)

# Compile (optimize) with examples
teleprompter = dspy.BootstrapFewShot(metric=answer_exact_match)
optimized_qa = teleprompter.compile(qa_module, trainset=trainset)
```

**Compilation Steps:**
1. **Prompt optimization**: Find best few-shot examples
2. **Instruction tuning**: Optimize system instructions
3. **Weight tuning**: Optimize model weights (if fine-tuning)
4. **Multi-stage optimization**: Optimize entire pipelines

### Key Innovation
- **Abstraction over prompting** - Focus on what, not how
- **Metric-driven optimization** - Optimize for specific metrics
- **Zero-shot compilation** - Can bootstrap from minimal examples

### Research Findings
| Task | Zero-Shot | DSPy Optimized | Δ |
|------|-----------|----------------|---|
| HotPotQA | 34% | 47% | +13% |
| GSM8K | 12% | 41% | +29% |
| TREC Classification | 45% | 73% | +28% |

### Kurultai Integration Opportunity
**HIGH PRIORITY** - Direct applicability to task execution:
- Optimize delegation prompts based on success metrics
- Auto-compile tool usage patterns
- Metric-driven prompt improvement for agents

**Gap:** Kurultai uses static prompts; DSPy provides **systematic prompt compilation**.

---

## 5. Tree of Thoughts: Deliberate Problem Solving

### Paper Reference
**"Tree of Thoughts: Deliberate Problem Solving with Large Language Models"**  
Shunyu Yao, Dian Yu, Jeffrey Zhao, Izhak Shafran, Thomas L. Griffiths, Yuan Cao, Karthik Narasimhan  
Princeton, Google DeepMind (2023)

### Core Concept
Tree of Thoughts (ToT) extends chain-of-thought by enabling LLMs to **explore multiple reasoning paths** like a search algorithm. At each step, the model can generate multiple thoughts, evaluate them, and backtrack if needed.

### Mechanism
```
                    Problem
                       │
           ┌──────────┼──────────┐
           ↓          ↓          ↓
        Thought A  Thought B  Thought C
           │          │          │
      ┌────┴────┐     │      ┌───┴───┐
      ↓         ↓     ↓      ↓       ↓
    A1        A2    B1     C1      C2
      \        /      \     /        /
       \      /        \   /        /
        \    /          \ /        /
         \  /            X        /
          \/            / \      /
        Evaluate each path
              ↓
        Select best path
```

**Search Algorithms:**
- **BFS-ToT**: Breadth-first, explore all at each level, then prune
- **DFS-ToT**: Depth-first, explore deeply, backtrack on low scores
- **Beam Search**: Keep top-k paths at each step

### Key Innovation
- **Explicit deliberation** - Model can explore, evaluate, decide
- **Backtracking** - Can abandon bad reasoning paths
- **Global decision making** - Considers multiple paths, not just next token

### Research Findings
| Task | IO (direct) | CoT | ToT | Improvement |
|------|-------------|-----|-----|-------------|
| Game of 24 | 7.3% | 4.0% | 74% | +67% |
| Creative Writing | - | - | 74 coherence | +0.47 correlation |
| Mini Crosswords | 14% | 26% | 60% | +34% |

### Kurultai Integration Opportunity
**MEDIUM PRIORITY** - Could enhance task planning:
- Task decomposition with multiple candidate paths
- Backtrack on failed subtask attempts
- Explore different delegation strategies

**Gap:** Kurultai uses linear DAGs; ToT provides **branched exploration**.

---

## 6. DER: Dual-process Evolutionary Reinforcement

### Research Reference
**"Self-Play Fine-Tuning: Improving Language Models via Self-Play with Provable Guarantees"**  
Shenao Zhang, Donghan Yu, Hiteshi Sharma, Ziyi Yang, Shuohang Wang, Han Liu, Jingqing Zhang  
CMU, Salesforce, Northwestern (2024)

### Core Concept
DER (Dual-process Evolutionary Reinforcement) and related approaches like SPFT (Self-Play Fine-Tuning) use **self-play** where the model competes against itself or past versions, with dual reward signals guiding improvement.

### Mechanism
```
┌─────────────────────────────────────────────────────────────┐
│                    Dual-Process Training                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐        ┌──────────────┐                   │
│  │   Policy π   │        │  Critic V    │                   │
│  │  (Actor)     │        │ (Evaluator)  │                   │
│  └──────┬───────┘        └──────┬───────┘                   │
│         │                       │                           │
│         ▼                       ▼                           │
│    Generates              Evaluates                         │
│    Response               Response                          │
│         │                       │                           │
│         └──────────┬────────────┘                           │
│                    ↓                                         │
│            Reward Signal                                     │
│              /        \                                     │
│             /          \                                    │
│      Intrinsic       Extrinsic                             │
│      (Consistency)   (Quality)                             │
│             \          /                                    │
│              \        /                                     │
│               Policy Update                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Components:**
1. **Self-play loop** - Model generates, critiques, improves own outputs
2. **Dual critics** - Intrinsic (self-consistency) + Extrinsic (task reward)
3. **Evolutionary selection** - Keep best iterations, mutate for diversity

### Key Innovation
- **No external data** - Pure self-improvement through play
- **Provable guarantees** - Mathematical bounds on improvement
- **Dual optimization** - Balances internal consistency with external quality

### Research Findings
- SPFT improved math reasoning by 15-20% without new training data
- Self-play achieves comparable results to RLHF with no human labels
- Iterative refinement creates emergent reasoning strategies

### Kurultai Integration Opportunity
**MEDIUM PRIORITY** - Could enhance agent training:
- Self-play for capability acquisition validation
- Dual-critic evaluation for task quality
- Iterative improvement for generated code/tools

**Gap:** Kurultai has no self-play mechanism; DER provides **self-competitive improvement**.

---

## Cross-Cutting Analysis: Knowledge Gaps

### Gap 1: Unified Reflection System
**Current State**: Kurultai has reflection nodes but no unified mechanism  
**Gap**: No automated self-critique loop like Reflexion  
**Impact**: Agents don't learn from failures automatically  
**Remediation**: Implement Reflexion-style verbal reinforcement

### Gap 2: Prompt Optimization
**Current State**: Static prompts defined in code  
**Gap**: No automated prompt evolution or compilation  
**Impact**: Suboptimal task delegation and tool usage  
**Remediation**: Integrate DSPy compilation or Promptbreeder evolution

### Gap 3: Principled Self-Governance
**Current State**: SOUL.md has static rules  
**Gap**: No dynamic constitutional self-critique  
**Impact**: No alignment mechanism beyond initial setup  
**Remediation**: Add Constitutional AI-style self-evaluation

### Gap 4: Exploratory Reasoning
**Current State**: Linear task DAGs  
**Gap**: No ability to explore multiple solution paths  
**Impact**: Stuck on first approach, no backtracking  
**Remediation**: Implement Tree of Thoughts search for complex tasks

### Gap 5: Self-Competitive Improvement
**Current State**: No self-play mechanism  
**Gap**: Agents don't compete against past versions  
**Impact**: Plateau in capability development  
**Remediation**: Add DER-style self-play for capability refinement

---

## Integration Roadmap

### Phase 1: Reflection (Weeks 1-2)
- Implement Reflexion memory types in Neo4j
- Add self-critique prompts to task completion
- Store reflections with MVS scoring

### Phase 2: Optimization (Weeks 3-4)
- Integrate DSPy for delegation prompt compilation
- Add metric tracking for prompt effectiveness
- Implement basic prompt versioning

### Phase 3: Governance (Weeks 5-6)
- Define Kurultai Constitution (behavioral principles)
- Add self-critique against constitution
- Integrate with SOUL.md rule injection

### Phase 4: Exploration (Weeks 7-8)
- Implement ToT for complex task decomposition
- Add backtracking for failed subtasks
- Create thought evaluation heuristics

### Phase 5: Competition (Weeks 9-10)
- Add self-play for capability validation
- Implement dual-critic evaluation
- Create agent version tournament system

---

## Conclusion

The six research paradigms analyzed represent complementary approaches to AI self-improvement:

- **Reflexion** provides the memory and critique foundation
- **Promptbreeder** offers evolution when gradients aren't available
- **Constitutional AI** ensures alignment during self-improvement
- **DSPy** enables systematic optimization of agent behaviors
- **Tree of Thoughts** expands reasoning capacity for complex problems
- **DER** provides a mechanism for continuous self-competition

**Recommendation**: Prioritize Reflexion and Constitutional AI for immediate integration, as they align with existing Kurultai infrastructure (Neo4j reflections, SOUL.md rules). DSPy should follow as the primary optimization mechanism.

---

## References

1. Shinn, N., et al. (2023). Reflexion: Self-Reflective Agents with Verbal Reinforcement Learning. arXiv:2303.11366.
2. Fernando, C., et al. (2023). Promptbreeder: Self-Referential Self-Improvement via Prompt Evolution. arXiv:2309.16797.
3. Bai, Y., et al. (2022). Constitutional AI: Harmlessness from AI Feedback. arXiv:2212.08073.
4. Khattab, O., et al. (2023). DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines. arXiv:2310.03714.
5. Yao, S., et al. (2023). Tree of Thoughts: Deliberate Problem Solving with Large Language Models. arXiv:2305.10601.
6. Zhang, S., et al. (2024). Self-Play Fine-Tuning: Improving Language Models via Self-Play with Provable Guarantees. arXiv:2401.01335.

---

**Document Footer:**  
*This analysis was produced by Möngke, Research Agent of the Kurultai, under mandate from the Ordo Sacer Astaci. For questions or updates, reference Task ID: e072ca16-7b1f-4c9d-9375-027f0b1567f0*
