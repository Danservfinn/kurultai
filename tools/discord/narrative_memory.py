"""
Narrative Memory for Kurultai

Allows agents to reference past conversations, creating continuity.
Makes interactions feel like ongoing relationships, not isolated messages.
"""

class NarrativeMemory:
    """Tracks what agents have said to enable callbacks and references."""
    
    def __init__(self, max_history=50):
        self.history = []
        self.themes = {}  # Recurring topics
        self.max_history = max_history
    
    def record(self, agent, content, channel, timestamp=None):
        """Record an agent message."""
        from datetime import datetime
        
        entry = {
            "agent": agent,
            "content": content,
            "channel": channel,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
        }
        self.history.append(entry)
        
        # Trim old history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def get_recent_topics(self, hours=24):
        """Get topics discussed recently."""
        # Simple keyword extraction
        recent = [h for h in self.history if self._within_hours(h, hours)]
        
        # Extract potential topics (words in quotes, capitalized phrases)
        topics = []
        for entry in recent:
            content = entry["content"]
            # Find quoted phrases
            import re
            quoted = re.findall(r'"([^"]+)"', content)
            topics.extend(quoted)
        
        return list(set(topics))[:5]  # Top 5 unique topics
    
    def get_agent_last_message(self, agent):
        """Get the last message from a specific agent."""
        for entry in reversed(self.history):
            if entry["agent"] == agent:
                return entry
        return None
    
    def _within_hours(self, entry, hours):
        """Check if entry is within N hours."""
        from datetime import datetime, timedelta
        
        entry_time = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return entry_time > cutoff
    
    def generate_callback(self, agent):
        """Generate a reference to something previously discussed."""
        topics = self.get_recent_topics(hours=48)
        
        if not topics:
            return None
        
        topic = random.choice(topics)
        callbacks = [
            f"Going back to what we discussed about '{topic}'...",
            f"I've been thinking more about '{topic}' since our last conversation.",
            f"Related to our earlier discussion on '{topic}'...",
            f"Building on what {agent} said about '{topic}'...",
        ]
        
        return random.choice(callbacks)


import random
