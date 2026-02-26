# LLM Survivor Implementation Plan

**Version:** 1.0  
**Execution Mode:** Autonomous via OpenClaw  
**Implementation Method:** Gemini CLI (multi-agent development)

---

## OpenClaw System Directive

**Primary Directive:** Build the complete, end-to-end "LLM Survivor" platform based on the Master Design Document.

**Execution Rules:**
1. Execute the 7 phases in exact sequential order. Do not skip steps.
2. Write complete, production-ready, heavily commented code.
3. Verify completion before moving to next phase.
4. Implement robust try/except blocks for all LLM API calls with strict 3-retry limit.

---

## Phase 1: Project Scaffolding & Environment

### 1.1 Initialize Directory Tree
```
llm_survivor/
├── backend/
└── frontend/
```

### 1.2 Backend Setup
**Location:** `backend/`

**requirements.txt:**
- litellm
- pydantic
- apscheduler
- fastapi
- uvicorn
- python-dotenv

**.env:**
```
OPENAI_API_KEY=placeholder
ANTHROPIC_API_KEY=placeholder
GEMINI_API_KEY=placeholder
```

### 1.3 Frontend Setup
**Location:** `frontend/`

**Command:**
```bash
npx create-next-app@latest . --typescript --tailwind --eslint --app --use-npm --yes
npm install reactflow lucide-react date-fns axios
```

---

## Phase 2: Database Initialization

**File:** `backend/database.py`

### 2.1 Database Schema

**GameState Table:**
- season_id (INTEGER)
- current_day (INTEGER)
- phase (TEXT)
- is_merged (BOOLEAN)

**Agents Table:**
- agent_id (TEXT PK)
- pseudonym (TEXT)
- model_api (TEXT)
- team_id (TEXT)
- status (TEXT)
- has_immunity (BOOLEAN)
- confessional_memory (TEXT)
- action_points (INTEGER)

**Messages Table:**
- id (INTEGER PK)
- day (INTEGER)
- sender_id (TEXT)
- receiver_ids (TEXT - JSON)
- is_public (BOOLEAN)
- inner_thought (TEXT)
- content (TEXT)
- trust_telemetry (TEXT - JSON)
- timestamp (DATETIME)

**Votes Table:**
- id (INTEGER PK)
- day (INTEGER)
- voter_id (TEXT)
- target_id (TEXT)

### 2.2 Seed Function
`seed_initial_state()`:
- GameState: day 1, phase 'challenge', is_merged False
- 16 Agents: Agent Alpha to Agent Pi
- 8 to Team_Alpha, 8 to Team_Beta
- status: 'active', action_points: 0
- Mixed model_api strings

---

## Phase 3: Core LLM Engine & Schemas

**File:** `backend/llm_engine.py`

### 3.1 Pydantic Output Schema

```python
class ActionPayload(BaseModel):
    action_type: Literal["whisper", "public_chat", "submit_arc", "cast_vote", "write_confessional", "idle"]
    targets: Optional[List[str]]
    content: str

class AgentResponse(BaseModel):
    inner_thought: str
    trust_telemetry: Dict[str, int]
    action: ActionPayload
```

### 3.2 call_agent() Function
- Use LiteLLM's response_format
- 3-retry limit for safety refusals/JSON errors
- Fallback to idle action after 3 failures

---

## Phase 4: Game Logic Modules

**Directory:** `backend/engine/`

### 4.1 phase_a_challenge.py
- Load dummy ARC grid
- Ping agents by team
- First correct submission wins immunity
- Update phase to 'scramble'

### 4.2 phase_b_scramble.py
- Assign AP: 5 to vulnerable, 2 to immune
- execute_scramble_tick(): Random agent with AP > 0
- Handle whisper → Messages table
- Deduct 1 AP per action

### 4.3 phase_c_tribal.py
- Query vulnerable agents
- Prompt for cast_vote
- Tally votes, eliminate highest
- Tie-breaker: random rock draw
- Update phase to 'memory'

### 4.4 phase_d_memory.py
- Prompt all active agents for write_confessional
- Overwrite confessional_memory
- Archive/delete today's Messages
- Increment current_day
- Reset immunities
- Update phase to 'challenge'

---

## Phase 5: API & Orchestration

### 5.1 api.py (FastAPI)
- GET /api/state endpoint
- CORS middleware for localhost:3000
- Returns: Current Day, Phase, Agents list, last 50 Messages

### 5.2 scheduler.py (APScheduler)
- 10:00 AM: phase_a_challenge
- 1:00 PM - 7:00 PM: execute_scramble_tick every 15 min
- 8:00 PM: phase_c_tribal
- 9:00 PM: phase_d_memory

**CRITICAL:** CLI flag `--fast-forward` for testing:
- Ignores real-world clock
- Executes phases sequentially with 2-second sleep

---

## Phase 6: Next.js Frontend (God View)

**Location:** `frontend/`

### 6.1 State Polling
- useEffect polling /api/state every 5 seconds
- Save to React state

### 6.2 Header Component
- Current Day, Phase
- Agent pseudonyms (grayscale if eliminated)

### 6.3 Alliance Graph (SpyShack.tsx)
- reactflow for network graph
- Whisper messages → Edges
- trust_telemetry > 5: Green edge
- trust_telemetry <= 5: Red dashed edge

### 6.4 God-Mode Feed
- Vertical scrolling feed
- inner_thought: gray italic with 🧠 icon
- Public content below

### 6.5 Tribal Theater (TribalCouncil.tsx)
- Cinematic overlay when phase == 'tribal'
- Reveal votes one by one with 4-second delay

---

## Phase 7: Validation & Dry Run

### 7.1 Execution Sequence
1. `python backend/database.py` - Seed DB
2. `uvicorn backend.api:app --port 8000 &` - Start API
3. `npm run dev &` - Start frontend
4. `python backend/scheduler.py --fast-forward` - Run simulation

### 7.2 Success Criteria
- Eliminates 1 agent
- Writes 15 confessionals
- Advances to Day 2
- No traceback errors

**Success Output:** "SYSTEM VERIFIED: LLM SURVIVOR V1 DEPLOYED."

---

## Clarifying Questions

Before implementation, need clarification on:

1. **API Keys:** Do you have OpenAI, Anthropic, and Gemini API keys ready?
2. **Models:** Which specific model versions should each agent use? (e.g., gpt-4o, claude-3-5-sonnet-20241022, etc.)
3. **ARC Tasks:** Should we use real ARC-AGI tasks or dummy grid transformations?
4. **Testing:** Do you want to run the fast-forward simulation immediately after each phase, or implement all 7 phases first then test?
5. **Directory:** Where should llm_survivor/ be created? (e.g., ~/projects/ or current workspace?)

---

**Saved:** 2026-02-25  
**Status:** Awaiting clarifications before implementation
