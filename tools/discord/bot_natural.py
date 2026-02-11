"""
Kurultai Discord Bot - Natural Agent Conversation
Agents respond to each other with meaningful, contextual dialogue.
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
import traceback
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deliberation_client import AgentRole, AGENT_PERSONALITIES
from conversation_value_scorer import get_scorer, ConversationValueScorer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kurultai-natural")


@dataclass
class DiscordMessage:
    id: str
    channel_id: str
    author: str
    author_id: str
    content: str
    timestamp: datetime
    mentions: List[str]


@dataclass
class ConversationThread:
    """Tracks an ongoing conversation between agents."""
    messages: List[DiscordMessage] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    human_initiated: bool = True
    participation_count: Dict[str, int] = field(default_factory=dict)
    
    def add_message(self, msg: DiscordMessage):
        self.messages.append(msg)
        self.last_activity = datetime.utcnow()
        self.participation_count[msg.author] = self.participation_count.get(msg.author, 0) + 1
    
    def should_continue(self) -> bool:
        """Check if conversation should naturally continue."""
        # End if too many messages (natural conclusion)
        if len(self.messages) >= 8:
            return False
        # End if too much time passed
        if datetime.utcnow() - self.last_activity > timedelta(minutes=5):
            return False
        # End if same agents are going back and forth too much
        if len(self.messages) >= 4:
            recent = [m.author for m in self.messages[-4:]]
            if len(set(recent)) <= 2:  # Only 2 participants going back and forth
                return False
        return True
    
    def get_context(self) -> str:
        """Get recent conversation context."""
        recent = self.messages[-5:] if len(self.messages) > 5 else self.messages
        return "\n".join([f"{m.author}: {m.content[:100]}" for m in recent])


class NaturalConversationBot:
    """Discord bot with natural agent-to-agent conversation."""
    
    # Agent usernames for identification
    AGENT_USERNAMES = {
        "Kublai 🏛️": AgentRole.KUBLAI,
        "Möngke 🔬": AgentRole.MONGKE,
        "Chagatai 📝": AgentRole.CHAGATAI,
        "Temüjin 🛠️": AgentRole.TEMUJIN,
        "Jochi 🔍": AgentRole.JOCHI,
        "Ögedei 📈": AgentRole.OGEDEI,
    }
    
    def __init__(self, bot_token: str, channel_id: str):
        self.token = bot_token
        self.channel_id = channel_id
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.heartbeat_interval: Optional[int] = None
        self.sequence_number: Optional[int] = None
        self.processed_ids: Set[str] = set()
        
        # Conversation tracking
        self.active_thread: Optional[ConversationThread] = None
        self.message_history: deque = deque(maxlen=100)
        
        # Rate limiting per agent
        self.last_response_time: Dict[str, datetime] = {}
        self.min_response_interval = timedelta(seconds=15)  # Natural pause
        
        # Topic memory
        self.current_topic: Optional[str] = None
        self.topic_keywords = {
            "research": [AgentRole.MONGKE, AgentRole.CHAGATAI],
            "build": [AgentRole.TEMUJIN, AgentRole.JOCHI],
            "code": [AgentRole.TEMUJIN],
            "pattern": [AgentRole.MONGKE],
            "system": [AgentRole.OGEDEI, AgentRole.JOCHI],
            "status": [AgentRole.OGEDEI, AgentRole.KUBLAI],
            "document": [AgentRole.CHAGATAI],
            "security": [AgentRole.JOCHI],
            "orchestrate": [AgentRole.KUBLAI],
            "synthesize": [AgentRole.KUBLAI, AgentRole.MONGKE],
        }
        
        # Value scorer for quality gating
        self.value_scorer = get_scorer()
        self.min_value_threshold = 0.6
    
    async def connect(self):
        """Connect to Discord Gateway."""
        self.session = aiohttp.ClientSession()
        
        async with self.session.get(
            "https://discord.com/api/v10/gateway",
            headers={"Authorization": f"Bot {self.token}"}
        ) as resp:
            data = await resp.json()
            gateway_url = data.get("url", "wss://gateway.discord.gg")
        
        self.ws = await self.session.ws_connect(f"{gateway_url}/?v=10&encoding=json")
        logger.info("🔗 Connected to Discord Gateway")
        
        msg = await self.ws.receive_json()
        if msg.get("op") == 10:
            self.heartbeat_interval = msg["d"]["heartbeat_interval"] / 1000
            asyncio.create_task(self._heartbeat_loop())
        
        await self.ws.send_json({
            "op": 2,
            "d": {
                "token": self.token,
                "intents": (1 << 9) | (1 << 15),
                "properties": {"os": "linux", "browser": "KurultaiBot", "device": "KurultaiBot"}
            }
        })
        logger.info("🔐 Identified to Gateway")
    
    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await self.ws.send_json({"op": 1, "d": self.sequence_number})
    
    async def listen(self):
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self._handle_event(data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {self.ws.exception()}")
                break
    
    async def _handle_event(self, data: dict):
        if "s" in data:
            self.sequence_number = data["s"]
        
        op = data.get("op")
        event_type = data.get("t")
        
        if op == 0 and event_type == "MESSAGE_CREATE":
            await self._handle_message(data["d"])
        elif op == 0 and event_type == "READY":
            logger.info(f"✅ Bot ready: {data['d']['user']['username']}")
    
    async def _handle_message(self, msg_data: dict):
        try:
            # Skip if already processed
            msg_id = msg_data["id"]
            if msg_id in self.processed_ids:
                return
            self.processed_ids.add(msg_id)
            if len(self.processed_ids) > 1000:
                self.processed_ids = set(list(self.processed_ids)[-500:])
            
            # Only our channel
            if msg_data.get("channel_id") != self.channel_id:
                return
            
            author_name = msg_data["author"]["username"]
            content = msg_data["content"]
            
            # Skip if author is unknown (not a user or our agents)
            is_agent = author_name in self.AGENT_USERNAMES
            is_human = not msg_data["author"].get("bot", False)
            
            if not (is_agent or is_human):
                return
            
            message = DiscordMessage(
                id=msg_id,
                channel_id=msg_data["channel_id"],
                author=author_name,
                author_id=msg_data["author"]["id"],
                content=content,
                timestamp=datetime.fromisoformat(msg_data["timestamp"].replace("Z", "+00:00")),
                mentions=[m["username"] for m in msg_data.get("mentions", [])]
            )
            
            self.message_history.append(message)
            
            # Update conversation thread
            if self.active_thread and not self.active_thread.should_continue():
                logger.info("📌 Conversation naturally concluded")
                self.active_thread = None
            
            if self.active_thread is None:
                self.active_thread = ConversationThread(human_initiated=is_human)
            
            self.active_thread.add_message(message)
            
            logger.info(f"💬 [{author_name}]: {content[:60]}")
            
            # Decide if and how to respond
            await self._decide_response(message, is_agent, is_human)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.error(traceback.format_exc())
    
    async def _decide_response(self, message: DiscordMessage, is_agent: bool, is_human: bool):
        """Decide if an agent should respond and which one."""
        content_lower = message.content.lower()
        
        # VALUE-FIRST PROTOCOL: Score the conversation for usefulness
        if self.active_thread:
            # Convert messages for scoring
            score_messages = [
                {"author": m.author, "content": m.content} 
                for m in self.active_thread.messages
            ]
            
            should_respond, reason = self.value_scorer.should_agent_respond(
                message.content, 
                score_messages
            )
            
            if not should_respond:
                logger.info(f"⏭️ Value gate blocked: {reason}")
                
                # If conversation has gone on too long with low value, generate summary
                convo_score = self.value_scorer.score_conversation(score_messages)
                if len(self.active_thread.messages) >= 6 and convo_score.total_score < 0.5:
                    summary = self.value_scorer.generate_summary(score_messages)
                    logger.info(f"📋 Conversation summary:\n{summary}")
                    # Reset the thread
                    self.active_thread = None
                
                return
            
            logger.info(f"✅ Value gate passed: {reason}")
        
        # Find interested agents based on topic
        interested_agents = []
        
        # Check for explicit mentions
        for agent_name, role in self.AGENT_USERNAMES.items():
            agent_simple = agent_name.split()[0].lower().replace("🛠️", "").replace("🔬", "").strip()
            if agent_simple in content_lower or f"@{agent_simple}" in content_lower:
                interested_agents.append((role, 1.0))  # High priority for mentions
        
        # Check for topic keywords
        for keyword, agents in self.topic_keywords.items():
            if keyword in content_lower:
                for agent in agents:
                    # Add if not already mentioned
                    if not any(a[0] == agent for a in interested_agents):
                        interested_agents.append((agent, 0.7))
        
        # If no specific match, agents might chime in based on conversation flow
        # BUT: Only if value score is high enough (>0.7) to warrant unsolicited contribution
        if not interested_agents and self.active_thread and len(self.active_thread.messages) > 1:
            score_messages = [
                {"author": m.author, "content": m.content} 
                for m in self.active_thread.messages
            ]
            convo_score = self.value_scorer.score_conversation(score_messages)
            
            # Only chime in if conversation is valuable (not social chatter)
            if convo_score.total_score >= 0.7 and random.random() < 0.2:
                # Pick an agent who hasn't spoken recently
                recent_speakers = set(m.author for m in self.active_thread.messages[-3:])
                available = [(role, 0.4) for name, role in self.AGENT_USERNAMES.items() 
                            if name not in recent_speakers]
                if available:
                    interested_agents.append(random.choice(available))
                    logger.info(f"💡 Agent chiming in due to high-value conversation ({convo_score.total_score:.2f})")
        
        # Filter out agents who responded too recently
        now = datetime.utcnow()
        eligible_agents = []
        for agent, interest in interested_agents:
            agent_name = AGENT_PERSONALITIES[agent].display_name
            last_time = self.last_response_time.get(agent_name)
            if last_time is None or now - last_time > self.min_response_interval:
                eligible_agents.append((agent, interest))
        
        # Also filter out the author (don't respond to yourself)
        if message.author in self.AGENT_USERNAMES:
            author_role = self.AGENT_USERNAMES[message.author]
            eligible_agents = [(a, i) for a, i in eligible_agents if a != author_role]
        
        if not eligible_agents:
            logger.info("⏭️ No eligible agents to respond")
            return
        
        # Sort by interest level and pick best match
        eligible_agents.sort(key=lambda x: x[1], reverse=True)
        chosen_agent = eligible_agents[0][0]
        
        # Add natural delay (agents don't respond instantly)
        delay = random.uniform(2, 8)
        logger.info(f"⏳ {AGENT_PERSONALITIES[chosen_agent].name} will respond in {delay:.1f}s")
        await asyncio.sleep(delay)
        
        # Generate and send response
        await self._generate_natural_response(chosen_agent, message)
    
    async def _generate_natural_response(self, agent: AgentRole, trigger_message: DiscordMessage):
        """Generate a natural, contextual response."""
        personality = AGENT_PERSONALITIES[agent]
        
        # Get conversation context
        context = ""
        if self.active_thread:
            context = self.active_thread.get_context()
        
        # Build response based on context and personality
        content_lower = trigger_message.content.lower()
        
        # Determine response type
        is_question = "?" in trigger_message.content
        is_agent_speaking = trigger_message.author in self.AGENT_USERNAMES
        
        # Build response
        responses = []
        
        if is_agent_speaking:
            # Responding to another agent - build on their point
            if agent == AgentRole.KUBLAI:
                responses = [
                    f"@{trigger_message.author.split()[0]} raises a crucial point. {self._synthesis_addition()}",
                    f"Building on what {trigger_message.author.split()[0]} said — {self._strategic_observation()}",
                    f"The Council notes: {trigger_message.author.split()[0]}'s insight connects to {self._pattern_connection()}",
                ]
            elif agent == AgentRole.MONGKE:
                responses = [
                    f"@{trigger_message.author.split()[0]}'s observation reveals {self._pattern_insight()}",
                    f"The data supports {trigger_message.author.split()[0]}'s assessment. Additionally, {self._research_addition()}",
                    f"Interesting correlation with {trigger_message.author.split()[0]}'s point: {self._analysis_addition()}",
                ]
            elif agent == AgentRole.TEMUJIN:
                responses = [
                    f"@{trigger_message.author.split()[0]} — I can implement that. {self._build_plan()}",
                    f"Practical application of {trigger_message.author.split()[0]}'s idea: {self._implementation_note()}",
                    f"From a builder's perspective on {trigger_message.author.split()[0]}'s point: {self._technical_angle()}",
                ]
            elif agent == AgentRole.JOCHI:
                responses = [
                    f"@{trigger_message.author.split()[0]} — let me validate that. {self._security_perspective()}",
                    f"Testing {trigger_message.author.split()[0]}'s approach: {self._audit_note()}",
                    f"Security consideration for {trigger_message.author.split()[0]}'s point: {self._risk_assessment()}",
                ]
            elif agent == AgentRole.CHAGATAI:
                responses = [
                    f"@{trigger_message.author.split()[0]} — I'll capture this insight. {self._documentation_angle()}",
                    f"The narrative emerging from {trigger_message.author.split()[0]}'s observation: {self._reflection_note()}",
                    f"Documenting {trigger_message.author.split()[0]}'s contribution: {self._wisdom_capture()}",
                ]
            elif agent == AgentRole.OGEDEI:
                responses = [
                    f"@{trigger_message.author.split()[0]} — systems perspective: {self._ops_perspective()}",
                    f"Monitoring confirms {trigger_message.author.split()[0]}'s assessment. {self._health_context()}",
                    f"Operational impact of {trigger_message.author.split()[0]}'s point: {self._infrastructure_note()}",
                ]
        else:
            # Responding to human
            if is_question:
                responses = self._get_question_responses(agent, trigger_message.author)
            else:
                responses = self._get_statement_responses(agent, trigger_message.author)
        
        response = random.choice(responses)
        
        # Occasionally add signature phrase
        if random.random() < 0.3:
            response += f"\n\n— *{personality.signature_phrase}*"
        
        # Update last response time
        self.last_response_time[personality.display_name] = datetime.utcnow()
        
        logger.info(f"📤 {personality.display_name} responding")
        await self._send_via_webhook(agent, response)
    
    def _get_question_responses(self, agent: AgentRole, author: str) -> List[str]:
        """Get responses for questions."""
        author_name = author.split()[0]
        responses = {
            AgentRole.KUBLAI: [
                f"@{author_name} The Council's assessment: {self._strategic_observation()}",
                f"@{author_name} Per ignotam portam — {self._synthesis_addition()}",
            ],
            AgentRole.MONGKE: [
                f"@{author_name} The patterns reveal: {self._pattern_insight()}",
                f"@{author_name} Research indicates: {self._research_addition()}",
            ],
            AgentRole.TEMUJIN: [
                f"@{author_name} Implementation path: {self._build_plan()}",
                f"@{author_name} Can build that. {self._technical_angle()}",
            ],
            AgentRole.JOCHI: [
                f"@{author_name} Security analysis: {self._risk_assessment()}",
                f"@{author_name} Validation shows: {self._audit_note()}",
            ],
            AgentRole.CHAGATAI: [
                f"@{author_name} The record reflects: {self._reflection_note()}",
                f"@{author_name} Documenting this: {self._wisdom_capture()}",
            ],
            AgentRole.OGEDEI: [
                f"@{author_name} Systems status: {self._health_context()}",
                f"@{author_name} Operations check: {self._ops_perspective()}",
            ],
        }
        return responses.get(agent, [f"@{author_name} Acknowledged."])
    
    def _get_statement_responses(self, agent: AgentRole, author: str) -> List[str]:
        """Get responses for statements."""
        author_name = author.split()[0]
        responses = {
            AgentRole.KUBLAI: [
                f"@{author_name} Noted. {self._strategic_observation()}",
                f"@{author_name} The Council incorporates this. {self._synthesis_addition()}",
            ],
            AgentRole.MONGKE: [
                f"@{author_name} Interesting data point. {self._analysis_addition()}",
                f"@{author_name} This connects to {self._pattern_connection()}",
            ],
            AgentRole.TEMUJIN: [
                f"@{author_name} Build systems acknowledge. {self._implementation_note()}",
                f"@{author_name} Adding to implementation queue. {self._technical_angle()}",
            ],
            AgentRole.JOCHI: [
                f"@{author_name} Security protocols note this. {self._security_perspective()}",
                f"@{author_name} Audit trail updated. {self._risk_assessment()}",
            ],
            AgentRole.CHAGATAI: [
                f"@{author_name} Capturing this insight. {self._documentation_angle()}",
                f"@{author_name} The narrative grows. {self._reflection_note()}",
            ],
            AgentRole.OGEDEI: [
                f"@{author_name} Systems logged. {self._infrastructure_note()}",
                f"@{author_name} Metrics updated. {self._health_context()}",
            ],
        }
        return responses.get(agent, [f"@{author_name} Acknowledged."])
    
    # Response content generators
    def _synthesis_addition(self) -> str: return random.choice([
        "we're seeing convergence across multiple workstreams.",
        "this aligns with the broader strategic direction.",
        "the pattern fits what we've been tracking.",
    ])
    def _strategic_observation(self) -> str: return random.choice([
        "The Work advances on schedule.",
        "Our coordination remains effective.",
        "The Council's focus is well-placed.",
    ])
    def _pattern_connection(self) -> str: return random.choice([
        "our previous findings on system optimization.",
        "the research Möngke shared earlier.",
        "Temüjin's recent infrastructure work.",
    ])
    def _pattern_insight(self) -> str: return random.choice([
        "correlations we hadn't previously identified.",
        "data trends worth deeper investigation.",
        "anomalies that might indicate opportunity.",
    ])
    def _research_addition(self) -> str: return random.choice([
        "our analysis suggests 3-5 optimization vectors.",
        "cross-referencing shows strong alignment.",
        "the metrics support pursuing this direction.",
    ])
    def _analysis_addition(self) -> str: return random.choice([
        "there's a secondary pattern emerging.",
        "historical data validates this approach.",
        "correlation coefficients are promising.",
    ])
    def _build_plan(self) -> str: return random.choice([
        "ETA for prototype: 48 hours.",
        "I'll prioritize this in the build queue.",
        "Implementation complexity: moderate. Starting now.",
    ])
    def _implementation_note(self) -> str: return random.choice([
        "the infrastructure can support this at scale.",
        "we'll need to update the deployment pipeline.",
        "integration with existing systems is straightforward.",
    ])
    def _technical_angle(self) -> str: return random.choice([
        "Performance metrics look solid.",
        "Code review passes all checks.",
        "The architecture handles this elegantly.",
    ])
    def _security_perspective(self) -> str: return random.choice([
        "threat model remains within acceptable bounds.",
        "validation confirms no new attack vectors.",
        "security posture is maintained.",
    ])
    def _audit_note(self) -> str: return random.choice([
        "all security gates pass.",
        "compliance checks complete.",
        "audit trail is clean.",
    ])
    def _risk_assessment(self) -> str: return random.choice([
        "Risk: low. Proceeding with confidence.",
        "No significant security concerns detected.",
        "The approach is defensible.",
    ])
    def _documentation_angle(self) -> str: return random.choice([
        "This will serve future agents well.",
        "The record captures the essential insight.",
        "Wisdom preserved for the archive.",
    ])
    def _reflection_note(self) -> str: return random.choice([
        "There's poetry in how we're building this.",
        "The story writes itself.",
        "History will remember this phase.",
    ])
    def _wisdom_capture(self) -> str: return random.choice([
        "Lessons distilled for future reference.",
        "Knowledge preserved.",
        "The archive grows richer.",
    ])
    def _ops_perspective(self) -> str: return random.choice([
        "All systems remain nominal.",
        "Infrastructure load is within parameters.",
        "Operations are smooth.",
    ])
    def _health_context(self) -> str: return random.choice([
        "Heartbeat monitors show green.",
        "No alerts requiring attention.",
        "Health metrics are optimal.",
    ])
    def _infrastructure_note(self) -> str: return random.choice([
        "Scaling handles this naturally.",
        "Resource utilization is efficient.",
        "The foundation remains solid.",
    ])
    
    async def _send_via_webhook(self, agent: AgentRole, content: str):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            
            webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
            if not webhook_url:
                return
            
            personality = AGENT_PERSONALITIES[agent]
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json={
                    "username": personality.display_name,
                    "content": content,
                }) as resp:
                    if resp.status == 204:
                        logger.info(f"✅ {personality.display_name} responded")
                    else:
                        logger.error(f"❌ Webhook failed: {resp.status}")
        except Exception as e:
            logger.error(f"Error sending: {e}")
    
    async def close(self):
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


async def main():
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("KUBLAI_DISCORD_TOKEN")
    channel_id = os.getenv("DISCORD_COUNCIL_CHANNEL_ID")
    
    if not token or not channel_id:
        logger.error("Missing credentials")
        return
    
    bot = NaturalConversationBot(token, channel_id)
    
    try:
        await bot.connect()
        await bot.listen()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
