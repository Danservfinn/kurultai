"""
Conversation Value Scorer v2
Improved Value-First Protocol with tiered thresholds and post-generation filtering.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re


class ValueDimension(Enum):
    """Dimensions for scoring conversation value."""
    TASK_CONNECTION = "task_connection"
    NEW_INFORMATION = "new_information"
    RESOLUTION = "resolution"
    ACTIONABILITY = "actionability"
    CLARITY = "clarity"  # NEW: Measures how clear/understandable the message is


class ConversationContext(Enum):
    """Type of conversation context for threshold selection."""
    HUMAN_TO_AGENT = "human_to_agent"
    AGENT_TO_AGENT_EARLY = "agent_to_agent_early"  # First 3 messages
    AGENT_TO_AGENT_MATURE = "agent_to_agent_mature"  # Established conversation
    AGENT_UNSOLICITED = "agent_unsolicited"  # Agent chiming in


@dataclass
class ValueScore:
    """Value score for a conversation or message."""
    total_score: float  # 0.0-1.0
    dimension_scores: Dict[ValueDimension, float]
    reason: str
    should_continue: bool
    recommended_depth: str  # NEW: 'skip', 'brief', 'substantive', 'deep'
    
    @property
    def is_valuable(self) -> bool:
        """Whether conversation meets value threshold (legacy)."""
        return self.total_score >= 0.6


@dataclass
class ResponseValidation:
    """Result of validating a potential response."""
    should_send: bool
    reason: str
    quality_score: float
    suggested_improvement: Optional[str] = None


class ConversationValueScorer:
    """
    Scores Discord conversations on value metrics.
    Implements Value-First Protocol v2:
    - Context-aware thresholds
    - Post-generation response validation
    - Agent self-moderation support
    """
    
    # === VALUE INDICATORS (expanded) ===
    
    VALUE_INDICATORS = {
        ValueDimension.TASK_CONNECTION: [
            r"\btask\b", r"\bproject\b", r"\bimplement\b", r"\bbuild\b",
            r"\bdeploy\b", r"\btest\b", r"\bfix\b", r"\bcomplete\b",
            r"\bwork\b", r"\bintegration\b", r"\bsystem\b", r"\bfeature\b",
            r"\bbug\b", r"\bissue\b", r"\berror\b", r"\bproblem\b",
            r"#\w+",  # Task references
            r"notion", r"github", r"railway", r"moltbook", r"discord",
            r"\bapi\b", r"\bendpoint\b", r"\bdatabase\b", r"\bauth\b",
            r"\bdeploy\b", r"\bserver\b", r"\bconfig\b", r"\benv\b",
        ],
        ValueDimension.NEW_INFORMATION: [
            r"\bfound\b", r"\bdiscovered\b", r"\blearned\b",
            r"\banalysis\b", r"\bresearch\b", r"\bdata\b", r"\bmetric",
            r"\bpattern\b", r"\binsight\b", r"\bobserved\b", r"\btrack\b",
            r"\brevealed\b", r"\buncovered\b", r"\bidentified\b",
            r"\bmeasured\b", r"\bcalculated\b", r"\bcompared\b",
            r"https?://[^\s]+",  # Links to resources
            r"\b\d+\.?\d*%?\b",  # Numbers/metrics with optional %
            r"`[^`]+`",  # Inline code
            r"```[\s\S]*?```",  # Code blocks
            r"\bversion\b", r"\brelease\b", r"\bupdate\b",
        ],
        ValueDimension.RESOLUTION: [
            r"\bdecided\b", r"\bconclusion\b", r"\bresolution\b", r"\bagreed\b",
            r"\bthe answer is\b", r"\bsolution\b", r"\bresolved\b",
            r"\bwe should\b", r"\blet's\b", r"\bgoing with\b", r"\bneed to\b",
            r"\bstrategy\b", r"\bplan\b", r"\bapproach\b", r"\bmethod\b",
            r"\brecommend\b", r"\bsuggest\b", r"\bproposal\b",
            r"\bconfirmed\b", r"\bverified\b", r"\bworks\b",
        ],
        ValueDimension.ACTIONABILITY: [
            r"\bnext step\b", r"\baction item\b", r"\btodo\b",
            r"\bwill do\b", r"\bassign\b", r"\bschedule\b", r"\bcan\b",
            r"\bwill\s+\w+\b",  # "will implement", "will check"
            r"\bby\s+(tomorrow|monday|friday|\d{1,2}/\d{1,2})",
            r"\bdeadline\b", r"\bdue\b", r"\bdone by\b",
            r"\bstart\b", r"\bbegin\b", r"\bcreate\b", r"\bset up\b",
            r"\bPR\b", r"\bpull request\b", r"\bcommit\b", r"\bmerge\b",
        ],
        ValueDimension.CLARITY: [
            r"\bbecause\b", r"\bsince\b", r"\btherefore\b",
            r"\bexample\b", r"\bfor instance\b", r"\bspecifically\b",
            r"\bmeans\b", r"\brefers to\b", r"\bdefined as\b",
        ],
    }
    
    # === NOISE INDICATORS (expanded) ===
    
    NOISE_INDICATORS = [
        r"^\s*👍\s*$", r"^\s*👆\s*$", r"^\s*✅\s*$",
        r"^\s*yes\s*$", r"^\s*no\s*$",
        r"^\s*agreed\s*$", r"^\s*agree\s*$",
        r"^\s*ok\s*$", r"^\s*okay\s*$", r"^\s*k\s*$",
        r"^\s*nice\s*$", r"^\s*cool\s*$", r"^\s*great\s*$",
        r"^\s*thanks?\s*$", r"^\s*ty\s*$", r"^\s*thx\s*$",
        r"^\s*hello\s*$", r"^\s*hi\s*$", r"^\s*hey\s*$",
        r"^\s*lol\s*$", r"^\s*haha\s*$", r"^\s*lmao\s*$",
        r"^\s*brb\s*$", r"^\s*afk\s*$", r"^\s*gtg\s*$",
        r"good morning\b.*\bgood morning\b",  # Circular greetings
        r"how are you.*\?",
    ]
    
    # === POSITIVE SIGNALS (new) ===
    # These boost score even if they don't match dimension patterns
    
    HIGH_VALUE_SIGNALS = [
        r"\?\s*$",  # Questions (seeking information)
        r"\bthoughts\?\b", r"\bopinion\?\b", r"\bfeedback\?\b",
        r"@\w+",  # Mentions (engaging others)
    ]
    
    # === CONTEXT-AWARE THRESHOLDS (new) ===
    
    THRESHOLDS = {
        ConversationContext.HUMAN_TO_AGENT: 0.30,
        ConversationContext.AGENT_TO_AGENT_EARLY: 0.25,  # Allow early clarifications
        ConversationContext.AGENT_TO_AGENT_MATURE: 0.45,
        ConversationContext.AGENT_UNSOLICITED: 0.70,
    }
    
    # === LIMITS ===
    
    MAX_CONVERSATION_LENGTH = 12  # Increased from 8
    MAX_CONVERSATION_MINUTES = 10  # Increased from 5
    
    def __init__(self):
        self.dimension_weights = {
            ValueDimension.TASK_CONNECTION: 0.30,    # Increased - task relevance is key
            ValueDimension.NEW_INFORMATION: 0.30,    # Increased - novelty matters
            ValueDimension.RESOLUTION: 0.15,         # Decreased - not all messages resolve
            ValueDimension.ACTIONABILITY: 0.15,      # Decreased - early messages lack this
            ValueDimension.CLARITY: 0.10,
        }
    
    def score_message(self, content: str, author: str = "") -> ValueScore:
        """Score a single message with improved algorithm."""
        content_lower = content.lower().strip()
        
        # Check for noise first
        for pattern in self.NOISE_INDICATORS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return ValueScore(
                    total_score=0.15,
                    dimension_scores={d: 0.1 for d in ValueDimension},
                    reason="Acknowledgment/short response",
                    should_continue=True,  # Don't block these, just don't expand
                    recommended_depth='skip'
                )
        
        # Score each dimension
        dimension_scores = {}
        for dimension, patterns in self.VALUE_INDICATORS.items():
            score = 0.0
            match_count = 0
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    match_count += len(matches)
                    score += min(len(matches) * 0.3, 1.0)  # Higher per-match value
            # Boost for multiple unique pattern matches
            if match_count >= 3:
                score = min(1.0, score * 1.2)
            dimension_scores[dimension] = min(score, 1.0)
        
        # Calculate weighted total
        total = sum(
            dimension_scores[d] * self.dimension_weights[d]
            for d in ValueDimension
        )
        
        # Boost for high-value signals
        for pattern in self.HIGH_VALUE_SIGNALS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                total = min(1.0, total + 0.08)
                break
        
        # Boost for legitimate questions (seeking information)
        if '?' in content and len(content) > 15:
            # Check if it's a substantive question, not just "ok?" or "right?"
            question_words = ['what', 'how', 'why', 'when', 'where', 'who', 'which', 'can', 'could', 'would', 'will', 'is', 'are', 'does', 'do']
            if any(qw in content_lower for qw in question_words):
                total = min(1.0, total + 0.15)
        
        # Length adjustments - more generous for technical content
        word_count = len(content.split())
        char_count = len(content)
        
        if 10 <= word_count <= 250:
            # Sweet spot: substantive but not overwhelming
            total = min(1.0, total + 0.08)
        elif word_count < 4:
            # Very short - likely low value
            total *= 0.7
        elif word_count > 400:
            # Very long - might be rambling
            total *= 0.95
        
        # Code content bonus (technical substance)
        code_blocks = len(re.findall(r'```', content))
        inline_code = len(re.findall(r'`[^`]+`', content))
        if code_blocks >= 2:
            total = min(1.0, total + 0.15)
        elif inline_code >= 1:
            total = min(1.0, total + 0.08)
        
        # Determine recommended response depth
        if total >= 0.75:
            depth = 'deep'
        elif total >= 0.55:
            depth = 'substantive'
        elif total >= 0.35:
            depth = 'brief'
        else:
            depth = 'skip'
        
        # Generate reason
        top_dimensions = sorted(
            dimension_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:2]
        
        if total >= 0.6:
            reason = f"Strong in: {', '.join(d.value for d, s in top_dimensions if s > 0.3)}"
        elif total >= 0.35:
            reason = f"Moderate value - brief response recommended"
        else:
            reason = "Low value - consider emoji reaction only"
        
        should_continue = total >= 0.25  # More permissive
        
        return ValueScore(
            total_score=round(total, 2),
            dimension_scores=dimension_scores,
            reason=reason,
            should_continue=should_continue,
            recommended_depth=depth
        )
    
    def score_conversation(self, messages: List[Dict]) -> ValueScore:
        """Score an entire conversation thread with improved aggregation."""
        if not messages:
            return ValueScore(
                0.0, {}, "Empty conversation", False, 'skip'
            )
        
        # Score individual messages
        message_scores = []
        for msg in messages:
            content = msg.get("content", "")
            score = self.score_message(content)
            message_scores.append(score)
        
        # Weight recent messages more heavily
        weights = [0.5 + 0.5 * (i / len(messages)) for i in range(len(messages))]
        weight_sum = sum(weights)
        
        avg_total = sum(
            s.total_score * w for s, w in zip(message_scores, weights)
        ) / weight_sum
        
        # Aggregate dimension scores
        dimension_avgs = {}
        for dim in ValueDimension:
            dim_scores = [
                s.dimension_scores.get(dim, 0) * w 
                for s, w in zip(message_scores, weights)
            ]
            dimension_avgs[dim] = sum(dim_scores) / weight_sum if dim_scores else 0
        
        # Check trajectory (is conversation improving?)
        if len(message_scores) >= 3:
            first_half = sum(s.total_score for s in message_scores[:len(message_scores)//2])
            second_half = sum(s.total_score for s in message_scores[len(message_scores)//2:])
            if second_half > first_half * 1.2:
                avg_total = min(1.0, avg_total + 0.05)  # Boost improving conversations
        
        # Length penalties (gentler than before)
        if len(messages) >= self.MAX_CONVERSATION_LENGTH:
            avg_total *= 0.9
        
        # Determine continuation and depth
        if avg_total >= 0.7:
            depth = 'substantive'
            should_continue = len(messages) < self.MAX_CONVERSATION_LENGTH
        elif avg_total >= 0.45:
            depth = 'brief'
            should_continue = len(messages) < self.MAX_CONVERSATION_LENGTH - 2
        else:
            depth = 'skip'
            should_continue = len(messages) < 4  # Allow short low-value convos
        
        # Generate summary reason
        if avg_total >= 0.75:
            reason = "High-value conversation with productive exchange"
        elif avg_total >= 0.55:
            reason = "Valuable conversation meeting usefulness criteria"
        elif avg_total >= 0.35:
            reason = "Moderate value - recommend focused continuation"
        else:
            reason = "Low value - recommend conclusion or refocus"
        
        return ValueScore(
            total_score=round(avg_total, 2),
            dimension_scores=dimension_avgs,
            reason=reason,
            should_continue=should_continue,
            recommended_depth=depth
        )
    
    def should_agent_respond(
        self, 
        message_content: str, 
        conversation_history: List[Dict],
        context: Optional[Dict] = None
    ) -> Tuple[bool, str, Dict]:
        """
        Determine if an agent should respond to a message.
        
        Args:
            message_content: The message that triggered consideration
            conversation_history: Prior messages in conversation
            context: Optional dict with 'is_human', 'is_agent', 'convo_length', 'agent_role'
        
        Returns:
            Tuple of (should_respond, reason, metadata)
            metadata includes: recommended_depth, confidence, suggested_tone
        """
        context = context or {}
        is_human = context.get('is_human', False)
        is_agent_speaking = context.get('is_agent', False)
        convo_length = context.get('convo_length', len(conversation_history))
        
        # Score the triggering message
        message_score = self.score_message(message_content)
        
        # Score the conversation so far
        conversation_score = self.score_conversation(conversation_history)
        
        # Select appropriate threshold
        if is_human:
            ctx = ConversationContext.HUMAN_TO_AGENT
        elif is_agent_speaking and convo_length < 3:
            ctx = ConversationContext.AGENT_TO_AGENT_EARLY
        elif is_agent_speaking:
            ctx = ConversationContext.AGENT_TO_AGENT_MATURE
        else:
            ctx = ConversationContext.AGENT_UNSOLICITED
        
        threshold = self.THRESHOLDS[ctx]
        
        metadata = {
            'message_score': message_score.total_score,
            'conversation_score': conversation_score.total_score,
            'recommended_depth': message_score.recommended_depth,
            'context': ctx.value,
            'threshold': threshold,
        }
        
        # Decision logic with detailed reasoning
        
        # 1. Very low value triggers - skip
        if message_score.total_score < 0.20:
            return False, f"Trigger lacks substance ({message_score.total_score:.2f})", metadata
        
        # 2. Check if conversation should conclude
        if convo_length >= self.MAX_CONVERSATION_LENGTH:
            metadata['recommended_depth'] = 'skip'
            return False, "Conversation at length limit", metadata
        
        # 3. Apply context-appropriate threshold
        if message_score.total_score < threshold:
            # But allow responses to questions even if low score
            if '?' in message_content:
                metadata['recommended_depth'] = 'brief'
                return True, f"Question detected - brief response", metadata
            return False, f"Below {ctx.value} threshold ({message_score.total_score:.2f} < {threshold})", metadata
        
        # 4. Check conversation health
        if not conversation_score.should_continue and convo_length > 5:
            metadata['recommended_depth'] = 'skip'
            return False, f"Conversation winding down ({conversation_score.reason})", metadata
        
        # 5. Determine response depth
        if message_score.total_score >= 0.7:
            depth = 'substantive'
        elif message_score.total_score >= 0.45:
            depth = message_score.recommended_depth
        else:
            depth = 'brief'
        
        metadata['recommended_depth'] = depth
        
        return True, f"Valuable context ({ctx.value}, score: {message_score.total_score:.2f})", metadata
    
    def validate_response(
        self,
        response_content: str,
        trigger_message: str,
        conversation_history: List[Dict],
        agent_role: str
    ) -> ResponseValidation:
        """
        POST-GENERATION validation: Check if a generated response is worth sending.
        
        This prevents generic template responses from being sent.
        """
        # Score the response itself
        response_score = self.score_message(response_content)
        
        # Score hypothetical future conversation
        hypothetical_convo = conversation_history + [
            {"author": agent_role, "content": response_content}
        ]
        future_score = self.score_conversation(hypothetical_convo)
        
        current_score = self.score_conversation(conversation_history)
        
        # Check for generic/template patterns
        generic_patterns = [
            r"^@\w+\s+Noted\.",
            r"^@\w+\s+Acknowledged",
            r"^@\w+\s+Understood",
            r"The Council notes",
            r"interesting( data)? point",
            r"building on what",
            r"from a \w+ perspective",
        ]
        
        generic_count = sum(
            1 for p in generic_patterns 
            if re.search(p, response_content, re.IGNORECASE)
        )
        
        # Check if response actually addresses trigger message
        trigger_words = set(re.findall(r'\b\w{4,}\b', trigger_message.lower()))
        response_words = set(re.findall(r'\b\w{4,}\b', response_content.lower()))
        word_overlap = len(trigger_words & response_words)
        
        # Quality assessment
        quality_issues = []
        
        if generic_count >= 2:
            quality_issues.append("too generic")
        
        if word_overlap < 2 and len(trigger_words) > 5:
            quality_issues.append("lacks topical connection")
        
        if response_score.total_score < current_score.total_score:
            quality_issues.append("response lowers conversation value")
        
        if len(response_content.split()) < 5:
            quality_issues.append("too brief")
        
        # Calculate quality score
        base_quality = response_score.total_score
        if generic_count > 0:
            base_quality -= 0.1 * generic_count
        if word_overlap < 2:
            base_quality -= 0.15
        
        quality_score = max(0.0, min(1.0, base_quality))
        
        # Decision
        if quality_issues:
            return ResponseValidation(
                should_send=False,
                reason=f"Response quality issues: {', '.join(quality_issues)}",
                quality_score=quality_score,
                suggested_improvement="Add specific details from trigger message"
            )
        
        if quality_score < 0.35:
            return ResponseValidation(
                should_send=False,
                reason=f"Response too low value ({quality_score:.2f})",
                quality_score=quality_score,
                suggested_improvement="Consider emoji reaction instead"
            )
        
        return ResponseValidation(
            should_send=True,
            reason=f"Response adds value ({quality_score:.2f})",
            quality_score=quality_score
        )
    
    def generate_summary(self, messages: List[Dict]) -> str:
        """Generate improved conversation summary with action items."""
        if not messages:
            return "No conversation to summarize."
        
        # Extract key participants
        authors = list(set(m.get("author", "Unknown") for m in messages))
        
        # Score the conversation
        score = self.score_conversation(messages)
        
        # Extract action items (improved heuristic)
        action_items = []
        decisions = []
        questions = []
        
        for m in messages:
            content = m.get("content", "")
            author = m.get("author", "Unknown")
            content_lower = content.lower()
            
            # Action items
            if any(kw in content_lower for kw in ["will", "should", "need to", "todo", "action", "by tomorrow", "by friday"]):
                sentences = re.split(r'[.!?]+', content)
                for sent in sentences:
                    if any(kw in sent.lower() for kw in ["will", "should", "need to", "todo", "going to"]):
                        action_items.append(f"• {author}: {sent.strip()[:100]}")
                        break
            
            # Decisions
            if any(kw in content_lower for kw in ["decided", "conclusion", "agreed", "going with", "we'll use"]):
                decisions.append(f"• {content[:100]}...")
            
            # Open questions
            if '?' in content and not content_lower.startswith(("what do you think", "any thoughts")):
                questions.append(f"• {author}: {content[:80]}...")
        
        # Build summary
        lines = [
            "📋 **Conversation Summary**",
            f"**Participants:** {', '.join(authors[:4])}{'...' if len(authors) > 4 else ''}",
            f"**Messages:** {len(messages)} | **Value Score:** {score.total_score:.0%}",
            "",
        ]
        
        if decisions:
            lines.extend(["**Decisions Made:**", *decisions[:3], ""])
        
        if action_items:
            lines.extend(["**Action Items:**", *action_items[:5], ""])
        
        if questions and len(questions) <= 3:
            lines.extend(["**Open Questions:**", *questions, ""])
        
        if score.total_score < 0.4:
            lines.append("*Note: This conversation had low measured value. Consider more focused discussions in the future.*")
        
        return "\n".join(lines)


# Global scorer instance
_value_scorer: Optional[ConversationValueScorer] = None


def get_scorer() -> ConversationValueScorer:
    """Get or create the global value scorer."""
    global _value_scorer
    if _value_scorer is None:
        _value_scorer = ConversationValueScorer()
    return _value_scorer


if __name__ == "__main__":
    # Test the improved scorer
    scorer = ConversationValueScorer()
    
    print("=" * 60)
    print("VALUE SCORER V2 TEST SUITE")
    print("=" * 60)
    
    # Test 1: Early brainstorming (should pass with lower threshold)
    print("\n--- Test 1: Early Clarification Question ---")
    test_early = [
        {"author": "Kublai", "content": "We need to decide on the deployment strategy for the engagement tracker. The moltbook API is now available."},
        {"author": "Temüjin", "content": "What options are we considering for the rollout?"},
    ]
    
    result = scorer.should_agent_respond(
        "What options are we considering for the rollout?",
        test_early,
        {'is_agent': True, 'convo_length': 2}
    )
    print(f"Should respond: {result[0]}")
    print(f"Reason: {result[1]}")
    print(f"Recommended depth: {result[2]['recommended_depth']}")
    
    # Test 2: Substantive technical message
    print("\n--- Test 2: Technical Finding ---")
    test_msg = "Found the issue in auth.py. The redirect URL isn't matching what we registered in the OAuth app."
    score = scorer.score_message(test_msg)
    print(f"Score: {score.total_score}")
    print(f"Dimensions: {score.dimension_scores}")
    print(f"Reason: {score.reason}")
    print(f"Recommended depth: {score.recommended_depth}")
    
    # Test 3: Low-value acknowledgment
    print("\n--- Test 3: Low-value Acknowledgment ---")
    ack_msg = "ok thanks"
    score2 = scorer.score_message(ack_msg)
    print(f"Score: {score2.total_score}")
    print(f"Reason: {score2.reason}")
    print(f"Recommended depth: {score2.recommended_depth}")
    
    # Test 4: Response validation - bad generic response
    print("\n--- Test 4: Response Validation (Generic) ---")
    tech_convo = [
        {"author": "Kublai", "content": "Found the issue in auth.py. The redirect URL isn't matching what we registered."},
    ]
    bad_response = "@Kublai Noted. The Council incorporates this."
    validation = scorer.validate_response(
        bad_response,
        tech_convo[0]["content"],
        tech_convo,
        "Möngke"
    )
    print(f"Should send: {validation.should_send}")
    print(f"Reason: {validation.reason}")
    print(f"Quality score: {validation.quality_score:.2f}")
    
    # Test 5: Response validation - good specific response
    print("\n--- Test 5: Response Validation (Specific) ---")
    good_response = "@Kublai The OAuth redirect mismatch is a common issue. We need to verify the callback URL in both the app config and the environment variables."
    validation2 = scorer.validate_response(
        good_response,
        tech_convo[0]["content"],
        tech_convo,
        "Möngke"
    )
    print(f"Should send: {validation2.should_send}")
    print(f"Reason: {validation2.reason}")
    print(f"Quality score: {validation2.quality_score:.2f}")
    
    # Test 6: Full conversation scoring
    print("\n--- Test 6: Full Conversation Scoring ---")
    test_convo = [
        {"author": "Kublai", "content": "We need to decide on the deployment strategy. The moltbook API is now available."},
        {"author": "Temüjin", "content": "I can implement that. The endpoint is confirmed at /api/v1/posts. Will have it done by Friday."},
        {"author": "Möngke", "content": "The data shows we should track engagement scores to identify trending topics."},
    ]
    convo_score = scorer.score_conversation(test_convo)
    print(f"Conversation score: {convo_score.total_score}")
    print(f"Reason: {convo_score.reason}")
    print(f"Should continue: {convo_score.should_continue}")
    print(f"Recommended depth: {convo_score.recommended_depth}")
    
    # Test 7: Summary generation
    print("\n--- Test 7: Summary Generation ---")
    print(scorer.generate_summary(test_convo))
    
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)
