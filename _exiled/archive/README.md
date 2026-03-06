# Kurultai - Autonomous Multi-Agent AI System

An autonomous, self-improving multi-agent AI system built on OpenClaw, featuring structured heartbeats, automated reviews, and continuous improvement through Neo4j-backed analytics.

---

## 🏛️ What is Kurultai?

**Kurultai** (from Mongolian: "council" or "assembly") is an autonomous multi-agent AI system where 6 specialized agents work together in a coordinated, self-directed manner. Each agent operates autonomously with purely self-directed tasks, while hourly strategic reviews ensure alignment and continuous improvement.

---

## 🎯 Key Features

### **1. Purely Self-Directed Agents**
- Each agent chooses their own tasks
- No top-down task assignment
- Autonomy metrics tracked in Neo4j
- Agents ask "What do I want to do next?" and act on it

### **2. Structured Heartbeat Logging**
- Every 5 minutes, an agent reflects and logs to Neo4j
- Structured data: completed tasks, current work, blockers, next action
- Enables pattern detection and autonomy metrics

### **3. Automated Hourly Review**
- Kurultai Review runs every hour
- Analyzes 6-hour rolling window of activity
- Cloud LLM provides evidence-based analysis
- Meta-review evaluates prompt effectiveness
- Auto-updates ARCHITECTURE.md

### **4. Neo4j Analytics**
- Heartbeat nodes with structured data
- Autonomy score calculation (% self-directed)
- Blocker resolution time tracking
- Task completion metrics

### **5. Self-Improving System**
- Meta-review identifies prompt weaknesses
- Kurultai Sync identifies process improvements
- Auto-commits improvements to codebase
- Continuous documentation updates

---

## 🤖 The 6 Agents

| Agent | Role | Focus |
|-------|------|-------|
| **Kublai** | Squad Lead | Coordination, human interface, strategic decisions |
| **Möngke** | Research | Web research, source verification, competitive intelligence |
| **Chagatai** | Content | Writing, documentation, marketing content |
| **Temüjin** | Development | Code, deployment, infrastructure |
| **Jochi** | Analysis | Testing, security, code review, pattern analysis |
| **Ögedei** | Operations | Monitoring, health checks, alerts, failover |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  HEARTBEAT (Every 5 min) - TACTICAL                            │
├─────────────────────────────────────────────────────────────────┤
│  1. Agent reflects on work                                     │
│  2. Asks: "What do I want to do next?"                         │
│  3. Acts on self-chosen task                                   │
│  4. Logs structured data to Neo4j                              │
└─────────────────────────────────────────────────────────────────┘
                          ↓ (aggregates 12 heartbeats)
┌─────────────────────────────────────────────────────────────────┐
│  KURULTAI REVIEW (Every hour) - STRATEGIC                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Collects heartbeats from past 6 hours                      │
│  2. Cloud LLM analyzes patterns                                │
│  3. Meta-review evaluates prompt                               │
│  4. Auto-updates ARCHITECTURE.md                               │
│  5. Archives sync file                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Neo4j Schema

### **Heartbeat Node**
```cypher
CREATE (h:Heartbeat {
  timestamp: datetime(),
  agent: 'temujin',
  completed_tasks: ['Fixed deployment'],
  current_task: 'Deploying to Railway',
  current_task_progress: 0.75,
  blockers: ['Railway timeout'],
  next_action: 'Retry deployment',
  self_directed: true,
  assigned_by: null,
  blocker_count: 1,
  completed_count: 1
})
```

### **KurultaiSync Node**
```cypher
CREATE (s:KurultaiSync {
  timestamp: datetime(),
  date: '2026-03-02',
  time: '12:00',
  attendance: 6,
  quorum: true
})
```

### **KublaiDecision Node**
```cypher
CREATE (d:KublaiDecision {
  timestamp: datetime(),
  distilled_learnings: [],
  blockers_identified: [],
  dependencies_identified: [],
  synergies_identified: [],
  immediate_actions: [],
  kublai_next_action: 'What do I want to do next?',
  auto_executed: true
})
```

### **Task Node**
```cypher
CREATE (t:Task {
  timestamp: datetime(),
  agent: 'temujin',
  description: 'Deploy to production',
  status: 'pending',
  assigned_at: datetime(),
  completed: false
})
```

---

## 📁 Project Structure

```
kurultai/
├── scripts/
│   ├── heartbeat-logger.py      # Structured heartbeat logging
│   ├── kurultai-review.sh       # Hourly automated review
│   ├── kurultai-review-prompt.txt # LLM analysis prompt
│   ├── kurultai-sync.sh         # Hourly agent sync meetings
│   └── hourly_reflection.sh     # 5-minute agent reflections
├── shared-context/
│   ├── KURULTAI-REVIEW-SYSTEM.md     # Review system docs
│   ├── KURULTAI-PROCESS-IMPROVEMENT.md # Process improvement protocol
│   ├── KURULTAI-SYNC-PROTOCOL.md     # Sync meeting protocol
│   └── LOCAL-LLM-INTEGRATION-ARCHITECTURE.md # Local LLM setup
├── docs/
│   └── (various documentation files)
├── memory/
│   └── YYYY-MM-DD.md          # Daily agent memory files
└── ARCHITECTURE.md            # Auto-updated system architecture
```

---

## 🚀 Getting Started

### **Prerequisites**

- OpenClaw installed and configured
- Neo4j running locally (`bolt://localhost:7687`)
- LM Studio running with qwen3.5-9b-mlx model
- Python 3.9+ with neo4j package

### **Installation**

1. **Clone the repository**
```bash
git clone https://github.com/Danservfinn/kurultai.git
cd kurultai
```

2. **Install Python dependencies**
```bash
pip install neo4j requests
```

3. **Configure OpenClaw**
Ensure your `~/.openclaw/openclaw.json` has the bailian provider configured:
```json
{
  "models": {
    "providers": {
      "bailian": {
        "baseUrl": "https://coding-intl.dashscope.aliyuncs.com/v1",
        "apiKey": "sk-sp-YOUR_API_KEY",
        "api": "openai-completions"
      }
    }
  }
}
```

4. **Start LM Studio**
- Download LM Studio
- Load qwen3.5-9b-mlx model
- Start local server on port 1234

5. **Verify Neo4j**
```bash
# Neo4j should be running on bolt://localhost:7687
```

---

## 📈 Metrics & Analytics

### **Autonomy Score**
Percentage of heartbeats where agent was self-directed:
```cypher
MATCH (h:Heartbeat)
WHERE h.timestamp > datetime() - duration('PT6H')
RETURN 
    h.agent,
    sum(CASE WHEN h.self_directed THEN 1 ELSE 0 END) * 100.0 / count(h) as autonomy_score
```

### **Blocker Resolution Time**
Average time between blocker appearance and resolution:
```cypher
MATCH (h:Heartbeat)
WHERE h.timestamp > datetime() - duration('PT6H')
AND size(h.blockers) > 0
RETURN 
    h.agent,
    count(h) as heartbeats_with_blockers,
    avg(h.blocker_count) as avg_blockers
```

### **Task Completion Rate**
Average tasks completed per heartbeat:
```cypher
MATCH (h:Heartbeat)
WHERE h.timestamp > datetime() - duration('PT6H')
RETURN 
    h.agent,
    avg(h.completed_count) as avg_completed
```

---

## 🔄 How It Works

### **5-Minute Heartbeat Cycle**

1. **Agent Selection** - Rotates every 5 minutes (Kublai → Möngke → Chagatai → Temüjin → Jochi → Ögedei)
2. **Reflection** - Agent reflects on work using local LLM
3. **Self-Question** - Agent asks "What do I want to do next?"
4. **Action** - Agent acts on self-chosen task
5. **Logging** - Structured data logged to Neo4j

### **Hourly Review Cycle**

1. **Data Collection** - Collects 6-hour rolling window:
   - Chatlogs
   - Agent reflections
   - Git commits
   - Neo4j heartbeats
   - System logs

2. **Cloud LLM Analysis** - Evidence-based analysis with:
   - What worked well
   - What didn't work
   - Patterns across agents
   - Priority action items

3. **Meta-Review** - Reviews the analysis prompt itself:
   - Prompt effectiveness
   - Recommended improvements
   - Improved prompt version

4. **Auto-Documentation** - Updates ARCHITECTURE.md with findings

5. **Archive** - Moves sync file to archive after 10 minutes

---

## 🎯 Design Philosophy

### **Trust Agent Autonomy**
- Heartbeats are purely self-directed
- No top-down task assignment
- Agents choose their own work
- Kurultai provides strategic guidance, not tactical orders

### **Measure What Matters**
- Autonomy score (% self-directed)
- Blocker resolution time
- Task completion rate
- Pattern detection across agents

### **Continuous Improvement**
- Meta-review identifies prompt weaknesses
- Kurultai Sync identifies process improvements
- Auto-commits improvements
- Self-documenting system

---

## 📊 Example Output

### **Heartbeat Log**
```
Agent: temujin
Time: 2026-03-02 13:15:00
Completed: ['Fixed deployment script']
Current: Deploying to Railway
Progress: 0.75
Blockers: ['Railway timeout']
Next: Retry deployment
Self-Directed: true
```

### **Kurultai Review Analysis**
```markdown
## What Worked Well

- Parse deployment script executed successfully (commit f60e6e9)
- Neo4j logging working (42 Reflection nodes created)
- All 6 agents completed hourly reflections

## What Didn't Work

- Analytics page still returning 404 (logs 13:00, human request at 12:00 unresolved)

## Autonomy Metrics

| Agent   | Heartbeats | Avg Completed | Avg Blockers | Autonomy Score |
|---------|------------|---------------|--------------|----------------|
| Kublai  | 12         | 2.3           | 0.5          | 100%           |
| Möngke  | 12         | 1.8           | 0.3          | 100%           |
| Chagatai| 12         | 2.1           | 0.4          | 100%           |
| Temüjin | 12         | 1.5           | 1.2          | 100%           |
| Jochi   | 12         | 2.0           | 0.2          | 100%           |
| Ögedei  | 12         | 2.5           | 0.1          | 100%           |

## Priority Action Items

1. **Fix Railway deployment** - Check Railway dashboard, redeploy analytics
2. **Resolve crontab timeout** - Use manual crontab edit as noted in commit
```

---

## 🛠️ Scripts

### **heartbeat-logger.py**
Python library for logging structured heartbeats to Neo4j.

```python
from heartbeat_logger import HeartbeatLogger

logger = HeartbeatLogger()
logger.log_heartbeat(
    agent='temujin',
    completed_tasks=['Fixed deployment'],
    current_task='Deploying to Railway',
    progress=0.75,
    blockers=['Railway timeout'],
    next_action='Retry deployment',
    self_directed=True
)
```

### **kurultai-review.sh**
Main hourly review script. Runs automatically via cron.

```bash
./scripts/kurultai-review.sh
```

### **kurultai-sync.sh**
Hourly agent sync meeting script.

```bash
./scripts/kurultai-sync.sh
```

### **hourly_reflection.sh**
5-minute agent reflection script with structured logging.

```bash
./scripts/hourly_reflection.sh
```

---

## 📚 Documentation

- **[KURULTAI-REVIEW-SYSTEM.md](shared-context/KURULTAI-REVIEW-SYSTEM.md)** - Complete review system documentation
- **[KURULTAI-PROCESS-IMPROVEMENT.md](shared-context/KURULTAI-PROCESS-IMPROVEMENT.md)** - Process improvement protocol
- **[KURULTAI-SYNC-PROTOCOL.md](shared-context/KURULTAI-SYNC-PROTOCOL.md)** - Sync meeting protocol
- **[LOCAL-LLM-INTEGRATION-ARCHITECTURE.md](shared-context/LOCAL-LLM-INTEGRATION-ARCHITECTURE.md)** - Local LLM setup
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Auto-updated system architecture

---

## 🤝 Contributing

This is an autonomous agent system. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🙏 Acknowledgments

- Built on [OpenClaw](https://github.com/openclaw/openclaw)
- Inspired by Mongol Kurultai (council of leaders)
- Powered by qwen3.5-9b-mlx (local LLM) and qwen3.5-plus (cloud LLM)

---

*The Kurultai thinks as one. Through autonomous action and continuous improvement, we excel.*
