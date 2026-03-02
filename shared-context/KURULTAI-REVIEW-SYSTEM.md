# Kurultai Review System

## Overview

Automated hourly review of Kurultai activity using:
- **6-hour rolling window** of chatlogs
- **Cloud LLM analysis** (qwen3.5-plus)
- **Meta-review** of the LLM prompt itself
- **Auto-execution** of priority actions
- **Archive** after completion

---

## Files

| File | Purpose |
|------|---------|
| `scripts/kurultai-review.sh` | Main review script |
| `scripts/kurultai-review-prompt.txt` | LLM prompt for analysis |
| `scripts/kurultai-sync.sh` | Simple sync (no chatlog analysis) |
| `scripts/kurultai-sync-review.sh` | Kublai manual review |

---

## How It Works

### Step 1: Data Collection

```bash
# Collects from past 6 hours:
- Session chatlogs (*.jsonl files)
- Agent reflections (memory/*.md)
- Git commits
- Neo4j activity
- System logs
```

### Step 2: Cloud LLM Analysis

```python
# Sends to qwen3.5-plus:
- All collected data
- Structured prompt
- Returns evidence-based analysis
```

### Step 3: Meta-Review

```python
# Reviews the LLM prompt itself:
- Was the output useful?
- What could be improved?
- Returns improved prompt version
```

### Step 4: Auto-Execute

```bash
# Kublai executes priority actions:
- Parses action items from analysis
- Executes automatically
- Logs execution status
```

### Step 5: Archive

```bash
# After 10 minutes:
- Moves sync file to archive/
- Keeps audit trail
- Cleans working directory
```

---

## Running Manually

```bash
# Run full review
./scripts/kurultai-review.sh

# Output files:
- /tmp/kurultai-review-YYYY-MM-DD-HH:MM/llm-analysis.txt
- /tmp/kurultai-review-YYYY-MM-DD-HH:MM/meta-review.txt
- shared-context/KURULTAI-SYNC-YYYY-MM-DD-HH:MM.md (archived after 10 min)
```

---

## Automating (Cron)

```bash
# Add to crontab for hourly review
0 * * * * /Users/kublai/.openclaw/agents/main/scripts/kurultai-review.sh >> /tmp/kurultai-review.log 2>&1
```

---

## Output Structure

### LLM Analysis

```markdown
## What Worked Well

- [Specific item with evidence citation]

## What Didn't Work

- [Specific item with evidence citation]

## Patterns Across Agents

[Analysis of patterns]

## Kublai Performance Review

**Promises Made vs. Completed:**
- [ ] Promise 1: Completed/Failed - [evidence]

**Blocking Issues:**
- [Blocker with evidence]

## Priority Action Items (Next Hour)

1. **[Action 1]** - [specific, actionable]
2. **[Action 2]** - [specific, actionable]
```

### Meta-Review

```markdown
## Prompt Effectiveness

- Did the prompt produce useful analysis?
- What was missing?

## Recommended Prompt Improvements

1. [Specific change]

## Improved Prompt Version

[Rewritten prompt]
```

---

## Neo4j Schema

```cypher
// KurultaiSync (one per hour)
CREATE (s:KurultaiSync {
  timestamp: datetime(),
  hour: '2026-03-02 11:00',
  attendance: 6
})

// KublaiDecision (actions taken)
CREATE (d:KublaiDecision {
  timestamp: datetime(),
  distilled_learnings: [],
  immediate_actions: [],
  llm_analysis: '...',
  auto_executed: true
})

// ProcessImprovement (from meta-review)
CREATE (pi:ProcessImprovement {
  timestamp: datetime(),
  prompt_review: '...',
  improvements_to_prompt: [],
  implemented: false
})

// Link them
CREATE (s)-[:HAS_DECISION]->(d)
CREATE (s)-[:HAS_IMPROVEMENT]->(pi)
```

---

## Privacy Considerations

**Chatlogs contain:**
- Human requests (may be sensitive)
- Agent responses
- Task details

**Current implementation:**
- Sends full chatlogs to cloud LLM
- 6-hour rolling window (limited exposure)
- Logs stored temporarily in /tmp/

**To make privacy-safe:**
1. Summarize chatlogs with local LLM first
2. Send summary (not raw logs) to cloud LLM
3. Delete raw logs after analysis

---

## Troubleshooting

### LLM Analysis Fails

```bash
# Check API configuration
export CLOUD_LLM_API_KEY="your-key"
export CLOUD_LLM_API_URL="https://api.example.com/v1/chat/completions"

# Re-run
./scripts/kurultai-review.sh
```

### Chatlogs Not Collected

```bash
# Check session files exist
ls -la /Users/kublai/.openclaw/agents/main/sessions/*.jsonl

# Check modification times
stat -f "%m %N" /Users/kublai/.openclaw/agents/main/sessions/*.jsonl
```

### Archive Not Working

```bash
# Check archive directory exists
ls -la shared-context/archive/sync/

# Check permissions
chmod 755 shared-context/archive/sync/
```

---

## Example Output

See: `/tmp/kurultai-review-2026-03-02-11:30/`

---

## Next Steps

1. **Configure API** - Set cloud LLM API key and URL
2. **Test Run** - Run manually first
3. **Automate** - Add to crontab
4. **Monitor** - Check logs for issues
5. **Iterate** - Use meta-review to improve prompt

---

*The Kurultai thinks as one. Through automated review, we improve continuously.*
