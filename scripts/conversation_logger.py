#!/usr/bin/env python3
"""
Conversation Logger - Automatic logging of all human conversations with privacy controls

This module provides:
1. Automatic conversation capture from Signal and other channels
2. Privacy controls (file permissions, access checks)
3. Search and retrieval functionality
4. Integration with human_profile_memory.py

Usage:
    from conversation_logger import log_conversation, search_conversations

    # Log a message
    log_conversation("+19194133445", {
        "direction": "inbound",
        "content": "Hello world",
        "channel": "signal"
    })

    # Search conversations
    results = search_conversations("+19194133445", "authentication")
"""

import os
import re
import json
import stat
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Import existing memory system
import sys
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from human_profile_memory import HumanProfileMemory

# Configuration
MEMORY_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans"
ARCHIVE_DIR = MEMORY_DIR / "archive"
CONVERSATION_INDEX_DIR = MEMORY_DIR / "index"
MAX_CONVERSATIONS_IN_FILE = 50
MAX_ARCHIVE_FILES = 12  # Keep up to 12 monthly archives


class ConversationLogger:
    """Manages persistent conversation storage with privacy controls."""

    def __init__(self, agent_name: str = "main"):
        self.agent_name = agent_name
        self.memory = HumanProfileMemory(agent_name)
        self._ensure_directories()

    def _get_index_file(self, phone_number: str) -> Path:
        """Get the JSON index file path for a user's conversations."""
        normalized = self.memory._normalize_id(phone_number)
        return CONVERSATION_INDEX_DIR / f"{normalized}.json"

    def _ensure_directories(self) -> None:
        """Create directories with proper permissions and verify them."""
        # Main memory dir
        self.memory.memory_dir.mkdir(parents=True, exist_ok=True)

        # Archive dir
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        # Index dir
        CONVERSATION_INDEX_DIR.mkdir(parents=True, exist_ok=True)

        # Set directory permissions to 700 (owner only) and verify
        self._verify_and_set_permissions(self.memory.memory_dir, is_dir=True)
        self._verify_and_set_permissions(ARCHIVE_DIR, is_dir=True)
        self._verify_and_set_permissions(CONVERSATION_INDEX_DIR, is_dir=True)

    def _verify_and_set_permissions(self, path: Path, is_dir: bool = True) -> bool:
        """
        Verify and set correct permissions on a file or directory.

        Args:
            path: Path to verify/set permissions on
            is_dir: True if path is a directory, False if file

        Returns:
            True if permissions are correct, False otherwise
        """
        if not path.exists():
            return False

        try:
            if is_dir:
                os.chmod(path, stat.S_IRWXU)  # 700 - owner read/write/execute only
                expected_mode = "700"
            else:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600 - owner read/write only
                expected_mode = "600"

            actual_mode = oct(path.stat().st_mode)[-3:]
            if actual_mode != expected_mode:
                print(f"Warning: Incorrect permissions on {path}. Current: {actual_mode}, Expected: {expected_mode}")
                return False
            return True
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not set permissions on {path}: {e}")
            return False

    def _get_index_file(self, phone_number: str) -> Path:
        """Get the JSON index file path for a user's conversations."""
        normalized = self.memory._normalize_id(phone_number)
        return CONVERSATION_INDEX_DIR / f"{normalized}.json"

    def _load_conversation_index(self, phone_number: str) -> List[Dict[str, Any]]:
        """Load conversations from JSON index."""
        index_file = self._get_index_file(phone_number)
        if index_file.exists():
            try:
                return json.loads(index_file.read_text())
            except (json.JSONDecodeError, Exception):
                return []
        return []

    def _set_file_permissions(self, file_path: Path) -> None:
        """Set file permissions to 600 (owner read/write only)."""
        if file_path.exists():
            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)

    def _extract_topics(self, content: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Extract key topics from message content with scoring.

        Args:
            content: Message content to analyze
            conversation_history: Optional list of past conversations for frequency weighting

        Returns:
            List of topic dicts with keys: topic, type, domain, score
        """
        topics = []

        # 1. Domain-specific keyword lists
        domain_keywords = {
            "technical": [
                "authentication", "deployment", "database", "api", "frontend", "backend",
                "performance", "testing", "security", "infrastructure", "microservices",
                "container", "orchestration", "monitoring", "scaling", "load balancing",
                "caching", "cdn", "websocket", "graphql", "rest", "grpc",
                "deploy", "bug", "feature", "test", "review", "merge", "release", "config",
                "code", "function", "class", "pr", "commit", "build", "implement"
            ],
            "business": [
                "revenue", "customer", "sales", "pricing", "subscription", "metrics",
                "growth", "churn", "retention", "acquisition", "conversion", "funnel",
                "lifecycle", "upsell", "cross-sell", "discount", "promotion",
                "user", "business", "product", "service", "market", "competition"
            ],
            "personal": [
                "coffee", "lunch", "break", "vacation", "weekend", "family",
                "health", "exercise", "gym", "doctor", "appointment", "birthday",
                "holiday", "dinner", "movie", "trip"
            ]
        }

        content_lower = content.lower()

        # Extract single-word keywords
        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    topics.append({
                        "topic": keyword,
                        "type": "keyword",
                        "domain": domain,
                        "score": 1.0
                    })

        # 2. Phrase extraction (2-3 word phrases)
        # Extract bigrams (2-word phrases)
        words = content.lower().split()
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]

        # Extract trigrams (3-word phrases)
        trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words)-2)]

        # Meaningful technical phrases
        technical_phrases = [
            "database migration", "api authentication", "user onboarding",
            "performance optimization", "security audit", "feature deployment",
            "customer feedback", "subscription model", "growth metrics",
            "a/b testing", "continuous deployment", "load testing",
            "rate limiting", "data pipeline", "error handling",
            "user authentication", "access control", "data encryption"
        ]

        # Check bigrams and trigrams against meaningful phrases
        for phrase in technical_phrases:
            phrase_lower = phrase.lower()
            if phrase_lower in content_lower:
                # Check if it's a bigram or trigram match
                word_count = len(phrase.split())
                topics.append({
                    "topic": phrase,
                    "type": f"{word_count}-word phrase",
                    "domain": "technical",
                    "score": 1.5 if word_count == 2 else 2.0  # Trigrams worth more
                })

        # 3. Named entity recognition (regex-based)
        # Capitalized words (project names, companies)
        entities = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', content)
        common_exclusions = {
            "The", "This", "That", "I", "You", "We", "They", "It", "He", "She",
            "And", "But", "Or", "For", "With", "From", "Let", "Need", "Can", "Will",
            "Just", "Also", "Then", "When", "What", "How", "Where", "Why", "Who"
        }

        for entity in set(entities):
            if len(entity) > 2 and entity not in common_exclusions:
                # Clean up leading "The" from multi-word entities
                clean_entity = entity
                if clean_entity.startswith("The "):
                    clean_entity = clean_entity[4:]

                # Determine if it's likely a project name (appears capitalized mid-sentence)
                topics.append({
                    "topic": clean_entity,
                    "type": "entity",
                    "domain": "project",
                    "score": 1.3
                })

        # Extract @mentions (companies/users)
        mentions = re.findall(r'@(\w+)', content)
        for mention in set(mentions):
            topics.append({
                "topic": f"@{mention}",
                "type": "mention",
                "domain": "company",
                "score": 1.2
            })

        # Extract #hashtags (technologies/categories)
        hashtags = re.findall(r'#(\w+)', content)
        for tag in set(hashtags):
            topics.append({
                "topic": f"#{tag}",
                "type": "hashtag",
                "domain": "technology",
                "score": 1.4
            })

        # 4. Topic frequency weighting
        if conversation_history:
            topic_counts = {}
            for conv in conversation_history[-20:]:  # Last 20 conversations
                conv_topics = conv.get("topics", [])
                for topic in conv_topics:
                    # Handle both string format (old) and dict format (new)
                    if isinstance(topic, str):
                        topic_name = topic
                    elif isinstance(topic, dict):
                        topic_name = topic.get("topic", "")
                    else:
                        continue

                    if topic_name:
                        topic_counts[topic_name] = topic_counts.get(topic_name, 0) + 1

            # Boost recurring topics
            for topic in topics:
                topic_name = topic["topic"]
                if topic_name in topic_counts:
                    frequency_boost = min(topic_counts[topic_name] * 0.1, 0.5)
                    topic["score"] += frequency_boost

        # Sort by score and return top 10
        topics.sort(key=lambda t: t["score"], reverse=True)

        # Remove duplicates (keep highest scoring version)
        seen_topics = {}
        for topic in topics:
            topic_name = topic["topic"]
            if topic_name not in seen_topics:
                seen_topics[topic_name] = topic
            elif topic["score"] > seen_topics[topic_name]["score"]:
                seen_topics[topic_name] = topic

        # Return top 10 unique topics
        unique_topics = list(seen_topics.values())
        unique_topics.sort(key=lambda t: t["score"], reverse=True)

        return unique_topics[:10]

    def _normalize_topics(self, topics: List[Any]) -> List[str]:
        """
        Normalize topics to string format for backward compatibility.

        Args:
            topics: List of topics (strings or dicts)

        Returns:
            List of topic strings
        """
        normalized = []
        for topic in topics:
            if isinstance(topic, str):
                normalized.append(topic)
            elif isinstance(topic, dict):
                normalized.append(topic.get("topic", str(topic)))
            else:
                normalized.append(str(topic))
        return normalized

    def _extract_action_items(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract action items with metadata including assignee, priority, and deadlines.

        Returns structured action items with:
        - action: the action text
        - assignee: who committed to the action (self, other, shared, unassigned)
        - priority: high, medium, or low
        - deadline: extracted deadline category (if any)
        - source_pattern: how the action was detected
        """
        items = []

        # 1. Commitment patterns with assignee detection
        commitment_patterns = [
            # Self-commitments
            (r"(?:I will|I'll|I shall)\s+([^.!?]+)", "self"),
            (r"(?:Let me|I'll handle)\s+([^.!?]+)", "self"),
            (r"(?:Send|Get|Give)\s+(?:me|us)\s+([^.!?]+)", "self"),

            # Shared commitments
            (r"(?:We will|We'll)\s+([^.!?]+)", "shared"),
            (r"(?:Let's|Lets)\s+([^.!?]+)", "shared"),

            # Other-directed (delegation)
            (r"Can you\s+([^.!?]+)", "other"),
            (r"Could you\s+([^.!?]+)", "other"),
            (r"(?:Please|kindly)\s+([^.!?]+)", "other"),
            (r"(?:I need you to|You need to)\s+([^.!?]+)", "other"),

            # General obligation
            (r"(?:need to|should|must|have to)\s+([^.!?]+)", "unassigned"),
            (r"(?:has to|have got to)\s+([^.!?]+)", "unassigned"),
        ]

        for pattern, assignee in commitment_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                action = match.strip().strip(".,!?")
                if len(action) > 3:
                    items.append({
                        "action": action,
                        "assignee": assignee,
                        "priority": self._detect_priority(action + " " + content),
                        "deadline": self._extract_deadline(action + " " + content),
                        "source_pattern": "commitment"
                    })

        # 2. Task/delegation patterns (explicit markers)
        task_patterns = [
            r"todo:\s*([^.!?]+)",
            r"task:\s*([^.!?]+)",
            r"action item:\s*([^.!?]+)",
            r"\[([^\]]+)\]",  # [bracketed items]
        ]

        for pattern in task_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                action = match.strip()
                if len(action) > 3:
                    items.append({
                        "action": action,
                        "assignee": "unassigned",
                        "priority": self._detect_priority(action + " " + content),
                        "deadline": self._extract_deadline(action + " " + content),
                        "source_pattern": "task"
                    })

        # 3. Deduplicate by action text (case-insensitive)
        seen = set()
        unique_items = []
        for item in items:
            action_lower = item["action"].lower()
            if action_lower not in seen:
                seen.add(action_lower)
                unique_items.append(item)

        # Return top 5 action items
        return unique_items[:5]

    def _detect_priority(self, text: str) -> str:
        """
        Detect priority level from text.

        Returns:
            'high' for urgent/critical items
            'medium' for important/priority items
            'low' for normal items
        """
        text_lower = text.lower()

        # Urgent keywords
        urgent_words = ["asap", "urgent", "urgently", "immediately", "right now",
                       "emergency", "critical", "priority", "high priority",
                       "as soon as possible", "deadline", "overdue"]

        # Important keywords
        important_words = ["important", "significant", "essential", "must",
                          "key", "crucial", "vital", "necessary"]

        if any(word in text_lower for word in urgent_words):
            return "high"
        elif any(word in text_lower for word in important_words):
            return "medium"
        return "low"

    def _extract_deadline(self, text: str) -> Optional[str]:
        """
        Extract deadline information from text.

        Returns:
            Deadline category string (e.g., 'today', 'tomorrow', 'this_week', 'next_week', 'relative')
            None if no deadline detected
        """
        text_lower = text.lower()

        # Deadline patterns with categories
        deadline_patterns = [
            # Today (check this first as it's most specific)
            (r"\b(?:today|tonight|end of day|eod|close of business|cob)\b", "today"),
            (r"by\s+\d+(?:am|pm)\b", "today"),

            # Tomorrow
            (r"\btomorrow\b", "tomorrow"),

            # This week - day names
            (r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "this_week"),
            (r"by\s+this week\b", "this_week"),
            (r"end of week\b", "this_week"),

            # Next week
            (r"next\s+(?:week|monday|tuesday|wednesday|thursday|friday)\b", "next_week"),

            # Relative time
            (r"within\s+\d+\s+(?:hours?|hrs?|h|days?|d)\b", "relative"),
            (r"in\s+\d+\s+(?:hours?|hrs?|h|days?|d)\b", "relative"),

            # Specific dates (return as-is for parsing)
            (r"by\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}", "specific_date"),
            (r"by\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?", "specific_date"),
        ]

        for pattern, category in deadline_patterns:
            if re.search(pattern, text_lower):
                return category

        return None

    def _extract_event_mentions(self, content: str) -> List[str]:
        """
        Extract calendar event names from message content.

        Args:
            content: Message content to analyze

        Returns:
            List of event names (deduplicated, max 5)
        """
        events = []

        # Pattern 1: Quoted event names (highest priority)
        quoted_events = re.findall(r'"([^"]+)"', content)
        events.extend(quoted_events)

        # Pattern 2: Capitalized phrases with event keywords (more precise)
        # Match: Capitalized word(s) + event keyword (e.g., "Team Standup", "Project Review")
        event_keywords = ["meeting", "standup", "review", "call", "sync", "planning", "retro"]
        content_lower = content.lower()

        for keyword in event_keywords:
            if keyword in content_lower:
                # Extract 1-2 capitalized words before the keyword
                # Pattern: Word(s) + keyword, stop at non-capitalized or end
                pattern = rf'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+{keyword}\b'
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Reconstruct the full event name with proper capitalization
                    event_name = f"{match} {keyword}"

                    # Filter out matches that start with articles (case-insensitive)
                    if not re.match(r'^(?:the|a|an)\s', event_name, re.IGNORECASE):
                        events.append(event_name)

        # Pattern 3: Common event names (exact match, capitalized)
        common_events = [
            "Team Standup", "Sprint Review", "Planning Session",
            "Retrospective", "Weekly Sync", "Demo Day",
            "Daily Standup", "Sprint Planning", "Retrospective Meeting"
        ]
        for event in common_events:
            # Use word boundary for exact matching
            if re.search(rf'\b{re.escape(event)}\b', content, re.IGNORECASE):
                events.append(event)

        # Deduplicate and clean (case-insensitive)
        seen = set()
        cleaned = []
        for event in events:
            event_clean = event.strip()
            if event_clean and event_clean.lower() not in seen:
                seen.add(event_clean.lower())
                cleaned.append(event_clean)

        return cleaned[:5]

    def _extract_task_ids(self, content: str) -> List[str]:
        """
        Extract task IDs from message content.

        Args:
            content: Message content to analyze

        Returns:
            List of task IDs in format "task-XXXX" (deduplicated, max 5)
        """
        task_ids = []

        # Pattern 1: task-XXXX
        task_ids.extend(re.findall(r'task-(\d+)', content, re.IGNORECASE))

        # Pattern 2: #XXXX (4+ digits)
        task_ids.extend(re.findall(r'#(\d{4,})', content))

        # Pattern 3: issue-XXX
        task_ids.extend(re.findall(r'issue-(\d+)', content, re.IGNORECASE))

        # Normalize and deduplicate
        seen = set()
        normalized = []
        for task_id in task_ids:
            if task_id not in seen:
                seen.add(task_id)
                normalized.append(f"task-{task_id}")

        return normalized[:5]

    def _link_conversation_to_events(
        self,
        phone_number: str,
        conversation_date: str,
        event_names: List[str]
    ) -> None:
        """
        Link conversation to calendar events (bidirectional).

        Updates the user's profile JSON index to include event_links that reference
        conversations mentioning specific events.

        Args:
            phone_number: User's phone number
            conversation_date: ISO timestamp of conversation
            event_names: List of event names to link
        """
        if not event_names:
            return

        # Store event links in a separate JSON file for reliable querying
        links_file = CONVERSATION_INDEX_DIR / f"{self.memory._normalize_id(phone_number)}_event_links.json"

        # Load existing links
        if links_file.exists():
            try:
                event_links = json.loads(links_file.read_text())
            except:
                event_links = {}
        else:
            event_links = {}

        # Add conversation to each event
        for event_name in event_names:
            if event_name not in event_links:
                event_links[event_name] = []

            event_links[event_name].append({
                "conversation_date": conversation_date,
                "linked_at": datetime.now().isoformat()
            })

        # Save links
        links_file.parent.mkdir(parents=True, exist_ok=True)
        links_file.write_text(json.dumps(event_links, indent=2))
        self._set_file_permissions(links_file)

    def _link_conversation_to_tasks(
        self,
        phone_number: str,
        conversation_date: str,
        task_ids: List[str]
    ) -> None:
        """
        Link conversation to tasks (bidirectional).

        Updates the user's profile JSON index to include task_links that reference
        conversations mentioning specific tasks.

        Args:
            phone_number: User's phone number
            conversation_date: ISO timestamp of conversation
            task_ids: List of task IDs to link
        """
        if not task_ids:
            return

        # Store task links in a separate JSON file for reliable querying
        links_file = CONVERSATION_INDEX_DIR / f"{self.memory._normalize_id(phone_number)}_task_links.json"

        # Load existing links
        if links_file.exists():
            try:
                task_links = json.loads(links_file.read_text())
            except:
                task_links = {}
        else:
            task_links = {}

        # Add conversation to each task
        for task_id in task_ids:
            if task_id not in task_links:
                task_links[task_id] = []

            task_links[task_id].append({
                "conversation_date": conversation_date,
                "linked_at": datetime.now().isoformat()
            })

        # Save links
        links_file.parent.mkdir(parents=True, exist_ok=True)
        links_file.write_text(json.dumps(task_links, indent=2))
        self._set_file_permissions(links_file)

    def _set_file_permissions(self, file_path: Path) -> None:
        """Ensure file has 600 permissions (owner read/write only)."""
        if file_path.exists():
            self._verify_and_set_permissions(file_path, is_dir=False)

        # Also ensure parent directory has 700
        parent = file_path.parent
        if parent.exists():
            self._verify_and_set_permissions(parent, is_dir=True)

    def _detect_context(self, content: str) -> str:
        """Detect the context type of a message."""
        content_lower = content.lower()

        # Calendar-related
        calendar_words = ["event", "meeting", "schedule", "calendar", "rsvp", "tomorrow", "monday", "tuesday"]
        if any(w in content_lower for w in calendar_words):
            return "calendar"

        # Task-related
        task_words = ["task", "todo", "implement", "fix", "bug", "feature", "build"]
        if any(w in content_lower for w in task_words):
            return "task"

        # Code-related
        code_words = ["code", "function", "class", "api", "pr", "merge", "commit"]
        if any(w in content_lower for w in code_words):
            return "code"

        # Business-related
        biz_words = ["revenue", "customer", "user", "sales", "pricing", "subscription"]
        if any(w in content_lower for w in biz_words):
            return "business"

        return "general"

    def _analyze_sentiment(self, content: str) -> Dict[str, Any]:
        """
        Enhanced sentiment analysis with emotion, urgency, intensity, and politeness detection.

        Returns:
            Dict with keys:
            - polarity: positive/neutral/negative
            - emotion: excited/frustrated/curious/neutral
            - urgency: high/medium/low
            - intensity: 0.0 to 1.0
            - politeness: formal/casual/terse
        """
        content_lower = content.lower()

        # 1. Emotion detection
        emotion_keywords = {
            "excited": ["great", "awesome", "amazing", "love", "perfect", "excellent",
                       "fantastic", "wonderful", "brilliant", "yay", "hooray"],
            "frustrated": ["bad", "broken", "fail", "error", "problem", "issue", "stuck",
                          "frustrated", "annoying", "terrible", "horrible", "wrong"],
            "curious": ["wondering", "how", "what", "why", "curious", "question",
                       "confused", "unsure", "don't understand", "clarify"],
            "neutral": []  # Default
        }

        emotion_scores = {}
        for emotion, keywords in emotion_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                emotion_scores[emotion] = score

        # Determine primary emotion
        if emotion_scores:
            primary_emotion = max(emotion_scores, key=emotion_scores.get)
        else:
            primary_emotion = "neutral"

        # 2. Sentiment polarity
        positive_words = ["great", "awesome", "thanks", "love", "perfect", "excellent", "good", "happy"]
        negative_words = ["bad", "broken", "fail", "error", "problem", "issue", "hate", "frustrated", "sad"]

        positive_count = sum(1 for w in positive_words if w in content_lower)
        negative_count = sum(1 for w in negative_words if w in content_lower)

        if positive_count > negative_count:
            polarity = "positive"
        elif negative_count > positive_count:
            polarity = "negative"
        else:
            polarity = "neutral"

        # 3. Urgency detection
        high_urgency = ["asap", "urgent", "immediately", "right now", "emergency", "critical"]
        medium_urgency = ["soon", "quickly", "priority", "important", "essential"]

        if any(word in content_lower for word in high_urgency):
            urgency = "high"
        elif any(word in content_lower for word in medium_urgency):
            urgency = "medium"
        else:
            urgency = "low"

        # 4. Politeness level
        formal_phrases = ["would appreciate", "kindly", "request", "thank you for", "please"]
        casual_phrases = ["thanks", "cool", "awesome", "gotcha", "sure thing", "no worries"]

        if any(phrase in content_lower for phrase in formal_phrases):
            politeness = "formal"
        elif any(phrase in content_lower for phrase in casual_phrases):
            politeness = "casual"
        else:
            politeness = "terse"

        # 5. Intensity score (0.0 to 1.0)
        total_emotion_words = sum(emotion_scores.values())
        word_count = len(content.split())

        if word_count > 0:
            emotion_density = min(total_emotion_words / word_count, 1.0)
            intensity = min(emotion_density * 2, 1.0)  # Scale up slightly
        else:
            intensity = 0.0

        return {
            "polarity": polarity,
            "emotion": primary_emotion,
            "urgency": urgency,
            "intensity": round(intensity, 2),
            "politeness": politeness
        }

    def _should_archive(self, phone_number: str) -> bool:
        """Check if profile needs archiving (50+ conversations)."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return False

        conversations = profile.get("conversations", [])
        return len(conversations) >= MAX_CONVERSATIONS_IN_FILE

    def _archive_old_conversations(self, phone_number: str) -> None:
        """Archive older conversations to a separate file."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return

        conversations = profile.get("conversations", [])
        if len(conversations) < MAX_CONVERSATIONS_IN_FILE:
            return

        # Keep last 30 in main file, archive the rest
        to_archive = conversations[:-30]
        to_keep = conversations[-30:]

        if not to_archive:
            return

        # Write archive file
        normalized_id = self.memory._normalize_id(phone_number)
        archive_date = datetime.now().strftime("%Y-%m")
        archive_file = ARCHIVE_DIR / f"{normalized_id}-archive-{archive_date}.json"

        # Load existing archive if any
        existing_archive = []
        if archive_file.exists():
            try:
                existing_archive = json.loads(archive_file.read_text())
            except (json.JSONDecodeError, Exception):
                existing_archive = []

        # Append new archived conversations
        existing_archive.extend(to_archive)

        # Write archive
        archive_file.write_text(json.dumps(existing_archive, indent=2, default=str))
        self._set_file_permissions(archive_file)

        # Update profile with remaining conversations
        profile["conversations"] = to_keep
        self.memory.write_profile(phone_number, profile)

        # Clean up old archives (keep only MAX_ARCHIVE_FILES)
        self._cleanup_old_archives(phone_number)

    def _cleanup_old_archives(self, phone_number: str) -> None:
        """Remove old archive files beyond retention limit."""
        normalized_id = self.memory._normalize_id(phone_number)
        archives = sorted(ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"))

        # Remove oldest archives beyond limit
        while len(archives) > MAX_ARCHIVE_FILES:
            archives[0].unlink()
            archives = archives[1:]

    def log_conversation(
        self,
        phone_number: str,
        direction: str,
        content: str,
        channel: str = "signal",
        message_id: Optional[str] = None,
        related_tasks: Optional[List[str]] = None,
        related_events: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log a conversation with a human.

        Args:
            phone_number: E.164 phone number
            direction: "inbound" or "outbound"
            content: Message content
            channel: Communication channel (signal, email, etc.)
            message_id: Optional message ID for deduplication
            related_tasks: List of related task IDs
            related_events: List of related event names/IDs
            metadata: Additional metadata

        Returns:
            True if logged successfully
        """
        # Check if we need to archive first
        if self._should_archive(phone_number):
            self._archive_old_conversations(phone_number)

        # Build conversation entry
        conversation = {
            "date": datetime.now().isoformat(),
            "channel": channel,
            "direction": direction,
            "content": content[:1000],  # Limit content length
            "topics": self._extract_topics(content),
            "context": self._detect_context(content),
            "action_items": self._extract_action_items(content),
            "sentiment": self._analyze_sentiment(content),
        }

        if message_id:
            conversation["message_id"] = message_id

        if related_tasks:
            conversation["related_tasks"] = related_tasks

        if related_events:
            conversation["related_events"] = related_events

        if metadata:
            conversation["metadata"] = metadata

        # Add to profile
        success = self.memory.add_conversation(phone_number, conversation)

        # Ensure proper file permissions
        file_path = self.memory._get_file_path(phone_number)
        self._set_file_permissions(file_path)

        return success

    def search_conversations(
        self,
        phone_number: str,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search a human's conversations for a query.

        Reads from JSON index for reliable querying.

        Args:
            phone_number: Phone number to search
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching conversations
        """
        conversations = self._load_conversation_index(phone_number)
        if not conversations:
            return []

        query_lower = query.lower()

        results = []
        for conv in conversations:
            # Search in content, topics, action items
            content = conv.get("content", "").lower()

            # Normalize topics to handle both string and dict formats
            topics_list = self._normalize_topics(conv.get("topics", []))
            topics = " ".join(topics_list).lower()

            action_items = " ".join(conv.get("action_items", [])).lower()

            if query_lower in content or query_lower in topics or query_lower in action_items:
                results.append(conv)

                if len(results) >= limit:
                    break

        return results

    def search_all_conversations(
        self,
        query: str,
        limit: int = 50
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across all conversations (admin function).

        Args:
            query: Search query
            limit: Maximum results per person

        Returns:
            Dict mapping phone numbers to matching conversations
        """
        results = {}

        for phone_number in self.memory.list_profiles():
            matches = self.search_conversations(phone_number, query, limit)
            if matches:
                results[phone_number] = matches

        return results

    def get_conversation_stats(self, phone_number: str) -> Dict[str, Any]:
        """Get statistics about a human's conversations."""
        conversations = self._load_conversation_index(phone_number)

        stats = {
            "total": len(conversations),
            "channels": {},
            "contexts": {},
            "sentiments": {"positive": 0, "negative": 0, "neutral": 0},
            "first_conversation": None,
            "last_conversation": None,
        }

        for conv in conversations:
            # Count by channel
            channel = conv.get("channel", "unknown")
            stats["channels"][channel] = stats["channels"].get(channel, 0) + 1

            # Count by context
            context = conv.get("context", "unknown")
            stats["contexts"][context] = stats["contexts"].get(context, 0) + 1

            # Count by sentiment (handle both string and dict formats)
            sentiment_data = conv.get("sentiment", "neutral")
            if isinstance(sentiment_data, dict):
                sentiment = sentiment_data.get("polarity", "neutral")
            else:
                sentiment = sentiment_data if sentiment_data else "neutral"
            stats["sentiments"][sentiment] = stats["sentiments"].get(sentiment, 0) + 1

        if conversations:
            stats["first_conversation"] = conversations[0].get("date")
            stats["last_conversation"] = conversations[-1].get("date")

        return stats

    def export_conversations(self, phone_number: str) -> Optional[str]:
        """Export all conversations for a user (privacy request)."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return None

        conversations = profile.get("conversations", [])

        # Also load archived conversations
        normalized_id = self.memory._normalize_id(phone_number)
        archives = sorted(ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"))

        all_conversations = []
        for archive_file in archives:
            try:
                archived = json.loads(archive_file.read_text())
                all_conversations.extend(archived)
            except Exception:
                pass

        all_conversations.extend(conversations)

        return json.dumps(all_conversations, indent=2, default=str)

    def delete_all_conversations(self, phone_number: str) -> bool:
        """Delete all conversations for a user (privacy request)."""
        # Delete main profile conversations
        profile = self.memory.read_profile(phone_number)
        if profile:
            profile["conversations"] = []
            self.memory.write_profile(phone_number, profile)

        # Delete all archive files
        normalized_id = self.memory._normalize_id(phone_number)
        for archive_file in ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"):
            archive_file.unlink()

        return True

    def get_event_links(self, phone_number: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all event-to-conversation links for a user.

        Args:
            phone_number: User's phone number

        Returns:
            Dict mapping event names to lists of conversation references
        """
        links_file = CONVERSATION_INDEX_DIR / f"{self.memory._normalize_id(phone_number)}_event_links.json"
        if links_file.exists():
            try:
                return json.loads(links_file.read_text())
            except:
                return {}
        return {}

    def get_task_links(self, phone_number: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all task-to-conversation links for a user.

        Args:
            phone_number: User's phone number

        Returns:
            Dict mapping task IDs to lists of conversation references
        """
        links_file = CONVERSATION_INDEX_DIR / f"{self.memory._normalize_id(phone_number)}_task_links.json"
        if links_file.exists():
            try:
                return json.loads(links_file.read_text())
            except:
                return {}
        return {}

    def log_human_conversation(
        self,
        phone_number: str,
        direction: str,
        content: str,
        channel: str = "signal",
        context: Optional[str] = None,
        topics: Optional[List[str]] = None,
        action_items: Optional[List[str]] = None,
        sentiment: Optional[str] = None,
        related_events: Optional[List[str]] = None,
        related_tasks: Optional[List[str]] = None,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Comprehensive conversation logging with full context extraction.

        This is the primary method for logging human conversations with
        automatic extraction of topics, action items, sentiment, and
        optional linking to related events/tasks.

        Args:
            phone_number: E.164 phone number
            direction: "inbound" or "outbound"
            content: Message content
            channel: Communication channel (signal, email, etc.)
            context: Override auto-detected context
            topics: Override auto-extracted topics
            action_items: Override auto-extracted action items
            sentiment: Override auto-detected sentiment
            related_events: List of related calendar event names/IDs
            related_tasks: List of related task IDs
            message_id: Optional message ID for deduplication
            metadata: Additional metadata dict

        Returns:
            True if logged successfully
        """
        # Check if we need to archive first
        if self._should_archive(phone_number):
            self._archive_old_conversations(phone_number)

        # Use provided values or auto-extract
        detected_context = context or self._detect_context(content)
        if topics is not None:
            detected_topics = topics
        else:
            # Load conversation history for frequency weighting
            conversation_history = self._load_conversation_index(phone_number)
            detected_topics = self._extract_topics(content, conversation_history)
        detected_action_items = action_items if action_items is not None else self._extract_action_items(content)
        detected_sentiment = sentiment or self._analyze_sentiment(content)

        # Extract event and task mentions if not provided
        if related_events is None:
            related_events = self._extract_event_mentions(content)
        if related_tasks is None:
            related_tasks = self._extract_task_ids(content)

        # Build comprehensive conversation entry
        conversation = {
            "date": datetime.now().isoformat(),
            "channel": channel,
            "direction": direction,
            "content": content[:2000],  # Increased limit for full context
            "context": detected_context,
            "topics": detected_topics,
            "action_items": detected_action_items,
            "sentiment": detected_sentiment,
        }

        if message_id:
            conversation["message_id"] = message_id

        if related_events:
            conversation["related_events"] = related_events

        if related_tasks:
            conversation["related_tasks"] = related_tasks

        if metadata:
            conversation["metadata"] = metadata

        # Add to profile (Markdown for human readability)
        self.memory.add_conversation(phone_number, conversation)

        # Save to JSON index for reliable querying
        self._save_to_index(phone_number, conversation)

        # Create bidirectional links
        conversation_date = conversation["date"]
        self._link_conversation_to_events(phone_number, conversation_date, related_events)
        self._link_conversation_to_tasks(phone_number, conversation_date, related_tasks)

        # Ensure proper file permissions
        file_path = self.memory._get_file_path(phone_number)
        self._set_file_permissions(file_path)

        return True

    def _save_to_index(self, phone_number: str, conversation: Dict[str, Any]) -> None:
        """Save conversation to JSON index for reliable querying."""
        index_file = self._get_index_file(phone_number)
        index_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing index
        conversations = self._load_conversation_index(phone_number)

        # Append new conversation
        conversations.append(conversation)

        # Keep only last 100 in index (archives handle overflow)
        if len(conversations) > 100:
            self._archive_old_index_conversations(phone_number, conversations[:-50])
            conversations = conversations[-50:]

        # Save index
        index_file.write_text(json.dumps(conversations, indent=2, default=str))
        self._set_file_permissions(index_file)

    def _archive_old_index_conversations(self, phone_number: str, old_conversations: List[Dict[str, Any]]) -> None:
        """Archive old conversations from index to JSON archive."""
        if not old_conversations:
            return

        normalized_id = self.memory._normalize_id(phone_number)
        archive_date = datetime.now().strftime("%Y-%m")
        archive_file = ARCHIVE_DIR / f"{normalized_id}-archive-{archive_date}.json"

        # Load existing archive if any
        existing = []
        if archive_file.exists():
            try:
                existing = json.loads(archive_file.read_text())
            except Exception:
                existing = []

        # Append and save
        existing.extend(old_conversations)
        archive_file.write_text(json.dumps(existing, indent=2, default=str))
        self._set_file_permissions(archive_file)

    def get_recent_conversations(
        self,
        phone_number: str,
        limit: int = 10,
        context_filter: Optional[str] = None,
        sentiment_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent conversations with optional filtering.

        Reads from JSON index for reliable querying.

        Args:
            phone_number: Phone number
            limit: Maximum conversations to return
            context_filter: Filter by context type
            sentiment_filter: Filter by sentiment

        Returns:
            List of conversation dicts
        """
        conversations = self._load_conversation_index(phone_number)

        # Apply filters
        if context_filter:
            conversations = [c for c in conversations if c.get("context") == context_filter]

        if sentiment_filter:
            conversations = [c for c in conversations if c.get("sentiment") == sentiment_filter]

        # Return most recent first, limited
        return list(reversed(conversations[-limit:]))

    def get_action_items(self, phone_number: str, pending_only: bool = True) -> List[Dict[str, Any]]:
        """
        Extract all action items from conversations.

        Reads from JSON index for reliable querying.

        Args:
            phone_number: Phone number
            pending_only: Only return items not marked as completed

        Returns:
            List of action item dicts with conversation context
        """
        conversations = self._load_conversation_index(phone_number)
        all_action_items = []

        for conv in conversations:
            items = conv.get("action_items", [])
            for item in items:
                action_item = {
                    "item": item,
                    "date": conv.get("date"),
                    "context": conv.get("context"),
                    "completed": item in conv.get("completed_items", [])
                }
                if not pending_only or not action_item["completed"]:
                    all_action_items.append(action_item)

        return all_action_items

    def link_to_event(self, phone_number: str, conversation_date: str, event_name: str) -> bool:
        """
        Link a conversation to a calendar event.

        Args:
            phone_number: Phone number
            conversation_date: ISO date string of conversation
            event_name: Name of the event to link

        Returns:
            True if linked successfully
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return False

        conversations = profile.get("conversations", [])
        for conv in conversations:
            if conv.get("date") == conversation_date:
                if "related_events" not in conv:
                    conv["related_events"] = []
                if event_name not in conv["related_events"]:
                    conv["related_events"].append(event_name)
                self.memory.write_profile(phone_number, profile)
                return True

        return False

    def link_to_task(self, phone_number: str, conversation_date: str, task_id: str) -> bool:
        """
        Link a conversation to a task.

        Args:
            phone_number: Phone number
            conversation_date: ISO date string of conversation
            task_id: Task ID to link

        Returns:
            True if linked successfully
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return False

        conversations = profile.get("conversations", [])
        for conv in conversations:
            if conv.get("date") == conversation_date:
                if "related_tasks" not in conv:
                    conv["related_tasks"] = []
                if task_id not in conv["related_tasks"]:
                    conv["related_tasks"].append(task_id)
                self.memory.write_profile(phone_number, profile)
                return True

        return False

    def audit_permissions(self) -> Dict[str, Any]:
        """
        Audit all file and directory permissions in the conversation storage system.

        Returns:
            Dict with audit results including status of directories and files
        """
        results = {
            "directories": {},
            "files": [],
            "errors": [],
            "timestamp": datetime.now().isoformat()
        }

        # Audit directories
        directories = {
            "memory_dir": self.memory.memory_dir,
            "archive_dir": ARCHIVE_DIR,
            "index_dir": CONVERSATION_INDEX_DIR
        }

        for name, path in directories.items():
            if path.exists():
                ok = self._verify_and_set_permissions(path, is_dir=True)
                results["directories"][name] = {
                    "path": str(path),
                    "exists": True,
                    "permissions_ok": ok,
                    "mode": oct(path.stat().st_mode)[-3:]
                }
                if not ok:
                    results["errors"].append(f"Directory {name} has incorrect permissions")
            else:
                results["directories"][name] = {
                    "path": str(path),
                    "exists": False,
                    "permissions_ok": False
                }

        # Audit profile files (Markdown files in memory_dir)
        for profile_file in self.memory.memory_dir.glob("*.md"):
            ok = self._verify_and_set_permissions(profile_file, is_dir=False)
            results["files"].append({
                "type": "profile",
                "file": profile_file.name,
                "path": str(profile_file),
                "permissions_ok": ok,
                "mode": oct(profile_file.stat().st_mode)[-3:]
            })
            if not ok:
                results["errors"].append(f"Profile file {profile_file.name} has incorrect permissions")

        # Audit index files (JSON files in index_dir)
        if CONVERSATION_INDEX_DIR.exists():
            for index_file in CONVERSATION_INDEX_DIR.glob("*.json"):
                ok = self._verify_and_set_permissions(index_file, is_dir=False)
                results["files"].append({
                    "type": "index",
                    "file": index_file.name,
                    "path": str(index_file),
                    "permissions_ok": ok,
                    "mode": oct(index_file.stat().st_mode)[-3:]
                })
                if not ok:
                    results["errors"].append(f"Index file {index_file.name} has incorrect permissions")

        # Audit archive files
        if ARCHIVE_DIR.exists():
            for archive_file in ARCHIVE_DIR.glob("*.json"):
                ok = self._verify_and_set_permissions(archive_file, is_dir=False)
                results["files"].append({
                    "type": "archive",
                    "file": archive_file.name,
                    "path": str(archive_file),
                    "permissions_ok": ok,
                    "mode": oct(archive_file.stat().st_mode)[-3:]
                })
                if not ok:
                    results["errors"].append(f"Archive file {archive_file.name} has incorrect permissions")

        # Summary
        total_files = len(results["files"])
        ok_files = sum(1 for f in results["files"] if f["permissions_ok"])
        results["summary"] = {
            "total_files": total_files,
            "files_with_correct_permissions": ok_files,
            "files_with_incorrect_permissions": total_files - ok_files,
            "total_errors": len(results["errors"])
        }

        return results


# Singleton instance for convenience
_logger_instance: Optional[ConversationLogger] = None


def get_logger() -> ConversationLogger:
    """Get or create the singleton logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ConversationLogger()
    return _logger_instance


def log_conversation(
    phone_number: str,
    direction: str,
    content: str,
    channel: str = "signal",
    **kwargs
) -> bool:
    """
    Convenience function to log a conversation.

    Args:
        phone_number: E.164 phone number
        direction: "inbound" or "outbound"
        content: Message content
        channel: Communication channel
        **kwargs: Additional arguments passed to ConversationLogger.log_conversation

    Returns:
        True if logged successfully
    """
    return get_logger().log_conversation(phone_number, direction, content, channel, **kwargs)


def log_inbound(phone_number: str, content: str, channel: str = "signal", **kwargs) -> bool:
    """Log an inbound message."""
    return log_conversation(phone_number, "inbound", content, channel, **kwargs)


def log_outbound(phone_number: str, content: str, channel: str = "signal", **kwargs) -> bool:
    """Log an outbound message."""
    return log_conversation(phone_number, "outbound", content, channel, **kwargs)


def search_conversations(phone_number: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search a human's conversations."""
    return get_logger().search_conversations(phone_number, query, limit)


def search_all_conversations(query: str, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Search across all conversations (admin)."""
    return get_logger().search_all_conversations(query, limit)


def get_conversation_stats(phone_number: str) -> Dict[str, Any]:
    """Get conversation statistics."""
    return get_logger().get_conversation_stats(phone_number)


def export_conversations(phone_number: str) -> Optional[str]:
    """Export all conversations (privacy request)."""
    return get_logger().export_conversations(phone_number)


def delete_all_conversations(phone_number: str) -> bool:
    """Delete all conversations (privacy request)."""
    return get_logger().delete_all_conversations(phone_number)


def audit_permissions() -> Dict[str, Any]:
    """
    Audit all file and directory permissions in the conversation storage system.

    Returns:
        Dict with audit results including status of directories and files
    """
    return get_logger().audit_permissions()


def log_human_conversation(
    phone_number: str,
    direction: str,
    content: str,
    channel: str = "signal",
    context: Optional[str] = None,
    topics: Optional[List[str]] = None,
    action_items: Optional[List[str]] = None,
    sentiment: Optional[str] = None,
    related_events: Optional[List[str]] = None,
    related_tasks: Optional[List[str]] = None,
    message_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Comprehensive conversation logging with full context extraction.

    This is the primary function for logging human conversations with
    automatic extraction of topics, action items, sentiment, and
    optional linking to related events/tasks.

    Args:
        phone_number: E.164 phone number
        direction: "inbound" or "outbound"
        content: Message content
        channel: Communication channel (signal, email, etc.)
        context: Override auto-detected context (calendar, task, code, business, general)
        topics: Override auto-extracted topics
        action_items: Override auto-extracted action items
        sentiment: Override auto-detected sentiment (positive, negative, neutral)
        related_events: List of related calendar event names/IDs
        related_tasks: List of related task IDs
        message_id: Optional message ID for deduplication
        metadata: Additional metadata dict

    Returns:
        True if logged successfully

    Example:
        log_human_conversation(
            phone_number="+19194133445",
            direction="inbound",
            content="Can you schedule a meeting for Friday?",
            channel="signal",
            related_events=["Team Standup"],
            related_tasks=["task-abc123"]
        )
    """
    return get_logger().log_human_conversation(
        phone_number=phone_number,
        direction=direction,
        content=content,
        channel=channel,
        context=context,
        topics=topics,
        action_items=action_items,
        sentiment=sentiment,
        related_events=related_events,
        related_tasks=related_tasks,
        message_id=message_id,
        metadata=metadata
    )


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Conversation Logger CLI")
    parser.add_argument("command", choices=["log", "search", "stats", "export", "list"])
    parser.add_argument("--phone", "-p", help="Phone number (E.164)")
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--content", "-c", help="Message content")
    parser.add_argument("--direction", "-d", choices=["inbound", "outbound"], default="inbound")

    args = parser.parse_args()

    logger = ConversationLogger()

    if args.command == "list":
        profiles = logger.memory.list_profiles()
        print("Profiles with conversations:")
        for p in profiles:
            stats = logger.get_conversation_stats(p)
            print(f"  {p}: {stats['total']} conversations")
        sys.exit(0)

    if not args.phone:
        print("Error: --phone is required for this command")
        sys.exit(1)

    if args.command == "log":
        if not args.content:
            print("Error: --content is required for logging")
            sys.exit(1)
        logger.log_conversation(args.phone, args.direction, args.content)
        print(f"Logged {args.direction} message for {args.phone}")

    elif args.command == "search":
        if not args.query:
            print("Error: --query is required for search")
            sys.exit(1)
        results = logger.search_conversations(args.phone, args.query)
        print(f"Found {len(results)} matching conversations:")
        for r in results:
            print(f"  [{r.get('date', 'unknown')}] {r.get('content', '')[:100]}...")

    elif args.command == "stats":
        stats = logger.get_conversation_stats(args.phone)
        print(f"Conversation stats for {args.phone}:")
        print(json.dumps(stats, indent=2))

    elif args.command == "export":
        export_data = logger.export_conversations(args.phone)
        if export_data:
            print(export_data)
        else:
            print(f"No conversations found for {args.phone}")
