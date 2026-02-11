"""
Conversation Value Scorer
Implements the Value-First Protocol for Discord agent conversations.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import re


class ValueDimension(Enum):
    """Dimensions for scoring conversation value."""
    TASK_CONNECTION = "task_connection"      # Connected to actual work
    NEW_INFORMATION = "new_information"      # Provides novel insights
    RESOLUTION = "resolution"                # Moves toward a decision/solution
    ACTIONABILITY = "actionability"          # Leads to concrete next steps


@dataclass
class ValueScore:
    """Value score for a conversation or message."""
    total_score: float  # 0.0-1.0
    dimension_scores: Dict[ValueDimension, float]
    reason: str
    should_continue: bool
    
    @property
    def is_valuable(self) -> bool:
        """Whether conversation meets value threshold."""
        return self.total_score >= 0.6


class ConversationValueScorer:
    """
    Scores Discord conversations on value metrics.
    Implements Value-First Protocol:
    - Must have [GOAL] declared
    - Must produce mandatory summary
    - Must score >0.6 on value metrics
    """
    
    # Patterns that indicate valuable content
    VALUE_INDICATORS = {
        ValueDimension.TASK_CONNECTION: [
            r"\btask\b", r"\bproject\b", r"\bimplement\b", r"\bbuild\b",
            r"\bdeploy\b", r"\btest\b", r"\bfix\b", r"\bcomplete\b",
            r"\bwork\b", r"\bintegration\b", r"\bsystem\b",
            r"#\w+",  # Task references
            r"notion", r"github", r"railway", r"moltbook", r"discord",
        ],
        ValueDimension.NEW_INFORMATION: [
            r"\bfound\b", r"\bdiscovered\b", r"\bdiscovered\b", r"\blearned\b",
            r"\banalysis\b", r"\bresearch\b", r"\bdata\b", r"\bmetric",
            r"\bpattern\b", r"\binsight\b", r"\bobserved\b", r"\btrack\b",
            r"https?://",  # Links to resources
            r"\d+\.?\d*",  # Numbers/metrics
            r"\bapi\b", r"\bendpoint\b", r"\bdatabase\b",
        ],
        ValueDimension.RESOLUTION: [
            r"\bdecided\b", r"\bconclusion\b", r"\bresolution\b", r"\bagreed\b",
            r"\bthe answer is\b", r"\bsolution\b", r"\bresolved\b",
            r"\bwe should\b", r"\blet's\b", r"\bgoing with\b", r"\bneed to\b",
            r"\bstrategy\b", r"\bplan\b", r"\bapproach\b",
        ],
        ValueDimension.ACTIONABILITY: [
            r"\bnext step\b", r"\baction item\b", r"\btodo\b",
            r"\bwill do\b", r"\bassign\b", r"\bschedule\b", r"\bcan\b",
            r"\bby\s+(tomorrow|monday|friday|\d{1,2}/\d{1,2})",  # Deadlines
            r"\bdeadline\b", r"\bdue\b", r"\bdone by\b",
        ],
    }
    
    # Patterns that indicate low-value chatter
    NOISE_INDICATORS = [
        r"^\s*👍\s*$",  # Just thumbs up
        r"^\s*yes\s*$",
        r"^\s*agreed\s*$",
        r"^\s*ok\s*$",
        r"^\s*nice\s*$",
        r"^\s*thanks?\s*$",
        r"good morning\b.*\bgood morning\b",  # Circular greetings
        r"^\s*hello\s*$",
        r"^\s*hi\s*$",
        r"how are you.*\?",  # Generic pleasantries
        r"^\s*lol\s*$",
        r"^\s*haha\s*$",
    ]
    
    # Minimum thresholds
    MIN_VALUE_THRESHOLD = 0.6
    MAX_CONVERSATION_LENGTH = 8  # messages
    MAX_CONVERSATION_MINUTES = 5
    
    def __init__(self):
        self.dimension_weights = {
            ValueDimension.TASK_CONNECTION: 0.3,
            ValueDimension.NEW_INFORMATION: 0.25,
            ValueDimension.RESOLUTION: 0.25,
            ValueDimension.ACTIONABILITY: 0.2,
        }
    
    def score_message(self, content: str, author: str = "") -> ValueScore:
        """Score a single message."""
        content_lower = content.lower()
        
        # Check for noise first
        for pattern in self.NOISE_INDICATORS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return ValueScore(
                    total_score=0.1,
                    dimension_scores={d: 0.1 for d in ValueDimension},
                    reason="Low-value response (noise)",
                    should_continue=False
                )
        
        # Score each dimension
        dimension_scores = {}
        for dimension, patterns in self.VALUE_INDICATORS.items():
            score = 0.0
            for pattern in patterns:
                matches = len(re.findall(pattern, content, re.IGNORECASE))
                score += min(matches * 0.2, 0.8)  # Cap at 0.8 per dimension
            dimension_scores[dimension] = min(score, 1.0)
        
        # Calculate weighted total
        total = sum(
            dimension_scores[d] * self.dimension_weights[d]
            for d in ValueDimension
        )
        
        # Boost for substantive length (but not too long)
        word_count = len(content.split())
        if 20 <= word_count <= 150:
            total = min(1.0, total + 0.1)
        
        # Determine if conversation should continue
        should_continue = total >= self.MIN_VALUE_THRESHOLD
        
        # Generate reason
        top_dimensions = sorted(
            dimension_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:2]
        reason = f"Strong in: {', '.join(d.value for d, s in top_dimensions if s > 0.3)}"
        if total < self.MIN_VALUE_THRESHOLD:
            reason = "Below value threshold - consider concluding"
        
        return ValueScore(
            total_score=round(total, 2),
            dimension_scores=dimension_scores,
            reason=reason,
            should_continue=should_continue
        )
    
    def score_conversation(self, messages: List[Dict]) -> ValueScore:
        """Score an entire conversation thread."""
        if not messages:
            return ValueScore(0.0, {}, "Empty conversation", False)
        
        # Score individual messages
        message_scores = []
        for msg in messages:
            content = msg.get("content", "")
            score = self.score_message(content)
            message_scores.append(score)
        
        # Calculate aggregate scores
        avg_total = sum(s.total_score for s in message_scores) / len(message_scores)
        
        # Aggregate dimension scores
        dimension_avgs = {}
        for dim in ValueDimension:
            dim_scores = [s.dimension_scores.get(dim, 0) for s in message_scores]
            dimension_avgs[dim] = sum(dim_scores) / len(dim_scores) if dim_scores else 0
        
        # Check conversation length limits
        conversation_value = avg_total
        if len(messages) >= self.MAX_CONVERSATION_LENGTH:
            conversation_value *= 0.8  # Penalty for dragging on
        
        # Determine continuation
        should_continue = (
            conversation_value >= self.MIN_VALUE_THRESHOLD
            and len(messages) < self.MAX_CONVERSATION_LENGTH
        )
        
        # Generate summary reason
        if conversation_value >= 0.8:
            reason = "High-value conversation with productive exchange"
        elif conversation_value >= 0.6:
            reason = "Valuable conversation meeting usefulness criteria"
        elif conversation_value >= 0.4:
            reason = "Moderate value - consider refocusing"
        else:
            reason = "Low value - recommend conclusion"
        
        return ValueScore(
            total_score=round(conversation_value, 2),
            dimension_scores=dimension_avgs,
            reason=reason,
            should_continue=should_continue
        )
    
    def should_agent_respond(self, message_content: str, conversation_history: List[Dict]) -> tuple[bool, str]:
        """
        Determine if an agent should respond to a message.
        Returns (should_respond, reason)
        """
        # Score the triggering message
        message_score = self.score_message(message_content)
        
        # Score the conversation so far
        conversation_score = self.score_conversation(conversation_history)
        
        # Decision logic
        if message_score.total_score < 0.3:
            return False, f"Low-value trigger ({message_score.total_score}) - skip"
        
        if not conversation_score.should_continue:
            return False, f"Conversation should conclude ({conversation_score.reason})"
        
        if len(conversation_history) >= self.MAX_CONVERSATION_LENGTH:
            return False, "Max conversation length reached"
        
        # Check if adding value is likely
        if conversation_score.total_score >= 0.6:
            return True, f"Valuable conversation ({conversation_score.total_score}) - contribute"
        
        return False, f"Below value threshold ({conversation_score.total_score})"
    
    def generate_summary(self, messages: List[Dict]) -> str:
        """Generate mandatory conversation summary."""
        if not messages:
            return "No conversation to summarize."
        
        # Extract key participants
        authors = list(set(m.get("author", "Unknown") for m in messages))
        
        # Count messages by author
        author_counts = {}
        for m in messages:
            author = m.get("author", "Unknown")
            author_counts[author] = author_counts.get(author, 0) + 1
        
        # Score the conversation
        score = self.score_conversation(messages)
        
        # Extract action items (simple heuristic)
        actions = []
        for m in messages:
            content = m.get("content", "").lower()
            if any(kw in content for kw in ["will", "should", "need to", "todo", "action"]):
                # Extract the sentence containing action keywords
                sentences = content.split(".")
                for sent in sentences:
                    if any(kw in sent for kw in ["will", "should", "need to", "todo"]):
                        actions.append(f"• {sent.strip()[:80]}")
                        break
        
        lines = [
            "📋 **Conversation Summary**",
            f"**Participants:** {', '.join(authors[:4])}",
            f"**Messages:** {len(messages)}",
            f"**Value Score:** {score.total_score:.0%} ({score.reason})",
            "",
        ]
        
        if actions:
            lines.append("**Action Items:**")
            lines.extend(actions[:5])  # Top 5
        else:
            lines.append("**Key Points:**")
            # Extract a key message from each major participant
            for author in authors[:3]:
                for m in messages:
                    if m.get("author") == author and len(m.get("content", "")) > 30:
                        lines.append(f"• {author}: {m.get('content', '')[:60]}...")
                        break
        
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
    # Test the scorer
    scorer = ConversationValueScorer()
    
    test_messages = [
        {"author": "Kublai", "content": "We need to decide on the deployment strategy for the engagement tracker. The moltbook API is now available."},
        {"author": "Temüjin", "content": "I can implement that. The endpoint is confirmed at www.moltbook.com/api/v1/posts. Will have it done by tomorrow."},
        {"author": "Möngke", "content": "The data shows we should track engagement scores over time to identify trending topics."},
    ]
    
    score = scorer.score_conversation(test_messages)
    print(f"Conversation score: {score.total_score}")
    print(f"Reason: {score.reason}")
    print(f"Should continue: {score.should_continue}")
    print()
    print(scorer.generate_summary(test_messages))
