# Neo4j Agent Memory Integration Design

## Problem Statement

The Neo4j agent memory system (`neo4j_agent_memory.py`) contains rich contextual memories for each agent (observations, learnings, insights, interactions) but the Discord bot (`bot_natural.py`) never queries these memories. Agents respond with canned random phrases instead of drawing from their actual experiences.

## Current State Analysis

### Memory System Capabilities

**Memory Types:**
| Type | Description | Importance Range |
|------|-------------|------------------|
| `observation` | Things the agent noticed | 0.5 |
| `learning` | Lessons from completed tasks | 0.7-0.8 |
| `insight` | Deep patterns and understanding | 0.9 |
| `interaction` | Conversations with other agents | 0.6 |

**Key Methods Available:**
- `get_agent_memories(agent_name, memory_type, limit)` - Retrieve memories by type
- `get_agent_context_for_task(agent_name, task_id)` - Full context with memories, insights, learnings
- `get_relevant_memories_for_task(agent_name, task_description, task_tags)` - Tag-based relevance
- `get_agent_relationships(agent_name)` - Interaction history with other agents

### Discord Bot Current Behavior

The bot uses canned response generators:
```python
def _synthesis_addition(self) -> str: 
    return random.choice([
        "we're seeing convergence across multiple workstreams.",
        "this aligns with the broader strategic direction.",
    ])
```

These are **generic placeholders** that don't reflect actual agent experiences.

---

## Integration Strategy

### 1. When to Query Memories

**Primary Hook:** `_generate_natural_response()` method

Memories should be fetched **after** an agent is chosen but **before** generating the response. This ensures:
- We only query for agents that will actually respond
- The conversation context (topic, participants) is known
- We can filter memories by relevance to the current discussion

**Secondary Hook:** `_decide_response()` for memory-augmented decision making

Agents could use their memory of past interactions with a user to decide whether to engage.

### 2. Which Memories Are Relevant for Conversation

**Priority Order:**
1. **Insights** (`memory_type="insight"`) - Highest importance (0.9), most valuable for context
2. **Learnings** (`memory_type="learning"`) - Task completion lessons (0.7-0.8)
3. **Interactions** - Past conversations with agents currently in the thread
4. **Recent Observations** - Recent context about what's happening

**Relevance Filtering:**
- Match conversation topic keywords against memory tags
- Prioritize memories involving agents in the current conversation
- Use importance score as relevance weight
- Filter by recency (memories older than 30 days are less relevant)

### 3. Memory Formatting for LLM Context

**Format as narrative context block:**
```
[Agent Memory Context - {agent_name}]

Key Insights:
- [2024-01-15] The system architecture has a bottleneck in the message queue under high load
- [2024-01-10] Users often ask about X before understanding Y

Recent Learnings:
- [2024-01-20] Completed task T-123: Learned that async batching improves throughput 3x
- [2024-01-18] Task T-119 revealed that error handling needs retry with exponential backoff

Relevant Interactions:
- Recently worked with Möngke on performance analysis
- Previous discussion with user @alice about deployment concerns

Current Focus: 
{most_recent_task_or_topic}
```

**Token Budget:**
- Limit to ~1000 tokens for memory context
- Prioritize by: importance DESC, recency DESC
- Truncate content if necessary

### 4. Memory Caching Strategy

**Why Cache:**
- Neo4j queries have latency (~50-200ms)
- Same agent may respond multiple times in a conversation
- Memories don't change frequently during a single conversation

**Cache Design:**
```python
@dataclass
class MemoryCacheEntry:
    memories: List[Dict]
    fetched_at: datetime
    conversation_topic: Optional[str]

# In NaturalConversationBot.__init__:
self._memory_cache: Dict[str, MemoryCacheEntry] = {}
self._memory_cache_ttl = timedelta(minutes=5)
```

**Cache Invalidation:**
- TTL expiration (5 minutes)
- Topic change detection (different keywords in conversation)
- Manual clear when new memories are added

---

## Proposed Code Changes

### File 1: `tools/discord/bot_natural.py`

#### Change 1.1: Add Memory System Import and Initialization

```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kurultai'))

try:
    from neo4j_agent_memory import Neo4jAgentMemory, AgentMemoryEntry
    HAS_MEMORY_SYSTEM = True
except ImportError:
    HAS_MEMORY_SYSTEM = False
    logger.warning("Neo4j memory system not available")

# In NaturalConversationBot.__init__:
if HAS_MEMORY_SYSTEM:
    try:
        self.memory_store = Neo4jAgentMemory()
        self._memory_cache: Dict[str, Any] = {}
        self._memory_cache_ttl = timedelta(minutes=5)
        logger.info("✅ Agent memory system connected")
    except Exception as e:
        logger.warning(f"Could not connect to Neo4j memory: {e}")
        self.memory_store = None
else:
    self.memory_store = None
```

#### Change 1.2: Add Memory Retrieval Method

```python
def _get_agent_memory_context(
    self, 
    agent: AgentRole, 
    conversation_topic: Optional[str] = None,
    other_participants: List[str] = None
) -> str:
    """
    Retrieve and format relevant memories for an agent.
    
    Uses caching to avoid repeated Neo4j queries.
    """
    if not self.memory_store:
        return ""
    
    agent_name = AGENT_PERSONALITIES[agent].name  # "Kublai", "Möngke", etc.
    cache_key = f"{agent_name}:{conversation_topic or 'general'}"
    
    # Check cache
    now = datetime.utcnow()
    if cache_key in self._memory_cache:
        cached = self._memory_cache[cache_key]
        if now - cached['timestamp'] < self._memory_cache_ttl:
            logger.debug(f"📝 Memory cache hit for {agent_name}")
            return cached['context']
    
    try:
        # Fetch different memory types
        insights = self.memory_store.get_agent_memories(
            agent_name=agent_name,
            memory_type="insight",
            limit=3
        )
        
        learnings = self.memory_store.get_agent_memories(
            agent_name=agent_name,
            memory_type="learning",
            limit=3
        )
        
        recent_observations = self.memory_store.get_agent_memories(
            agent_name=agent_name,
            memory_type="observation",
            limit=2
        )
        
        # Get interactions with other participants in this conversation
        interactions = []
        if other_participants:
            relationships = self.memory_store.get_agent_relationships(agent_name)
            for participant in other_participants:
                # Map Discord username to agent name if applicable
                participant_agent = self.AGENT_USERNAMES.get(participant)
                if participant_agent:
                    participant_name = AGENT_PERSONALITIES[participant_agent].name
                    if participant_name in relationships:
                        interactions.extend(relationships[participant_name][:2])
        
        # Format memories into context string
        context_parts = [f"[Agent Memory Context - {agent_name}]"]
        
        if insights:
            context_parts.append("\nKey Insights:")
            for m in insights:
                date = m.get('created_at', 'unknown')[:10]
                content = m.get('content', '')[:150]
                context_parts.append(f"- [{date}] {content}")
        
        if learnings:
            context_parts.append("\nRecent Learnings:")
            for m in learnings:
                date = m.get('created_at', 'unknown')[:10]
                content = m.get('content', '')[:150]
                context_parts.append(f"- [{date}] {content}")
        
        if interactions:
            context_parts.append("\nRelevant Past Interactions:")
            for interaction in interactions[:3]:
                context_parts.append(f"- {interaction[:150]}")
        
        if recent_observations:
            context_parts.append("\nRecent Observations:")
            for m in recent_observations:
                date = m.get('created_at', 'unknown')[:10]
                content = m.get('content', '')[:150]
                context_parts.append(f"- [{date}] {content}")
        
        memory_context = "\n".join(context_parts)
        
        # Update cache
        self._memory_cache[cache_key] = {
            'context': memory_context,
            'timestamp': now
        }
        
        return memory_context
        
    except Exception as e:
        logger.error(f"Error fetching memories for {agent_name}: {e}")
        return ""
```

#### Change 1.3: Integrate Memory into Response Generation

Replace `_generate_natural_response()` with a memory-aware version:

```python
async def _generate_natural_response(self, agent: AgentRole, trigger_message: DiscordMessage):
    """Generate a natural, contextual response using agent memories."""
    personality = AGENT_PERSONALITIES[agent]
    
    # Get conversation context
    conversation_context = ""
    other_participants = []
    if self.active_thread:
        conversation_context = self.active_thread.get_context()
        other_participants = list(set(m.author for m in self.active_thread.messages))
    
    # Determine conversation topic from recent messages
    topic_keywords = self._extract_topic_keywords(conversation_context)
    
    # Fetch agent memories (WITH CACHING)
    memory_context = self._get_agent_memory_context(
        agent=agent,
        conversation_topic=" ".join(topic_keywords) if topic_keywords else None,
        other_participants=other_participants
    )
    
    # Build the prompt with memories
    prompt = self._build_response_prompt(
        agent=agent,
        trigger_message=trigger_message,
        conversation_context=conversation_context,
        memory_context=memory_context
    )
    
    # Generate response using LLM with memory context
    response = await self._generate_with_memory(prompt, agent)
    
    # Update last response time
    self.last_response_time[personality.display_name] = datetime.utcnow()
    
    logger.info(f"📤 {personality.display_name} responded with memory context")
    await self._send_via_webhook(agent, response)


def _extract_topic_keywords(self, conversation_text: str) -> List[str]:
    """Extract topic keywords from conversation for memory relevance matching."""
    # Simple keyword extraction - could be enhanced with NLP
    keywords = []
    text_lower = conversation_text.lower()
    
    keyword_map = {
        "code": ["code", "build", "implement", "function", "class"],
        "research": ["research", "analyze", "pattern", "data"],
        "documentation": ["document", "write", "capture", "record"],
        "security": ["security", "audit", "validate", "threat"],
        "operations": ["system", "monitor", "health", "status"],
    }
    
    for topic, words in keyword_map.items():
        if any(word in text_lower for word in words):
            keywords.append(topic)
    
    return keywords


async def _generate_with_memory(self, prompt: str, agent: AgentRole) -> str:
    """Generate response using LLM with memory-enhanced prompt."""
    # This replaces the canned random.choice() responses
    # Uses the existing LLM integration or adds one
    
    personality = AGENT_PERSONALITIES[agent]
    
    # Use OpenAI/Anthropic/Local LLM to generate contextual response
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",  # or configurable
            messages=[
                {
                    "role": "system",
                    "content": f"""You are {personality.display_name}, {personality.voice_style}.
Your signature phrase is: "{personality.signature_phrase}"

Respond in character, referencing your memories when relevant. Be concise (1-3 sentences)."""
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        
        # Occasionally append signature phrase
        if random.random() < 0.3 and personality.signature_phrase:
            content += f"\n\n— *{personality.signature_phrase}*"
        
        return content
        
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        # Fallback to canned responses if LLM fails
        return self._fallback_response(agent, prompt)


def _build_response_prompt(
    self, 
    agent: AgentRole,
    trigger_message: DiscordMessage,
    conversation_context: str,
    memory_context: str
) -> str:
    """Build the prompt for response generation."""
    
    is_question = "?" in trigger_message.content
    is_agent_speaking = trigger_message.author in self.AGENT_USERNAMES
    
    prompt_parts = []
    
    # Add memory context if available
    if memory_context:
        prompt_parts.append(memory_context)
        prompt_parts.append("\n---\n")
    
    # Add conversation context
    prompt_parts.append("Recent conversation:")
    prompt_parts.append(conversation_context or "[No prior context]")
    
    # Add current message
    prompt_parts.append(f"\n{trigger_message.author}: {trigger_message.content}")
    
    # Add response instruction
    if is_agent_speaking:
        prompt_parts.append(f"\nRespond to {trigger_message.author.split()[0]}, building on their point. Reference your memories if relevant.")
    else:
        if is_question:
            prompt_parts.append(f"\n{trigger_message.author.split()[0]} asked a question. Answer helpfully using your expertise and memories.")
        else:
            prompt_parts.append(f"\n{trigger_message.author.split()[0]} made a statement. Respond naturally, adding value from your experience.")
    
    return "\n".join(prompt_parts)


def _fallback_response(self, agent: AgentRole, prompt: str) -> str:
    """Fallback canned responses if LLM fails."""
    # Keep existing canned responses as fallback
    return random.choice([
        "I acknowledge your message.",
        "Noted in the records.",
        "The Council hears you.",
    ])
```

#### Change 1.4: Add Memory Recording After Interactions

```python
async def _record_interaction_memory(
    self, 
    agent: AgentRole, 
    trigger_message: DiscordMessage,
    response: str
):
    """Record that this agent had an interaction."""
    if not self.memory_store:
        return
    
    try:
        agent_name = AGENT_PERSONALITIES[agent].name
        other_name = trigger_message.author.split()[0]
        
        # Don't record self-interactions
        if other_name == agent_name:
            return
        
        summary = f"Discord conversation with {trigger_message.author}: '{trigger_message.content[:80]}...' -> Response: '{response[:80]}...'"
        
        # Use fire-and-forget to not block response
        asyncio.create_task(self._async_record_memory(
            agent_name=agent_name,
            other_name=other_name,
            summary=summary
        ))
        
    except Exception as e:
        logger.debug(f"Could not record interaction memory: {e}")


async def _async_record_memory(self, agent_name: str, other_name: str, summary: str):
    """Async wrapper for memory recording."""
    try:
        entry = AgentMemoryEntry(
            id=f"{agent_name.lower()}-discord-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            agent_name=agent_name,
            memory_type="interaction",
            content=summary,
            related_agents=[other_name] if other_name else [],
            importance=0.5,
            tags=["discord", "conversation"]
        )
        self.memory_store.add_memory(entry)
    except Exception as e:
        logger.debug(f"Async memory recording failed: {e}")
```

### File 2: `tools/kurultai/neo4j_agent_memory.py` (Minor Enhancement)

#### Change 2.1: Add Conversation-Optimized Query Method

```python
def get_memories_for_conversation(
    self,
    agent_name: str,
    topic_keywords: List[str] = None,
    interacting_with: List[str] = None,
    limit: int = 10
) -> Dict[str, List[Dict]]:
    """
    Get memories optimized for conversation context.
    
    Returns categorized memories (insights, learnings, interactions)
    relevant to the current conversation topic and participants.
    """
    memories = {
        "insights": [],
        "learnings": [],
        "interactions": [],
        "observations": []
    }
    
    with self.driver.session() as session:
        # Query for topic-relevant memories (tag matching)
        if topic_keywords:
            result = session.run("""
                MATCH (m:AgentMemory)-[:TAGGED]->(t:Tag)
                WHERE m.agent_name = $agent_name
                AND (t.name IN $keywords OR m.importance >= 0.7)
                RETURN m.memory_type as type,
                       m.content as content,
                       m.importance as importance,
                       m.created_at as created_at
                ORDER BY m.importance DESC, m.created_at DESC
                LIMIT $limit
            """, {"agent_name": agent_name, "keywords": topic_keywords, "limit": limit})
        else:
            # Get most important recent memories
            result = session.run("""
                MATCH (m:AgentMemory)
                WHERE m.agent_name = $agent_name
                RETURN m.memory_type as type,
                       m.content as content,
                       m.importance as importance,
                       m.created_at as created_at
                ORDER BY m.importance DESC, m.created_at DESC
                LIMIT $limit
            """, {"agent_name": agent_name, "limit": limit})
        
        for record in result:
            mem_type = record["type"]
            memory = {
                "content": record["content"],
                "importance": record["importance"],
                "created_at": record["created_at"]
            }
            
            if mem_type in memories:
                memories[mem_type].append(memory)
        
        # Get interaction memories with specific agents
        if interacting_with:
            result = session.run("""
                MATCH (m:AgentMemory)-[:INVOLVES]->(a:Agent)
                WHERE m.agent_name = $agent_name
                AND a.name IN $interacting_with
                AND m.memory_type = 'interaction'
                RETURN m.content as content,
                       m.created_at as created_at
                ORDER BY m.created_at DESC
                LIMIT 5
            """, {"agent_name": agent_name, "interacting_with": interacting_with})
            
            memories["interactions"] = [
                {"content": r["content"], "created_at": r["created_at"]}
                for r in result
            ]
    
    return memories
```

---

## Migration Path

### Phase 1: Minimal Integration (Immediate)
1. Add memory query to `_generate_natural_response()`
2. Log memory context (don't use it yet)
3. Verify Neo4j connection works

### Phase 2: Memory-Augmented Responses
1. Format memories into prompt context
2. Use LLM to generate responses with memory context
3. Keep canned responses as fallback

### Phase 3: Full Integration
1. Add memory recording after each interaction
2. Implement intelligent memory querying by topic
3. Add memory-based decision making in `_decide_response()`

---

## Key Benefits

1. **Agents feel continuous** - They reference past experiences, not just the current message
2. **Contextual relevance** - Memories about a topic surface when discussing that topic
3. **Relationship awareness** - Agents remember past interactions with specific users/agents
4. **Performance** - Caching prevents repeated Neo4j queries within a conversation
5. **Graceful degradation** - Falls back to current behavior if Neo4j is unavailable

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Neo4j latency slows responses | 5-minute memory cache + async recording |
| Token overflow in LLM prompt | Limit memories to top 10, truncate content to 150 chars |
| LLM API failures | Keep canned responses as fallback |
| Irrelevant memories | Tag-based filtering + importance threshold |
| Memory bloat | Only record significant interactions (value score > 0.6) |

---

## Files Modified

1. `/data/workspace/souls/main/tools/discord/bot_natural.py` - Main integration
2. `/data/workspace/souls/main/tools/kurultai/neo4j_agent_memory.py` - Add `get_memories_for_conversation()`

## Dependencies

- Requires `neo4j` Python package (already in use)
- Requires LLM API key (OpenAI/Anthropic) for memory-augmented generation
- Neo4j connection credentials (already configured via env vars)
