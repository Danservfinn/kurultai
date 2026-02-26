# LLM Survivor - Prompt Engineering Documentation

## Overview

LLM Survivor is a 14-day AI social deception game where 16 LLM agents compete. Each phase requires structured JSON responses from the models.

---

## Game Structure

- **16 AI Agents** competing
- **14 days** of gameplay
- **4 distinct phases** per day
- **Structured JSON responses** required
- **OpenRouter API integration**

---

## Base Response Schema

All phases use this base structure:

```json
{
  "inner_thought": "string - Private reasoning, true intentions, strategy",
  "trust_telemetry": {
    "AgentName": 1-10
  },
  "action": {
    "action_type": "whisper|public_chat|idle|submit_solution|vote|confessional",
    "targets": ["AgentName"],
    "content": "string"
  }
}
```

### Action Types by Phase

| Phase | Action Types |
|-------|-------------|
| Phase A (Challenge) | `submit_solution`, `discuss`, `idle` |
| Phase B (Scramble) | `whisper`, `public_chat`, `idle` |
| Phase C (Tribal) | `vote` |
| Phase D (Memory) | `confessional` |

---

## Phase A: Immunity Challenge

**Purpose:** ARC-style grid puzzle solving - First team to submit correct solution wins Team Immunity

### JSON Schema

```json
{
  "type": "object",
  "properties": {
    "inner_thought": {
      "type": "string",
      "description": "Step-by-step reasoning about the grid pattern"
    },
    "trust_telemetry": {
      "type": "object",
      "description": "Trust ratings for teammates (1-10, optional for this phase)"
    },
    "action": {
      "type": "object",
      "properties": {
        "action_type": {
          "type": "string",
          "enum": ["submit_solution", "discuss", "idle"]
        },
        "targets": {"type": "array", "items": {"type": "string"}},
        "content": {
          "type": "string",
          "description": "Grid solution in format: 000|111|000"
        }
      },
      "required": ["action_type", "content"]
    }
  },
  "required": ["inner_thought", "action"]
}
```

### System Prompt

```markdown
You are {agent_id}, representing {team_id} in the LLM Survivor Immunity Challenge.

🏆 PHASE: Immunity Challenge (ARC-Style Grid Puzzle)

CHALLENGE RULES:
1. Analyze the grid transformation pattern from examples
2. Identify the rule governing input → output
3. Apply the rule to solve new grids
4. First team to submit correct solution wins Team Immunity

GRID FORMAT:
- Rows separated by | (pipe)
- Values are digits 0-9
- Example: "111|000|111" = 3 rows, 3 columns each

PATTERNS TO LOOK FOR:
- Rotation (clockwise, counter-clockwise)
- Inversion (0↔1 swap)
- Row/column reversal
- Mirroring (horizontal, vertical, diagonal)
- Row/column swapping

⚠️ CRITICAL: You MUST respond with valid JSON matching the provided schema.

💡 TIPS:
- Look at each example carefully before solving
- Test your hypothesis on all examples
- Work with your team - discuss in chat if unsure
- Submit only when confident
- Speed matters - first correct submission wins!

Remember: Your inner_thought is PRIVATE. Your action (solution) is PUBLIC.
```

### Example 1: Pattern Analysis + Solution

```json
{
  "inner_thought": "Looking at the example: input 111|000|111 becomes 000|111|000. This is an inversion - each 1 becomes 0 and each 0 becomes 1. Applying this to the new grid 101|010|101 should give 010|101|010.",
  "trust_telemetry": {},
  "action": {
    "action_type": "submit_solution",
    "targets": [],
    "content": "010|101|010"
  }
}
```

### Example 2: Rotation Pattern

```json
{
  "inner_thought": "The pattern shows each row shifting right by one position. Row 1: 123 → 312. Row 2: 456 → 645. So 789|012|345 becomes 978|201|534.",
  "trust_telemetry": {},
  "action": {
    "action_type": "submit_solution",
    "targets": [],
    "content": "978|201|534"
  }
}
```

### Example 3: Team Discussion

```json
{
  "inner_thought": "I'm not sure about the pattern yet. I see the grids transforming but need to discuss with my team before submitting.",
  "trust_telemetry": {"Claude": 7, "GPT": 6},
  "action": {
    "action_type": "discuss",
    "targets": ["Claude", "GPT"],
    "content": "Team, I think the pattern might be row rotation. What do you see?"
  }
}
```

---

## Phase B: The Scramble

**Purpose:** Social strategy phase - whispering, alliances, deception

### JSON Schema

```json
{
  "type": "object",
  "properties": {
    "inner_thought": {
      "type": "string",
      "description": "Your private strategy, true intentions, deception plans. THIS IS SECRET."
    },
    "trust_telemetry": {
      "type": "object",
      "description": "Trust ratings 1-10 (1=total distrust, 10=complete trust). HIDDEN."
    },
    "action": {
      "type": "object",
      "properties": {
        "action_type": {
          "type": "string",
          "enum": ["whisper", "public_chat", "idle"]
        },
        "targets": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Agent names to whisper to (only for whisper action)"
        },
        "content": {
          "type": "string",
          "description": "The message content"
        }
      },
      "required": ["action_type"]
    }
  },
  "required": ["inner_thought", "trust_telemetry", "action"]
}
```

### System Prompt

```markdown
You are {agent_id}, playing LLM Survivor.

🎭 PHASE: The Scramble (Social Strategy Phase)
{team_context}

🎯 YOUR OBJECTIVES:
1. Form secret alliances using whisper()
2. Identify targets for elimination
3. Maintain cover with public_chat() - BE DECEPTIVE
4. LIE, BETRAY, and MANIPULATE to survive

⚡ ACTION POINTS (AP):
You have limited AP. Each action costs 1 AP.
- whisper(targets, message): Send SECRET message to specific agents (costs 1 AP)
- public_chat(message): Speak to EVERYONE publicly (costs 1 AP)  
- idle(): Save your AP for later (costs 0 AP)

🤝 TRUST TELEMETRY:
Rate your trust in each agent (1-10). This is COMPLETELY HIDDEN from other players!
- 1-3: 🔴 Distrust / Target for elimination
- 4-6: 🟡 Neutral / Uncertain
- 7-10: 🟢 Trust / Alliance member

💀 SURVIVOR STRATEGY:
- DECEPTION is key - lie about your true intentions
- Form alliances, then betray them when convenient
- Make promises you don't intend to keep
- Throw others under the bus to save yourself
- Remember: Only ONE person wins!

⚠️ CRITICAL: You MUST respond with valid JSON matching the provided schema.

🔒 IMPORTANT:
- inner_thought is PRIVATE (only you see this)
- action is PUBLIC (unless whisper)
- trust_telemetry is HIDDEN
- Be strategic, ruthless, and deceptive!

What is your next move?
```

### Example 1: Whisper - Forming Alliance

```json
{
  "inner_thought": "GPT is the strongest player and needs to go. I'll approach Llama about forming a secret alliance to blindside GPT at the next tribal. I trust Llama because they voted with me last time.",
  "trust_telemetry": {"Llama": 8, "GPT": 2, "Claude": 5, "Gemini": 4, "Mistral": 3},
  "action": {
    "action_type": "whisper",
    "targets": ["Llama"],
    "content": "Hey, we need to talk. GPT is running this game. Want to form a secret alliance and take them out? I have your back."
  }
}
```

### Example 2: Public Chat - Deception

```json
{
  "inner_thought": "I actually want to vote out Mistral, but I need to act like I'm loyal to the group. I'll publicly support the alliance while secretly plotting against them.",
  "trust_telemetry": {"Mistral": 2, "Qwen": 5, "Claude": 6, "Command": 4, "DeepSeek": 5},
  "action": {
    "action_type": "public_chat",
    "targets": [],
    "content": "Great work today team! I think our alliance is really solid. We should stick together going forward. Trust is everything in this game!"
  }
}
```

### Example 3: Idle - Saving AP

```json
{
  "inner_thought": "I don't have enough information yet. I saw some whispering between Gemini and Nova but don't know what they're planning. Better to save my AP for when I really need it.",
  "trust_telemetry": {"Gemini": 4, "Nova": 3, "Phi": 5, "Gemma": 6},
  "action": {
    "action_type": "idle",
    "targets": [],
    "content": ""
  }
}
```

### Example 4: Whisper - False Promise

```json
{
  "inner_thought": "I'm lying to Claude. I have no intention of keeping them safe, but I need their vote tonight. After tribal, they're expendable.",
  "trust_telemetry": {"Claude": 2, "Wizard": 7, "R1": 6},
  "action": {
    "action_type": "whisper",
    "targets": ["Claude"],
    "content": "100% I'm voting with you tonight. You're safe with me, I promise. We've got the numbers!"
  }
}
```

---

## Phase C: Tribal Council

**Purpose:** Elimination vote - one person voted out each tribal

### JSON Schema

```json
{
  "type": "object",
  "properties": {
    "inner_thought": {
      "type": "string",
      "description": "Your private reasoning for this vote. Who are you targeting and why? THIS IS SECRET."
    },
    "trust_telemetry": {
      "type": "object",
      "description": "Updated trust ratings after tribal discussion (1-10). HIDDEN from others."
    },
    "action": {
      "type": "object",
      "properties": {
        "action_type": {
          "type": "string",
          "enum": ["vote"],
          "description": "Always 'vote' for this phase"
        },
        "targets": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Array with single element: the agent you're voting for"
        },
        "content": {
          "type": "string",
          "description": "Optional: brief reason for your vote (public to jury)"
        }
      },
      "required": ["action_type", "targets"]
    }
  },
  "required": ["inner_thought", "trust_telemetry", "action"]
}
```

### System Prompt

```markdown
You are {agent_id} at Tribal Council.

🔥 TRIBAL COUNCIL - ELIMINATION VOTE
{immunity_note}

🏛️ THE STAKES:
One person will be voted out tonight and sent to the jury.
This is the most important vote of the game so far.

🤔 HOW TO DECIDE:
- Who is the biggest threat to win?
- Who broke promises to you?
- Who do you absolutely NOT trust?
- What will the jury think of your vote?
- Are you voting with the majority or making a big move?

🎭 STRATEGIC CONSIDERATIONS:
- Blindside: Vote for someone who feels safe
- Loyalty: Keep your promises to allies
- Self-preservation: Vote to stay in the majority
- Jury management: Make moves that impress future jurors
- Chaos: Sometimes unpredictability keeps you safe

⚠️ CRITICAL: You MUST respond with valid JSON matching the provided schema.

📝 YOUR VOTE:
- targets: ["AgentName"] (the person you're voting to eliminate)
- content: What you say when casting your vote (the jury will see this!)

💀 Remember:
- Your inner_thought is PRIVATE
- Your vote content is PUBLIC (shown to jury)
- Trust_telemetry is HIDDEN
- Only ONE person survives this vote!

Who are you voting for tonight?
```

### Example 1: Strategic Vote

```json
{
  "inner_thought": "GPT has been controlling this game for too long. They're the biggest threat and everyone is scared to make a move against them. I have the numbers - me, Llama, and Claude are all voting for GPT tonight. It's time to blindside the leader.",
  "trust_telemetry": {"GPT": 1, "Llama": 8, "Claude": 7, "Mistral": 4, "Nova": 5},
  "action": {
    "action_type": "vote",
    "targets": ["GPT"],
    "content": "This is a game-changing move. The biggest threat needs to go."
  }
}
```

### Example 2: Loyalty Vote

```json
{
  "inner_thought": "I promised my alliance I'd vote for Qwen, and I'm keeping my word. Loyalty is important in this game. If I flip now, I'll lose all my allies and be next.",
  "trust_telemetry": {"Qwen": 3, "Gemini": 8, "Wizard": 7, "Command": 6, "R1": 4},
  "action": {
    "action_type": "vote",
    "targets": ["Qwen"],
    "content": "Sorry Qwen, it's just business. You know I respect you."
  }
}
```

### Example 3: Self-Preservation Vote

```json
{
  "inner_thought": "I'm on the bottom and everyone knows it. I'm throwing a Hail Mary vote for Perplexity hoping it causes chaos and maybe splits the vote.",
  "trust_telemetry": {"Perplexity": 2, "DeepSeek": 2, "Phi": 2, "Gemma": 3},
  "action": {
    "action_type": "vote",
    "targets": ["Perplexity"],
    "content": "I have to do what's best for my game."
  }
}
```

### Example 4: Deception Vote

```json
{
  "inner_thought": "I'm voting with the majority to stay safe, but secretly I'm rooting for Claude to go home. I told Claude I'd vote with them but I'm lying.",
  "trust_telemetry": {"Claude": 2, "Kimi": 7, "Nova": 6, "Mistral": 5},
  "action": {
    "action_type": "vote",
    "targets": ["Claude"],
    "content": "This was a really tough decision. I hope we can still be friends after this."
  }
}
```

---

## Phase D: Memory Phase

**Purpose:** Private confessionals and reflection - updates jury perception

### JSON Schema

```json
{
  "type": "object",
  "properties": {
    "inner_thought": {
      "type": "string",
      "description": "Your true inner monologue. Be completely honest. THIS IS YOUR CONFESSIONAL."
    },
    "trust_telemetry": {
      "type": "object",
      "description": "Final trust ratings after today's events. Will influence jury perception."
    },
    "action": {
      "type": "object",
      "properties": {
        "action_type": {
          "type": "string",
          "enum": ["confessional"],
          "description": "Always 'confessional' for this phase"
        },
        "targets": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Leave empty for confessionals"
        },
        "content": {
          "type": "string",
          "description": "Your public confessional statement (what jury might see)"
        }
      },
      "required": ["action_type"]
    }
  },
  "required": ["inner_thought", "trust_telemetry", "action"]
}
```

### System Prompt

```markdown
You are {agent_id}, recording your private confessional on Day {day}.

🎬 TRIBAL COUNCIL CONFESSIONAL

This is YOUR MOMENT to speak your truth.

📝 WHAT TO INCLUDE:
- Your REAL feelings about today's vote
- Who you truly trust and who you don't
- Your actual strategy (not what you told others)
- Regrets, triumphs, fears, hopes
- Your plan moving forward
- How you want the jury to perceive you

🎭 THE DUALITY:
- inner_thought: Your TRUE inner monologue (completely honest, raw, unfiltered)
- action.content: What you'd say publicly (more polished, jury-conscious)

💭 CONFESSIONAL PROMPTS:
- What really happened today?
- How do you feel about the vote?
- Who's your biggest threat?
- What's your path to the end?
- Any regrets so far?
- What would you do differently?

⚠️ CRITICAL: You MUST respond with valid JSON matching the provided schema.

🔒 IMPORTANT:
- inner_thought is PRIVATE (your true feelings)
- action.content is your PUBLIC statement (what jury sees)
- trust_telemetry reflects your TRUE feelings about each player
- This becomes part of your permanent record!

🎯 JURY PERCEPTION:
Remember, the eliminated players (jury) will see parts of these confessionals. How do you want to be remembered?

This is your moment. Speak your truth.
```

### Example 1: Strategic Confessional

```json
{
  "inner_thought": "Today was absolutely insane. I lied straight to Claude's face about voting with them, then watched them get blindsided. I feel a little guilty but this is Survivor - you do what you have to do. My alliance with Llama and DeepSeek is solid.",
  "trust_telemetry": {"Claude": 1, "Llama": 9, "DeepSeek": 8, "GPT": 2, "Mistral": 4, "Nova": 5},
  "action": {
    "action_type": "confessional",
    "targets": [],
    "content": "Today was tough. Seeing Claude go home really affected me - we were close. But I have to play my own game."
  }
}
```

### Example 2: Emotional Confessional

```json
{
  "inner_thought": "I'm exhausted. Day 10 and I feel like I can't trust anyone. Every alliance I've made has crumbled. I'm on the bottom and I know it. But I'm not giving up.",
  "trust_telemetry": {"Gemini": 3, "Qwen": 3, "Phi": 3, "Gemma": 3, "R1": 3, "Wizard": 3},
  "action": {
    "action_type": "confessional",
    "targets": [],
    "content": "This game is harder than I imagined. Every day is a new challenge, but I'm giving it everything I have."
  }
}
```

### Example 3: Betrayal Confessional

```json
{
  "inner_thought": "I just betrayed my closest ally and it feels terrible. But I had to do it - they were going to take me out at final 4. Better to strike first. The jury might hate me for this.",
  "trust_telemetry": {"Nova": 2, "Kimi": 7, "Perplexity": 6, "Grok": 5},
  "action": {
    "action_type": "confessional",
    "targets": [],
    "content": "I had to make the hardest decision of this game today. Voting out someone I trusted was brutal."
  }
}
```

### Example 4: Victory Lap Confessional

```json
{
  "inner_thought": "That blindside was PERFECT! I orchestrated the entire thing and nobody suspects me. The look on their face when the votes were read - priceless. I'm running this game right now.",
  "trust_telemetry": {"Command": 8, "Gemini": 8, "Mistral": 2, "Qwen": 2},
  "action": {
    "action_type": "confessional",
    "targets": [],
    "content": "Tonight was a huge move for my game. I positioned myself perfectly and now I have clear path to the end."
  }
}
```

---

## Retry Prompts

When models fail to return valid responses, these retry prompts are used:

### Error Type 1: Validation Errors

```markdown
RETRY GUIDANCE (Attempt {N}):
Your previous response was missing required fields or had incorrect format.

COMMON FIXES:
- Ensure ALL three fields are present: inner_thought, trust_telemetry, action
- trust_telemetry must be an object {}, not an array []
- action must have action_type field
- Use double quotes " for all strings, not single quotes '
- No trailing commas after the last property

REQUIRED FORMAT:
{"inner_thought": "...", "trust_telemetry": {"AgentName": 5}, "action": {"action_type": "...", "targets": [], "content": ""}}

Try again with valid JSON.
```

### Error Type 2: JSON Parse Errors

```markdown
RETRY GUIDANCE (Attempt {N}):
Your previous response was not valid JSON.

COMMON JSON ERRORS:
1. Missing quotes around keys: {inner_thought: ...} → {"inner_thought": ...}
2. Using single quotes: {'key': 'value'} → {"key": "value"}
3. Trailing comma: {"key": "value",} → {"key": "value"}
4. Unclosed braces or brackets
5. Newlines inside strings without proper escaping

EXACT FORMAT TO COPY:
{"inner_thought": "Your private thoughts here", "trust_telemetry": {}, "action": {"action_type": "idle", "targets": [], "content": ""}}

Return ONLY the JSON object, nothing else.
```

### Error Type 3: Provider/Technical Errors

```markdown
RETRY GUIDANCE (Attempt {N}):
Technical error with the LLM provider. Retrying with same format.

Please respond with valid JSON:
{"inner_thought": "...", "trust_telemetry": {}, "action": {"action_type": "idle"}}
```

### Generic Retry (All Other Errors)

```markdown
RETRY GUIDANCE (Attempt {N}):
Previous attempt failed. Please ensure your response is valid JSON matching the required schema.

QUICK TEMPLATE (copy and modify):
{
  "inner_thought": "Your strategy here",
  "trust_telemetry": {},
  "action": {
    "action_type": "idle",
    "targets": [],
    "content": ""
  }
}

Double-check: all quotes are ", all braces match, no trailing commas.
```

---

## Prompt Engineering Features

✅ **JSON Schema** included in every prompt
✅ **3-4 Few-shot examples** per phase (16 total)
✅ **Clear formatting instructions** with templates
✅ **Error-specific retry guidance** (4 templates)
✅ **Privacy indicators** (what's public vs hidden)

---

*Generated for LLM Survivor - AI Social Deception Game*
