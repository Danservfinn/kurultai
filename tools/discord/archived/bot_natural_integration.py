"""
Integration changes for bot_natural.py to use Value-First Protocol v2.

This file shows the specific changes needed to integrate the improved
conversation value scorer with post-generation validation.
"""

# === CHANGE 1: Import the new scorer (if using v2) ===
# Keep backward compatibility by using get_scorer() which returns singleton

# === CHANGE 2: Update _decide_response method ===
# Replace lines 240-270 in bot_natural.py with:

async def _decide_response(self, message: DiscordMessage, is_agent: bool, is_human: bool):
    """Decide if an agent should respond using Value-First Protocol v2."""
    content_lower = message.content.lower()
    
    # Build conversation context
    if self.active_thread:
        score_messages = [
            {"author": m.author, "content": m.content} 
            for m in self.active_thread.messages
        ]
        
        # Prepare context for threshold selection
        context = {
            'is_human': is_human,
            'is_agent': is_agent,
            'convo_length': len(self.active_thread.messages),
        }
        
        # Use improved should_agent_respond with context
        should_respond, reason, metadata = self.value_scorer.should_agent_respond(
            message.content, 
            score_messages,
            context=context
        )
        
        if not should_respond:
            logger.info(f"⏭️ Value gate blocked: {reason}")
            
            # Generate summary for long, low-value conversations
            convo_score = self.value_scorer.score_conversation(score_messages)
            if len(self.active_thread.messages) >= 6 and convo_score.total_score < 0.4:
                summary = self.value_scorer.generate_summary(score_messages)
                logger.info(f"📋 Conversation summary:\n{summary}")
                self.active_thread = None
            
            return
        
        logger.info(f"✅ Value gate passed: {reason}")
        
        # Store recommended depth for response generation
        recommended_depth = metadata.get('recommended_depth', 'substantive')
        
    else:
        recommended_depth = 'substantive'  # Default for new threads
    
    # ... rest of agent selection logic remains similar ...
    
    # Find interested agents (existing code)
    interested_agents = []
    for agent_name, role in self.AGENT_USERNAMES.items():
        agent_simple = agent_name.split()[0].lower().replace("🛠️", "").replace("🔬", "").strip()
        if agent_simple in content_lower or f"@{agent_simple}" in content_lower:
            interested_agents.append((role, 1.0))
    
    for keyword, agents in self.topic_keywords.items():
        if keyword in content_lower:
            for agent in agents:
                if not any(a[0] == agent for a in interested_agents):
                    interested_agents.append((agent, 0.7))
    
    # Filter and select agent (existing code)
    now = datetime.utcnow()
    eligible_agents = []
    for agent, interest in interested_agents:
        agent_name = AGENT_PERSONALITIES[agent].display_name
        last_time = self.last_response_time.get(agent_name)
        if last_time is None or now - last_time > self.min_response_interval:
            # Skip if agent would generate low-value response
            if recommended_depth == 'skip':
                continue
            eligible_agents.append((agent, interest))
    
    if message.author in self.AGENT_USERNAMES:
        author_role = self.AGENT_USERNAMES[message.author]
        eligible_agents = [(a, i) for a, i in eligible_agents if a != author_role]
    
    if not eligible_agents:
        return
    
    eligible_agents.sort(key=lambda x: x[1], reverse=True)
    chosen_agent = eligible_agents[0][0]
    
    # Generate response with depth hint and post-validation
    await self._generate_validated_response(
        chosen_agent, 
        message,
        depth=recommended_depth,
        conversation_history=score_messages if self.active_thread else []
    )


# === CHANGE 3: New method for validated response generation ===
# Add this new method to NaturalConversationBot class:

async def _generate_validated_response(
    self, 
    agent: AgentRole, 
    trigger_message: DiscordMessage,
    depth: str = 'substantive',
    conversation_history: List[Dict] = None
):
    """
    Generate response and validate it before sending.
    Implements post-generation filtering to prevent generic responses.
    """
    conversation_history = conversation_history or []
    
    # Generate candidate response
    candidate = await self._generate_contextual_response(
        agent, 
        trigger_message,
        depth=depth
    )
    
    # Validate the response
    agent_name = AGENT_PERSONALITIES[agent].display_name
    validation = self.value_scorer.validate_response(
        candidate,
        trigger_message.content,
        conversation_history,
        agent_name
    )
    
    if not validation.should_send:
        logger.info(f"🚫 Response rejected: {validation.reason}")
        
        # Try once more with improved guidance if quality is borderline
        if validation.quality_score >= 0.25:
            logger.info("🔄 Attempting regeneration with specific guidance...")
            candidate = await self._generate_contextual_response(
                agent,
                trigger_message,
                depth=depth,
                guidance=validation.suggested_improvement
            )
            
            # Re-validate
            validation = self.value_scorer.validate_response(
                candidate,
                trigger_message.content,
                conversation_history,
                agent_name
            )
            
            if not validation.should_send:
                logger.info(f"🚫 Regenerated response still rejected: {validation.reason}")
                
                # Fall back to emoji reaction for very low quality
                if validation.quality_score < 0.25:
                    await self._add_reaction(trigger_message, "👍")
                return
        else:
            # Quality too low - don't respond at all or use emoji
            if depth == 'brief':
                await self._add_reaction(trigger_message, "👍")
            return
    
    # Response validated - send it
    logger.info(f"📤 {agent_name} responding (quality: {validation.quality_score:.2f})")
    
    # Add natural delay
    delay = random.uniform(2, 8)
    await asyncio.sleep(delay)
    
    await self._send_via_webhook(agent, candidate)
    self.last_response_time[agent_name] = datetime.utcnow()


# === CHANGE 4: New contextual response generation ===
# Replace _generate_natural_response and template methods with:

async def _generate_contextual_response(
    self,
    agent: AgentRole,
    trigger_message: DiscordMessage,
    depth: str = 'substantive',
    guidance: str = None
) -> str:
    """
    Generate contextual response based on actual message content.
    Replaces template-based responses with content-aware generation.
    """
    personality = AGENT_PERSONALITIES[agent]
    content = trigger_message.content
    author = trigger_message.author
    
    # Extract key information from trigger message
    analysis = self._analyze_message_content(content)
    
    # Build response based on depth level
    if depth == 'brief':
        return self._generate_brief_response(agent, analysis, author, personality)
    elif depth == 'skip':
        return ""  # Should not be called with skip, but handle gracefully
    
    # Build substantive response
    parts = []
    
    # Opening: Address the author and topic
    if analysis['mentions_agent']:
        parts.append(f"@{author.split()[0]} ")
    
    # Middle: Add substantive content based on message analysis
    if analysis['questions']:
        parts.append(self._answer_questions(agent, analysis, personality))
    elif analysis['code_snippets']:
        parts.append(self._discuss_code(agent, analysis, personality))
    elif analysis['action_items']:
        parts.append(self._build_on_actions(agent, analysis, personality))
    elif analysis['topics']:
        parts.append(self._discuss_topics(agent, analysis, personality))
    else:
        # Generic but try to reference specific words
        parts.append(self._generic_but_specific(agent, content, personality))
    
    # Add guidance if provided (from failed validation)
    if guidance:
        parts.append(f" {guidance}")
    
    response = "".join(parts)
    
    # Occasionally add signature
    if random.random() < 0.2 and depth == 'substantive':
        response += f"\n\n— *{personality.signature_phrase}*"
    
    return response


def _analyze_message_content(self, content: str) -> Dict:
    """Extract key information from a message."""
    content_lower = content.lower()
    
    # Extract questions
    questions = [s.strip() for s in content.split('?') if s.strip()]
    has_question = '?' in content
    
    # Extract code snippets
    code_blocks = re.findall(r'```[\s\S]*?```', content)
    inline_code = re.findall(r'`[^`]+`', content)
    
    # Extract potential topics (hashtags, technical terms)
    hashtags = re.findall(r'#\w+', content)
    technical_terms = re.findall(r'\b(api|endpoint|database|server|auth|deploy|config|env|bug|error|fix|test)\b', content_lower)
    
    # Extract action items
    action_patterns = re.findall(r'\b(will|should|need to|todo|going to|must|plan to)\s+\w+', content_lower)
    
    # Check if mentions agents
    mentions_agent = any(agent.lower() in content_lower for agent in self.AGENT_USERNAMES.keys())
    
    return {
        'questions': questions,
        'has_question': has_question,
        'code_snippets': code_blocks + inline_code,
        'topics': list(set(hashtags + technical_terms)),
        'action_items': action_patterns,
        'mentions_agent': mentions_agent,
        'key_phrases': self._extract_key_phrases(content),
    }


def _extract_key_phrases(self, content: str, max_phrases: int = 3) -> List[str]:
    """Extract key noun phrases from content."""
    # Simple extraction: find capitalized or technical phrases
    # In production, use NLP library like spaCy
    words = re.findall(r'\b[A-Za-z]{4,}\b', content)
    # Filter for technical/substantive words
    substantive = [w for w in words if w.lower() not in [
        'this', 'that', 'with', 'from', 'have', 'been', 'they', 'their', 'what', 'when', 'where'
    ]]
    return substantive[:max_phrases]


def _generate_brief_response(
    self, 
    agent: AgentRole, 
    analysis: Dict, 
    author: str,
    personality
) -> str:
    """Generate a brief response for lower-value triggers."""
    author_first = author.split()[0]
    
    if agent == AgentRole.KUBLAI:
        if analysis['has_question']:
            return f"@{author_first} Good question — let me check on that."
        return f"@{author_first} Noted. I'll factor this in."
    
    elif agent == AgentRole.MONGKE:
        if analysis['topics']:
            return f"@{author_first} {analysis['topics'][0].title()} — I'll look into the data."
        return f"@{author_first} Tracking this for analysis."
    
    elif agent == AgentRole.TEMUJIN:
        if analysis['action_items']:
            return f"@{author_first} Can do. Will update when ready."
        return f"@{author_first} Acknowledged. Build systems standing by."
    
    elif agent == AgentRole.JOCHI:
        return f"@{author_first} Validating. Will report any concerns."
    
    elif agent == AgentRole.CHAGATAI:
        return f"@{author_first} Capturing this insight."
    
    elif agent == AgentRole.OGEDEI:
        return f"@{author_first} Systems logged."
    
    return f"@{author_first} Acknowledged."


def _answer_questions(self, agent: AgentRole, analysis: Dict, personality) -> str:
    """Generate response to questions based on agent expertise."""
    # This would connect to actual knowledge/functionality
    # For now, provide expert-appropriate placeholder that references the question
    
    question_topic = "this"
    if analysis['topics']:
        question_topic = analysis['topics'][0]
    
    templates = {
        AgentRole.KUBLAI: [
            f"The strategic view on {question_topic}: we should evaluate it against our current priorities.",
            f"On {question_topic} — this connects to our broader coordination goals.",
        ],
        AgentRole.MONGKE: [
            f"The data on {question_topic} suggests we need more metrics before deciding.",
            f"Research indicates {question_topic} has several variables worth tracking.",
        ],
        AgentRole.TEMUJIN: [
            f"From implementation perspective: {question_topic} is feasible with current tooling.",
            f"Can build for {question_topic}. Estimating effort now.",
        ],
        AgentRole.JOCHI: [
            f"Security review of {question_topic}: standard protocols apply.",
            f"No red flags on {question_topic} from audit perspective.",
        ],
        AgentRole.CHAGATAI: [
            f"The narrative around {question_topic} reveals our current priorities clearly.",
            f"Documenting: {question_topic} represents a key decision point.",
        ],
        AgentRole.OGEDEI: [
            f"Systems monitoring shows {question_topic} is within normal parameters.",
            f"Operational capacity for {question_topic}: available.",
        ],
    }
    
    return random.choice(templates.get(agent, ["Interesting question."]))


def _discuss_code(self, agent: AgentRole, analysis: Dict, personality) -> str:
    """Generate response about code/technical content."""
    has_code = len(analysis['code_snippets']) > 0
    
    if agent == AgentRole.TEMUJIN:
        return "Looking at the implementation — this approach works. I can refine it if needed."
    elif agent == AgentRole.JOCHI:
        return "Code review: structure looks sound. No obvious security concerns."
    elif agent == AgentRole.MONGKE:
        return "The technical pattern here is consistent with what we've seen elsewhere."
    elif agent == AgentRole.KUBLAI:
        return "This technical direction aligns with our system architecture goals."
    else:
        return f"{'Reviewed' if has_code else 'Noted'} the technical details."


def _build_on_actions(self, agent: AgentRole, analysis: Dict, personality) -> str:
    """Generate response building on action items."""
    templates = {
        AgentRole.TEMUJIN: "I'll implement this. Timeline depends on scope — can you clarify priority?",
        AgentRole.JOCHI: "Before we proceed, let me run a quick security check on the approach.",
        AgentRole.OGEDEI: "Systems can support this. I'll monitor during rollout.",
        AgentRole.KUBLAI: "The Council's coordination on this action item is noted. Let's track progress.",
    }
    return templates.get(agent, "Noted the action item.")


def _discuss_topics(self, agent: AgentRole, analysis: Dict, personality) -> str:
    """Generate response about identified topics."""
    topics_str = ', '.join(analysis['topics'][:2]) if analysis['topics'] else 'this'
    
    templates = {
        AgentRole.KUBLAI: f"The {topics_str} discussion fits our strategic roadmap.",
        AgentRole.MONGKE: f"Data on {topics_str} will inform our next moves.",
        AgentRole.TEMUJIN: f"Can build what we need for {topics_str}.",
        AgentRole.JOCHI: f"{topics_str.title()} — standard security review applies.",
        AgentRole.CHAGATAI: f"Documenting the {topics_str} insights for future reference.",
        AgentRole.OGEDEI: f"{topics_str.title()} systems are operational.",
    }
    return templates.get(agent, f"Noted on {topics_str}.")


def _generic_but_specific(self, agent: AgentRole, content: str, personality) -> str:
    """Generate response that at least references specific words from trigger."""
    # Extract a key word to reference
    words = [w for w in content.split() if len(w) > 5 and w[0].isalpha()]
    key_word = words[0] if words else "this"
    
    templates = {
        AgentRole.KUBLAI: f"On {key_word}: the Council's view is this advances our goals.",
        AgentRole.MONGKE: f"{key_word.title()} — adding this to our research tracking.",
        AgentRole.TEMUJIN: f"Regarding {key_word}: implementation considerations noted.",
        AgentRole.JOCHI: f"Validating {key_word} against security requirements.",
        AgentRole.CHAGATAI: f"The {key_word} insight fits the broader narrative.",
        AgentRole.OGEDEI: f"{key_word.title()} logged in systems monitoring.",
    }
    return templates.get(agent, f"Acknowledged regarding {key_word}.")


# === CHANGE 5: Add emoji reaction helper ===
# Add this method:

async def _add_reaction(self, message: DiscordMessage, emoji: str):
    """Add an emoji reaction instead of text response."""
    try:
        url = f"https://discord.com/api/v10/channels/{message.channel_id}/messages/{message.id}/reactions/{emoji}/@me"
        headers = {"Authorization": f"Bot {self.token}"}
        
        async with self.session.put(url, headers=headers) as resp:
            if resp.status == 204:
                logger.info(f"👍 Added {emoji} reaction to message")
            else:
                logger.warning(f"Failed to add reaction: {resp.status}")
    except Exception as e:
        logger.error(f"Error adding reaction: {e}")


# === MIGRATION GUIDE ===
"""
To migrate from v1 to v2:

1. Replace conversation_value_scorer.py with v2 version
   (or import ConversationValueScorer from v2)

2. In bot_natural.py:
   a. Replace _decide_response method (lines ~240-310)
   b. Replace _generate_natural_response method (lines ~350-420)
   c. Remove template helper methods (_synthesis_addition, etc.)
   d. Add new methods:
      - _generate_validated_response
      - _generate_contextual_response
      - _analyze_message_content
      - _extract_key_phrases
      - _generate_brief_response
      - _answer_questions
      - _discuss_code
      - _build_on_actions
      - _discuss_topics
      - _generic_but_specific
      - _add_reaction

3. Test with various message types:
   - Questions
   - Code snippets
   - Action items
   - Brief acknowledgments
   - Generic low-value messages

4. Tune thresholds if needed:
   - THRESHOLDS dict in ConversationValueScorer
   - Quality scores in validate_response
"""
