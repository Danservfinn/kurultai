#!/usr/bin/env python3
"""
Context-Aware Routing - Kurultai v2.0

Enhanced task routing based on:
- Conversation context analysis
- Priority inference from message tone/urgency
- Multi-factor routing decisions
- Intent classification

Author: Kurultai v2.0
Date: 2026-02-10
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kurultai.kurultai_types import DeliverableType, TaskStatus


class UrgencyLevel(Enum):
    """Detected urgency levels from message analysis."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Sentiment(Enum):
    """Message sentiment classification."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"
    URGENT = "urgent"


class IntentType(Enum):
    """Types of user intents detected."""
    QUESTION = "question"
    REQUEST = "request"
    COMMAND = "command"
    REPORT = "report"
    DISCUSSION = "discussion"
    FOLLOW_UP = "follow_up"
    CLARIFICATION = "clarification"


@dataclass
class MessageContext:
    """Rich context extracted from a message."""
    content: str
    timestamp: datetime
    sender_hash: str
    urgency: UrgencyLevel = UrgencyLevel.NORMAL
    sentiment: Sentiment = Sentiment.NEUTRAL
    intent: IntentType = IntentType.REQUEST
    topics: List[str] = field(default_factory=list)
    referenced_tasks: List[str] = field(default_factory=list)
    mentioned_agents: List[str] = field(default_factory=list)
    time_constraints: Optional[str] = None
    complexity_indicators: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "urgency": self.urgency.value,
            "sentiment": self.sentiment.value,
            "intent": self.intent.value,
            "topics": self.topics,
            "referenced_tasks": self.referenced_tasks,
            "mentioned_agents": self.mentioned_agents,
            "time_constraints": self.time_constraints,
            "complexity_indicators": self.complexity_indicators
        }


@dataclass
class RoutingDecision:
    """Result of context-aware routing."""
    target_agent: str
    deliverable_type: DeliverableType
    priority: str
    priority_weight: float
    routing_confidence: float
    reason: str
    suggested_agents: List[str] = field(default_factory=list)
    estimated_duration: int = 15
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_agent": self.target_agent,
            "deliverable_type": self.deliverable_type.value,
            "priority": self.priority,
            "priority_weight": self.priority_weight,
            "routing_confidence": round(self.routing_confidence, 2),
            "reason": self.reason,
            "suggested_agents": self.suggested_agents,
            "estimated_duration": self.estimated_duration
        }


class ContextAwareRouter:
    """
    Intelligent context-aware routing for tasks and messages.
    
    Features:
    - Conversation context analysis
    - Urgency detection from tone and keywords
    - Priority inference
    - Multi-factor routing decisions
    - Intent classification
    """
    
    # Urgency keywords mapping
    URGENCY_KEYWORDS = {
        UrgencyLevel.CRITICAL: [
            "asap", "immediately", "urgent", "critical", "emergency",
            "broken", "down", "crash", "failure", "outage",
            "blocking", "blocked", "stuck", "cannot proceed",
            "deadline", "due today", "due tomorrow", "expired"
        ],
        UrgencyLevel.HIGH: [
            "soon", "quickly", "important", "priority", "needed",
            "required", "should", "please", "can you", "would you"
        ],
        UrgencyLevel.NORMAL: [
            "when you can", "at your convenience", "no rush",
            "eventually", "sometime", "whenever"
        ]
    }
    
    # Sentiment patterns
    SENTIMENT_PATTERNS = {
        Sentiment.FRUSTRATED: [
            r"this is (?:ridiculous|absurd|crazy)",
            r"(?:again|still) (?:not working|broken|failing)",
            r"why (?:isn't|doesn't|won't|can't)",
            r"(?:very|really|extremely) (?:frustrated|annoyed|disappointed)",
        ],
        Sentiment.URGENT: [
            r"need (?:this|it) (?:now|asap|immediately|today)",
            r"(?:hurry|quick|fast|rush)",
        ],
        Sentiment.NEGATIVE: [
            r"(?:bad|wrong|terrible|awful|poor)",
            r"(?:not|never|no) (?:good|right|correct|working)",
        ],
        Sentiment.POSITIVE: [
            r"(?:great|good|excellent|awesome|perfect|thanks|thank you)",
            r"(?:love|like|appreciate)",
        ]
    }
    
    # Intent patterns
    INTENT_PATTERNS = {
        IntentType.QUESTION: [
            r"^(?:what|why|how|when|where|who|is|are|can|could|would|will|does|do)",
            r"\?$",
        ],
        IntentType.COMMAND: [
            r"^(?:create|make|build|implement|fix|update|change|delete|remove|add)",
            r"^(?:run|execute|start|stop|restart|deploy)",
        ],
        IntentType.REPORT: [
            r"(?:error|exception|failed|crash|bug|issue|problem)",
            r"(?:log|report|output|result)",
        ],
        IntentType.FOLLOW_UP: [
            r"(?:follow up|following up|any update|status|progress)",
            r"(?:how is|what about|regarding|about the)",
        ],
        IntentType.CLARIFICATION: [
            r"(?:clarify|clarification|explain|what (?:did you mean|do you mean)|unclear)",
        ],
    }
    
    # Topic keywords
    TOPIC_KEYWORDS = {
        "architecture": ["architecture", "design", "system", "structure", "pattern"],
        "security": ["security", "auth", "login", "password", "encrypt", "vulnerability"],
        "database": ["database", "neo4j", "query", "schema", "migration", "data"],
        "api": ["api", "endpoint", "rest", "graphql", "request", "response"],
        "frontend": ["ui", "frontend", "interface", "component", "react", "vue"],
        "backend": ["backend", "server", "service", "endpoint", "handler"],
        "deployment": ["deploy", "deployment", "kubernetes", "docker", "infrastructure"],
        "testing": ["test", "testing", "pytest", "spec", "unit test", "integration"],
        "documentation": ["doc", "documentation", "readme", "guide", "manual"],
        "research": ["research", "analyze", "investigate", "study", "explore"],
        "bugfix": ["bug", "fix", "error", "issue", "problem", "broken"],
        "performance": ["performance", "optimization", "slow", "fast", "speed", "memory"],
    }
    
    # Agent routing mapping with context factors
    AGENT_ROUTING = {
        "researcher": {
            "deliverable_types": [DeliverableType.RESEARCH],
            "keywords": ["research", "analyze", "investigate", "find", "look up", "search", "what is", "how does"],
            "topics": ["research", "analysis"],
            "confidence_bonus": 0.1
        },
        "analyst": {
            "deliverable_types": [DeliverableType.ANALYSIS, DeliverableType.STRATEGY],
            "keywords": ["analyze", "review", "audit", "assess", "evaluate", "strategy", "plan"],
            "topics": ["security", "performance", "architecture"],
            "confidence_bonus": 0.1
        },
        "developer": {
            "deliverable_types": [DeliverableType.CODE, DeliverableType.TESTING],
            "keywords": ["code", "implement", "build", "create", "fix", "develop", "refactor", "test"],
            "topics": ["api", "backend", "frontend", "database", "bugfix", "testing"],
            "confidence_bonus": 0.1
        },
        "writer": {
            "deliverable_types": [DeliverableType.CONTENT, DeliverableType.DOCS],
            "keywords": ["write", "document", "draft", "content", "blog", "article"],
            "topics": ["documentation"],
            "confidence_bonus": 0.1
        },
        "ops": {
            "deliverable_types": [DeliverableType.OPS],
            "keywords": ["deploy", "monitor", "check", "health", "status", "restart", "configure"],
            "topics": ["deployment", "infrastructure"],
            "confidence_bonus": 0.1
        },
        "main": {
            "deliverable_types": [DeliverableType.ANALYSIS],
            "keywords": [],
            "topics": [],
            "confidence_bonus": 0.0
        }
    }
    
    def __init__(self, driver):
        self.driver = driver
    
    def analyze_message(self, content: str, sender_hash: str = "") -> MessageContext:
        """
        Analyze message content to extract rich context.
        """
        context = MessageContext(
            content=content,
            timestamp=datetime.now(),
            sender_hash=sender_hash
        )
        
        content_lower = content.lower()
        
        # Detect urgency
        context.urgency = self._detect_urgency(content_lower)
        
        # Detect sentiment
        context.sentiment = self._detect_sentiment(content_lower)
        
        # Detect intent
        context.intent = self._detect_intent(content_lower)
        
        # Extract topics
        context.topics = self._extract_topics(content_lower)
        
        # Find referenced tasks
        context.referenced_tasks = self._find_referenced_tasks(content)
        
        # Find mentioned agents
        context.mentioned_agents = self._find_mentioned_agents(content_lower)
        
        # Detect time constraints
        context.time_constraints = self._detect_time_constraints(content_lower)
        
        # Calculate complexity
        context.complexity_indicators = self._calculate_complexity(content)
        
        return context
    
    def _detect_urgency(self, content: str) -> UrgencyLevel:
        """Detect urgency level from message content."""
        for urgency, keywords in self.URGENCY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content:
                    return urgency
        return UrgencyLevel.NORMAL
    
    def _detect_sentiment(self, content: str) -> Sentiment:
        """Detect sentiment from message content."""
        for sentiment, patterns in self.SENTIMENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return sentiment
        return Sentiment.NEUTRAL
    
    def _detect_intent(self, content: str) -> IntentType:
        """Detect intent from message content."""
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return intent
        return IntentType.REQUEST
    
    def _extract_topics(self, content: str) -> List[str]:
        """Extract topics mentioned in content."""
        topics = []
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                topics.append(topic)
        return topics[:3]  # Top 3 topics
    
    def _find_referenced_tasks(self, content: str) -> List[str]:
        """Find task IDs referenced in content."""
        # Look for task IDs like TASK-123, task_abc123, etc.
        patterns = [
            r'(?:task|ticket|issue)[-_\s#]*(\w+[-_]?\d+)',
            r'#(\d+)',
        ]
        
        tasks = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            tasks.extend(matches)
        
        return tasks
    
    def _find_mentioned_agents(self, content: str) -> List[str]:
        """Find agent mentions in content."""
        agent_names = ["researcher", "analyst", "developer", "writer", "ops", "main"]
        mentioned = []
        
        for agent in agent_names:
            if agent in content:
                mentioned.append(agent)
        
        return mentioned
    
    def _detect_time_constraints(self, content: str) -> Optional[str]:
        """Detect time constraints mentioned in content."""
        patterns = [
            r'(?:by|before|until)\s+(\w+day|tomorrow|today|\d{1,2}:\d{2})',
            r'(?:in|within)\s+(\d+)\s*(minute|hour|day|week)',
            r'(?:due|deadline)\s*:?\s*(\w+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    def _calculate_complexity(self, content: str) -> Dict[str, int]:
        """Calculate complexity indicators."""
        indicators = {
            "word_count": len(content.split()),
            "sentence_count": len(re.split(r'[.!?]+', content)),
            "question_count": content.count('?'),
            "technical_terms": 0
        }
        
        # Count technical terms
        technical_patterns = [
            r'\b(?:api|database|function|class|method|endpoint|query|schema)\b',
            r'\b(?:config|deployment|kubernetes|docker|infrastructure)\b',
            r'\b(?:python|javascript|typescript|java|go|rust)\b',
        ]
        
        for pattern in technical_patterns:
            indicators["technical_terms"] += len(re.findall(pattern, content, re.IGNORECASE))
        
        return indicators
    
    def infer_priority(self, context: MessageContext) -> Tuple[str, float]:
        """
        Infer priority from message context.
        
        Returns (priority, weight) tuple.
        """
        base_weight = 0.5
        
        # Urgency factor
        urgency_weights = {
            UrgencyLevel.CRITICAL: 1.0,
            UrgencyLevel.HIGH: 0.8,
            UrgencyLevel.NORMAL: 0.5,
            UrgencyLevel.LOW: 0.2
        }
        base_weight += urgency_weights.get(context.urgency, 0.5) * 0.3
        
        # Sentiment factor (frustration increases priority)
        if context.sentiment == Sentiment.FRUSTRATED:
            base_weight += 0.2
        elif context.sentiment == Sentiment.URGENT:
            base_weight += 0.15
        
        # Intent factor
        if context.intent == IntentType.COMMAND:
            base_weight += 0.1
        elif context.intent == IntentType.REPORT:
            base_weight += 0.05
        
        # Time constraint factor
        if context.time_constraints:
            base_weight += 0.1
        
        # Map to priority
        if base_weight >= 0.9:
            return "critical", min(1.0, base_weight)
        elif base_weight >= 0.75:
            return "high", min(1.0, base_weight)
        elif base_weight >= 0.45:
            return "medium", base_weight
        else:
            return "low", base_weight
    
    def route(self, content: str, sender_hash: str = "") -> RoutingDecision:
        """
        Make context-aware routing decision.
        
        Considers multiple factors:
        - Message content analysis
        - Detected topics
        - Urgency and sentiment
        - Intent
        - Complexity
        """
        # Analyze message
        context = self.analyze_message(content, sender_hash)
        
        # Infer priority
        priority, priority_weight = self.infer_priority(context)
        
        # Calculate routing scores for each agent
        scores = {}
        for agent_id, config in self.AGENT_ROUTING.items():
            score = self._calculate_agent_score(agent_id, context, config)
            scores[agent_id] = score
        
        # Sort by score
        sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Select primary agent
        primary_agent = sorted_agents[0][0]
        primary_score = sorted_agents[0][1]
        
        # Determine deliverable type
        deliverable_type = self._select_deliverable_type(context, primary_agent)
        
        # Build reason
        reason_parts = [
            f"Intent: {context.intent.value}",
            f"Topics: {', '.join(context.topics) if context.topics else 'general'}",
        ]
        if context.urgency != UrgencyLevel.NORMAL:
            reason_parts.append(f"Urgency: {context.urgency.value}")
        reason_parts.append(f"Agent confidence: {primary_score:.2f}")
        
        # Suggest additional agents
        suggested_agents = [
            agent for agent, score in sorted_agents[1:3] 
            if score > primary_score * 0.7
        ]
        
        # Estimate duration based on complexity
        estimated_duration = self._estimate_duration(context)
        
        return RoutingDecision(
            target_agent=primary_agent,
            deliverable_type=deliverable_type,
            priority=priority,
            priority_weight=priority_weight,
            routing_confidence=primary_score,
            reason=" | ".join(reason_parts),
            suggested_agents=suggested_agents,
            estimated_duration=estimated_duration
        )
    
    def _calculate_agent_score(
        self, 
        agent_id: str, 
        context: MessageContext,
        config: Dict
    ) -> float:
        """Calculate routing score for an agent."""
        score = 0.3  # Base score
        
        content_lower = context.content.lower()
        
        # Keyword matching
        for keyword in config.get("keywords", []):
            if keyword in content_lower:
                score += 0.15
        
        # Topic matching
        for topic in context.topics:
            if topic in config.get("topics", []):
                score += 0.2
        
        # Agent mention bonus
        if agent_id in context.mentioned_agents:
            score += 0.25
        
        # Confidence bonus
        score += config.get("confidence_bonus", 0)
        
        return min(1.0, score)
    
    def _select_deliverable_type(
        self, 
        context: MessageContext,
        agent_id: str
    ) -> DeliverableType:
        """Select appropriate deliverable type."""
        config = self.AGENT_ROUTING.get(agent_id, {})
        types = config.get("deliverable_types", [DeliverableType.ANALYSIS])
        
        # If multiple types, select based on intent
        if len(types) > 1:
            intent_map = {
                IntentType.QUESTION: DeliverableType.RESEARCH,
                IntentType.REQUEST: DeliverableType.ANALYSIS,
                IntentType.COMMAND: DeliverableType.CODE,
                IntentType.REPORT: DeliverableType.ANALYSIS,
            }
            
            preferred = intent_map.get(context.intent)
            if preferred in types:
                return preferred
        
        return types[0]
    
    def _estimate_duration(self, context: MessageContext) -> int:
        """Estimate task duration based on complexity."""
        base_duration = 15
        
        # Word count factor
        word_count = context.complexity_indicators.get("word_count", 0)
        if word_count > 100:
            base_duration += 15
        if word_count > 300:
            base_duration += 15
        
        # Technical complexity
        tech_terms = context.complexity_indicators.get("technical_terms", 0)
        base_duration += tech_terms * 5
        
        # Question complexity
        questions = context.complexity_indicators.get("question_count", 0)
        base_duration += questions * 10
        
        # Cap at reasonable maximum
        return min(120, base_duration)
    
    def route_task_with_context(
        self,
        task_description: str,
        existing_context: Optional[Dict] = None
    ) -> RoutingDecision:
        """
        Route a task with full context awareness.
        
        Considers both the task description and any existing conversation context.
        """
        # Combine with existing context if available
        full_content = task_description
        if existing_context:
            recent_messages = existing_context.get("recent_messages", [])
            if recent_messages:
                full_content = " ".join(recent_messages[-3:]) + " " + task_description
        
        return self.route(full_content)
    
    def analyze_conversation_thread(
        self,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze a conversation thread for routing insights.
        """
        if not messages:
            return {"status": "no_messages"}
        
        contexts = [self.analyze_message(m.get("content", ""), m.get("sender", "")) for m in messages]
        
        # Aggregate insights
        all_topics = []
        all_urgencies = []
        all_intents = []
        
        for ctx in contexts:
            all_topics.extend(ctx.topics)
            all_urgencies.append(ctx.urgency)
            all_intents.append(ctx.intent)
        
        # Most common topics
        topic_counts = {}
        for topic in all_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Most urgent message
        urgency_order = [UrgencyLevel.CRITICAL, UrgencyLevel.HIGH, UrgencyLevel.NORMAL, UrgencyLevel.LOW]
        max_urgency = UrgencyLevel.LOW
        for u in all_urgencies:
            if urgency_order.index(u) < urgency_order.index(max_urgency):
                max_urgency = u
        
        return {
            "message_count": len(messages),
            "top_topics": [t[0] for t in top_topics],
            "dominant_urgency": max_urgency.value,
            "recent_intent": contexts[-1].intent.value if contexts else None,
            "escalation_detected": max_urgency in [UrgencyLevel.CRITICAL, UrgencyLevel.HIGH]
        }


# Global instance
_router: Optional[ContextAwareRouter] = None


def get_context_router(driver) -> ContextAwareRouter:
    """Get or create global context router instance."""
    global _router
    if _router is None:
        _router = ContextAwareRouter(driver)
    return _router


def reset_context_router():
    """Reset global instance (for testing)."""
    global _router
    _router = None


# Standalone execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Context-Aware Router")
    parser.add_argument("--route", type=str, help="Route a message")
    parser.add_argument("--analyze", type=str, help="Analyze a message")
    
    args = parser.parse_args()
    
    from neo4j import GraphDatabase
    
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    
    if args.route:
        # Create dummy driver for testing
        router = ContextAwareRouter(None)
        decision = router.route(args.route)
        print(json.dumps(decision.to_dict(), indent=2))
    elif args.analyze:
        router = ContextAwareRouter(None)
        context = router.analyze_message(args.analyze)
        print(json.dumps(context.to_dict(), indent=2))
    else:
        # Demo
        demo_messages = [
            "Can you research the latest AI models?",
            "URGENT: The production server is down! Fix immediately!",
            "Please document the API endpoints when you have time",
            "This is broken again... really frustrated with these bugs",
        ]
        
        router = ContextAwareRouter(None)
        for msg in demo_messages:
            print(f"\nMessage: {msg}")
            decision = router.route(msg)
            print(f"  -> Route to: {decision.target_agent}")
            print(f"  -> Priority: {decision.priority} ({decision.priority_weight:.2f})")
            print(f"  -> Confidence: {decision.routing_confidence:.2f}")
            print(f"  -> Reason: {decision.reason}")
