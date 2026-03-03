# Multi-Agent Gemini CLI Architecture
**Analysis:** Can 6 agents have their own Gemini CLI instances?

---

## TL;DR: YES, with Context Separation

Since you have **ONE Google account** (d@kurult.ai), we cannot create 6 fully separate authenticated Gemini CLIs.

**BUT** we can create **6 separate contexts** with:
- ✅ Individual project workspaces
- ✅ Agent-specific settings
- ✅ Separate conversation histories
- ✅ Isolated working directories

---

## Architecture Options

### Option 1: Separate Config Directories (RECOMMENDED)

Create isolated environments for each agent:

```
~/.gemini-kublai/      # Kublai's context
~/.gemini-mongke/      # Möngke's context
~/.gemini-chagatai/    # Chagatai's context
~/.gemini-temujin/     # Temüjin's context
~/.gemini-jochi/       # Jochi's context
~/.gemini-ogedei/      # Ögedei's context
```

**Pros:**
- ✅ True isolation
- ✅ Separate history/settings per agent
- ✅ Can run simultaneously

**Cons:**
- ⚠️ Shares same Google account
- ⚠️ More disk usage

### Option 2: Project-Based Contexts

Use `.gemini.json` in each agent's workspace:

```
~/.openclaw/agents/main/.gemini.json          # Kublai
~/.openclaw/agents/researcher/.gemini.json    # Möngke
~/.openclaw/agents/writer/.gemini.json        # Chagatai
~/.openclaw/agents/developer/.gemini.json     # Temüjin
~/.openclaw/agents/analyst/.gemini.json       # Jochi
~/.openclaw/agents/ops/.gemini.json           # Ögedei
```

**Pros:**
- ✅ Native Gemini CLI project support
- ✅ Cleaner architecture
- ✅ Shared auth, separate contexts

**Cons:**
- ⚠️ Less isolation than Option 1

### Option 3: Session-Based Isolation

Use the CLI's session management:

```bash
gemini --resume kublai-session
gemini --resume mongke-session
```

**Pros:**
- ✅ Built-in to CLI
- ✅ Easy to implement

**Cons:**
- ⚠️ Manual session management
- ⚠️ Can't run truly parallel

---

## Recommended Implementation: Hybrid Approach

### Phase 1: Project-Based Contexts (Quick Setup)

Each agent gets their own workspace with `.gemini.json`:

```json
{
  "model": {
    "name": "gemini-3.1-pro-preview"
  },
  "agent": {
    "name": "Kublai",
    "role": "Squad Lead",
    "specialization": "orchestration"
  }
}
```

### Phase 2: Separate Config Directories (Full Isolation)

Use `GEMINI_HOME` environment variable:

```bash
# Kublai's CLI
export GEMINI_HOME=~/.gemini-kublai
gemini

# Möngke's CLI
export GEMINI_HOME=~/.gemini-mongke
gemini
```

### Phase 3: API Integration (Best for Automation)

Create a bridge that routes agent tasks to appropriate Gemini context:

```python
class AgentGeminiManager:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.gemini_home = f"~/.gemini-{agent_id}"
        self.workspace = f"~/.openclaw/agents/{agent_id}"
    
    def execute(self, prompt: str) -> str:
        # Set agent-specific context
        env = os.environ.copy()
        env['GEMINI_HOME'] = self.gemini_home
        env['GEMINI_AGENT'] = self.agent_id
        
        # Run gemini with agent context
        result = subprocess.run(
            ['gemini', '-p', prompt],
            env=env,
            cwd=self.workspace,
            capture_output=True,
            text=True
        )
        return result.stdout
```

---

## Implementation Script

Here's how to set this up:

```bash
#!/bin/bash
# Setup multi-agent Gemini CLI

AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")

for agent in "${AGENTS[@]}"; do
    echo "Setting up Gemini CLI for $agent..."
    
    # Create config directory
    mkdir -p ~/.gemini-$agent
    
    # Copy base config
    cp ~/.gemini/settings.json ~/.gemini-$agent/
    
    # Create agent-specific config
    cat > ~/.gemini-$agent/agent-config.json <<EOF
{
  "agent": {
    "id": "$agent",
    "workspace": "~/.openclaw/agents/$agent"
  }
}
EOF
    
    # Create project config in agent workspace
    mkdir -p ~/.openclaw/agents/$agent
    cat > ~/.openclaw/agents/$agent/.gemini.json <<EOF
{
  "model": {
    "name": "gemini-3.1-pro-preview"
  },
  "agent": "$agent"
}
EOF
    
    echo "✅ $agent configured"
done

echo ""
echo "All 6 agents have their own Gemini CLI context!"
```

---

## Usage Examples

### Direct CLI Usage

```bash
# Kublai manages the squad
export GEMINI_HOME=~/.gemini-kublai
gemini -p "Review task assignments for today"

# Möngke conducts research
export GEMINI_HOME=~/.gemini-mongke
gemini -p "Research async patterns in Python"

# Temüjin writes code
export GEMINI_HOME=~/.gemini-temujin
gemini -p "Generate FastAPI endpoint for agent registry"
```

### Via API Bridge

```python
# From Kurultai agent
from tools.kurultai.agent_gemini import get_agent_gemini

# Each agent gets their own instance
kublai_gemini = get_agent_gemini("kublai")
mongke_gemini = get_agent_gemini("mongke")
temujin_gemini = get_agent_gemini("temujin")

# Use independently
result = kublai_gemini.query("Summarize today's operations")
research = mongke_gemini.query("Find papers on distributed AI")
code = temujin_gemini.query("Write a Redis connection pool")
```

---

## Benefits of Multi-Agent Setup

1. **Isolation:** Each agent has own history/context
2. **Specialization:** Agent-specific prompts/settings
3. **Parallelism:** Can run simultaneously
4. **Audit Trail:** Separate logs per agent
5. **Workspace Integration:** Each tied to agent's directory

---

## Limitations

- **Shared Account:** All use d@kurult.ai (same rate limits)
- **Not True Multi-User:** Same underlying auth
- **Storage:** 6x config storage (minimal)

---

## Recommendation

**YES, implement Option 2 (Project-Based) + Option 3 (API Bridge)**

This gives each agent their own "Gemini CLI" while being practical to maintain.

**Want me to implement this multi-agent Gemini CLI setup now?**
