#!/usr/bin/env python3
"""
Conversation Search - Dedicated search utility for human conversations.

Provides fast, indexed search across all conversation logs with support for:
- Full-text search
- Context/sentiment filtering
- Date range queries
- Action item extraction
- Related event/task queries

Usage:
    python3 conversation_search.py --phone "+19194133445" --query "meeting"
    python3 conversation_search.py --phone "+19194133445" --action-items
    python3 conversation_search.py --phone "+19194133445" --context calendar
    python3 conversation_search.py --admin --query "deploy" --all
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from human_profile_memory import HumanProfileMemory
from conversation_logger import ConversationLogger

# Paths
MEMORY_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans"
ARCHIVE_DIR = MEMORY_DIR / "archive"


class ConversationSearch:
    """Optimized search engine for conversation logs with indexing."""

    def __init__(self):
        self.memory = HumanProfileMemory("main")
        self.logger = ConversationLogger()
        self._build_indices()

    def _build_indices(self):
        """Build search indices for fast queries."""
        self.topic_index = {}  # topic -> list of (phone, timestamp)
        self.date_index = {}   # date -> list of (phone, conversation)
        self.content_index = {}  # keyword -> list of (phone, timestamp)
        self.context_index = {}  # context -> list of (phone, timestamp)
        self.sentiment_index = {}  # sentiment -> list of (phone, timestamp)

        # Rebuild from JSON indices
        for phone in self.memory.list_profiles():
            conversations = self.logger._load_conversation_index(phone)
            for conv in conversations:
                self._index_conversation(phone, conv)

    def _index_conversation(self, phone: str, conv: Dict):
        """Index a single conversation for fast retrieval."""
        timestamp = conv.get("date", "")

        # Index by topics
        for topic in conv.get("topics", []):
            topic_name = topic if isinstance(topic, str) else str(topic)
            if topic_name not in self.topic_index:
                self.topic_index[topic_name] = []
            self.topic_index[topic_name].append((phone, timestamp))

        # Index by date (for date range filtering)
        date_key = timestamp[:10] if timestamp else ""  # YYYY-MM-DD
        if date_key not in self.date_index:
            self.date_index[date_key] = []
        self.date_index[date_key].append((phone, conv))

        # Index by content keywords (full-text search)
        content = conv.get("content", "").lower()
        words = set(self._extract_words(content))
        for word in words:
            if len(word) > 3:  # Only meaningful words
                if word not in self.content_index:
                    self.content_index[word] = []
                self.content_index[word].append((phone, timestamp))

        # Index by context
        context = conv.get("context", "")
        if context:
            if context not in self.context_index:
                self.context_index[context] = []
            self.context_index[context].append((phone, timestamp))

        # Index by sentiment
        sentiment = conv.get("sentiment", "")
        if sentiment:
            sentiment_val = sentiment if isinstance(sentiment, str) else str(sentiment)
            if sentiment_val not in self.sentiment_index:
                self.sentiment_index[sentiment_val] = []
            self.sentiment_index[sentiment_val].append((phone, timestamp))

    def _extract_words(self, text: str) -> List[str]:
        """Extract meaningful words from text for indexing."""
        # Remove punctuation and split
        words = re.findall(r'\b\w+\b', text.lower())
        # Filter out common stop words
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been', 'that', 'this', 'with', 'they', 'from', 'what', 'which', 'their', 'there', 'would', 'about'}
        return [w for w in words if w not in stop_words and len(w) > 2]

    def search_user(
        self,
        phone_number: str,
        query: str,
        context_filter: Optional[str] = None,
        sentiment_filter: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search a single user's conversations with optimized indexing.

        Args:
            phone_number: Phone number to search
            query: Search query string
            context_filter: Optional context filter (calendar, task, code, business)
            sentiment_filter: Optional sentiment filter (positive, negative, neutral)
            date_from: Optional start date
            date_to: Optional end date
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            List of matching conversations with relevance scores
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return []

        # Get candidates using indices for fast filtering
        candidates = self._get_candidates(
            phone_number,
            context_filter,
            sentiment_filter,
            date_from,
            date_to
        )

        # Full-text search on candidates
        query_lower = query.lower()
        query_terms = set(self._extract_words(query_lower))

        results = []
        for conv in candidates:
            # Calculate relevance score
            content = conv.get("content", "").lower()

            # Handle topics - they might be strings or dicts
            topics_list = conv.get("topics", [])
            topics_str = " ".join([
                t if isinstance(t, str) else str(t)
                for t in topics_list
            ]).lower()

            # Handle action items - they might be strings or dicts
            action_items_list = conv.get("action_items", [])
            action_items_str = " ".join([
                a if isinstance(a, str) else str(a)
                for a in action_items_list
            ]).lower()

            # Score based on term matches
            score = 0
            matched_terms = 0
            for term in query_terms:
                if term in content:
                    score += 3  # Content match is weighted higher
                    matched_terms += 1
                if term in topics_str:
                    score += 2  # Topic match
                    matched_terms += 1
                if term in action_items_str:
                    score += 1  # Action item match
                    matched_terms += 1

            if score > 0:
                results.append({
                    "conversation": conv,
                    "relevance_score": score,
                    "matched_terms": matched_terms,
                    "phone_number": phone_number
                })

        # Sort by relevance score, then by date
        results.sort(key=lambda x: (-x["relevance_score"], x["conversation"].get("date", "")), reverse=False)

        # Apply pagination
        return results[offset:offset+limit]

    def _get_candidates(
        self,
        phone_number: str,
        context_filter: Optional[str] = None,
        sentiment_filter: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get candidate conversations using indices for fast filtering.
        """
        candidates = []

        # Start with user's conversations
        user_conversations = self.logger._load_conversation_index(phone_number)

        if not context_filter and not sentiment_filter and not date_from and not date_to:
            return user_conversations

        # Use context index for fast filtering
        if context_filter:
            context_matches = set()
            if context_filter in self.context_index:
                for p, timestamp in self.context_index[context_filter]:
                    if p == phone_number:
                        context_matches.add(timestamp)
            candidates = [c for c in user_conversations if c.get("date") in context_matches]
        else:
            candidates = user_conversations

        # Use sentiment index for fast filtering
        if sentiment_filter:
            sentiment_matches = set()
            if sentiment_filter in self.sentiment_index:
                for p, timestamp in self.sentiment_index[sentiment_filter]:
                    if p == phone_number:
                        sentiment_matches.add(timestamp)
            candidates = [c for c in candidates if c.get("date") in sentiment_matches]

        # Use date index for fast date range filtering
        if date_from or date_to:
            candidates = [
                c for c in candidates
                if self._in_date_range(c.get("date", ""), date_from, date_to)
            ]

        return candidates

    def _in_date_range(
        self,
        timestamp: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime]
    ) -> bool:
        """Check if timestamp is in date range."""
        if not timestamp:
            return False

        try:
            conv_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            if date_from and conv_date < date_from:
                return False

            if date_to and conv_date > date_to:
                return False

            return True
        except ValueError:
            return False

    def search_all(
        self,
        query: str,
        context_filter: Optional[str] = None,
        sentiment_filter: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit_per_user: int = 20,
        total_limit: int = 100,
        topics: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search across all users' conversations (admin function).

        Args:
            query: Search query string
            context_filter: Optional context filter
            sentiment_filter: Optional sentiment filter
            date_from: Optional start date
            date_to: Optional end date
            limit_per_user: Max results per user
            total_limit: Total max results
            topics: Optional topic filters

        Returns:
            List of matching conversations with user context
        """
        all_results = []

        # Use topic index to narrow down phone numbers if topics specified
        phone_numbers = self.memory.list_profiles()
        if topics:
            topic_phones = set()
            for topic in topics:
                if topic in self.topic_index:
                    for p, _ in self.topic_index[topic]:
                        topic_phones.add(p)
            phone_numbers = list(topic_phones)

        for phone_number in phone_numbers:
            user_results = self.search_user(
                phone_number,
                query,
                context_filter,
                sentiment_filter,
                date_from,
                date_to,
                limit_per_user
            )
            all_results.extend(user_results)

        # Sort all results by relevance
        all_results.sort(key=lambda x: -x["relevance_score"])
        return all_results[:total_limit]

    def search_by_topics(
        self,
        phone_number: str,
        topics: List[str],
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fast topic-based search using topic index.

        Args:
            phone_number: Phone number to search
            topics: List of topics to filter by
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            List of matching conversations
        """
        # Use topic index for fast lookup
        topic_matches = set()
        for topic in topics:
            if topic in self.topic_index:
                for p, timestamp in self.topic_index[topic]:
                    if p == phone_number:
                        topic_matches.add(timestamp)

        # Load conversations and filter by topic matches
        user_conversations = self.logger._load_conversation_index(phone_number)
        results = [
            conv for conv in user_conversations
            if conv.get("date") in topic_matches
        ]

        # Sort by date (newest first)
        results.sort(key=lambda x: x.get("date", ""), reverse=True)

        # Apply pagination
        return results[offset:offset+limit]

    def get_action_items(
        self,
        phone_number: str,
        pending_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all action items from a user's conversations.

        Args:
            phone_number: Phone number
            pending_only: Only return pending items

        Returns:
            List of action items with conversation context
        """
        return self.logger.get_action_items(phone_number, pending_only)

    def get_by_context(
        self,
        phone_number: str,
        context: str,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations with a specific context.

        Args:
            phone_number: Phone number
            context: Context type (calendar, task, code, business, general)
            limit: Maximum results

        Returns:
            List of conversations
        """
        return self.logger.get_recent_conversations(
            phone_number,
            limit=limit,
            context_filter=context
        )

    def get_by_sentiment(
        self,
        phone_number: str,
        sentiment: str,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations with a specific sentiment.

        Args:
            phone_number: Phone number
            sentiment: Sentiment type (positive, negative, neutral)
            limit: Maximum results

        Returns:
            List of conversations
        """
        return self.logger.get_recent_conversations(
            phone_number,
            limit=limit,
            sentiment_filter=sentiment
        )

    def get_by_date_range(
        self,
        phone_number: str,
        date_from: datetime,
        date_to: datetime,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get conversations within a date range.

        Args:
            phone_number: Phone number
            date_from: Start date
            date_to: End date
            limit: Maximum results

        Returns:
            List of conversations
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return []

        conversations = profile.get("conversations", [])
        results = []

        for conv in conversations:
            conv_date_str = conv.get("date", "")
            if conv_date_str:
                try:
                    conv_date = datetime.fromisoformat(conv_date_str.replace("Z", "+00:00"))
                    if date_from <= conv_date <= date_to:
                        results.append(conv)
                except ValueError:
                    pass

        return results[:limit]

    def get_related_to_event(
        self,
        event_name: str,
        phone_number: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find conversations related to a specific event.

        Args:
            event_name: Event name to search for
            phone_number: Optional specific user (searches all if None)

        Returns:
            List of related conversations
        """
        results = []

        phone_numbers = [phone_number] if phone_number else self.memory.list_profiles()

        for pn in phone_numbers:
            profile = self.memory.read_profile(pn)
            if not profile:
                continue

            for conv in profile.get("conversations", []):
                related_events = conv.get("related_events", [])
                if event_name in related_events:
                    results.append({
                        "phone_number": pn,
                        "conversation": conv
                    })
                # Also search in content
                elif event_name.lower() in conv.get("content", "").lower():
                    results.append({
                        "phone_number": pn,
                        "conversation": conv,
                        "matched_in_content": True
                    })

        return results

    def get_related_to_task(
        self,
        task_id: str,
        phone_number: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find conversations related to a specific task.

        Args:
            task_id: Task ID to search for
            phone_number: Optional specific user

        Returns:
            List of related conversations
        """
        results = []

        phone_numbers = [phone_number] if phone_number else self.memory.list_profiles()

        for pn in phone_numbers:
            profile = self.memory.read_profile(pn)
            if not profile:
                continue

            for conv in profile.get("conversations", []):
                related_tasks = conv.get("related_tasks", [])
                if task_id in related_tasks:
                    results.append({
                        "phone_number": pn,
                        "conversation": conv
                    })

        return results

    def get_statistics(self, phone_number: str) -> Dict[str, Any]:
        """
        Get comprehensive statistics about a user's conversations.

        Args:
            phone_number: Phone number

        Returns:
            Statistics dict
        """
        return self.logger.get_conversation_stats(phone_number)


def format_search_result(result: Dict[str, Any], show_phone: bool = False) -> str:
    """Format a search result for display."""
    conv = result["conversation"]
    lines = []

    header = f"[{conv.get('date', 'unknown')[:10]}]"
    if show_phone:
        header += f" {result.get('phone_number', '')}"
    if "relevance_score" in result:
        header += f" (score: {result['relevance_score']})"
    lines.append(header)

    content = conv.get("content", "")
    if len(content) > 150:
        content = content[:150] + "..."
    lines.append(f"  {content}")

    if conv.get("topics"):
        lines.append(f"  Topics: {', '.join(conv['topics'])}")

    if conv.get("action_items"):
        lines.append(f"  Actions: {', '.join(conv['action_items'][:3])}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Conversation Search Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search a user's conversations
  python3 conversation_search.py --phone "+19194133445" --query "meeting"

  # Get all action items for a user
  python3 conversation_search.py --phone "+19194133445" --action-items

  # Search all users (admin)
  python3 conversation_search.py --admin --query "deploy" --all

  # Filter by context
  python3 conversation_search.py --phone "+19194133445" --context calendar

  # Search by date range
  python3 conversation_search.py --phone "+19194133445" --from 2026-03-01 --to 2026-03-08

  # Find conversations about a specific event
  python3 conversation_search.py --event "Team Standup"
        """
    )

    # User specification
    parser.add_argument("--phone", "-p", help="Phone number (E.164 format)")
    parser.add_argument("--admin", action="store_true", help="Admin mode (search all users)")
    parser.add_argument("--all", action="store_true", help="Search all users")

    # Search options
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--context", "-c", help="Filter by context (calendar, task, code, business, general)")
    parser.add_argument("--sentiment", "-s", help="Filter by sentiment (positive, negative, neutral)")

    # Date range
    parser.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")

    # Special queries
    parser.add_argument("--action-items", action="store_true", help="List all action items")
    parser.add_argument("--event", help="Find conversations related to an event")
    parser.add_argument("--task", help="Find conversations related to a task")
    parser.add_argument("--stats", action="store_true", help="Show conversation statistics")

    # Output options
    parser.add_argument("--limit", "-l", type=int, default=20, help="Maximum results")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--raw", action="store_true", help="Show raw conversation data")

    args = parser.parse_args()

    search = ConversationSearch()

    # Parse date filters
    date_from = None
    date_to = None
    if args.date_from:
        date_from = datetime.fromisoformat(args.date_from)
    if args.date_to:
        date_to = datetime.fromisoformat(args.date_to) + timedelta(days=1)

    # Determine search scope
    if args.admin or args.all:
        if not args.query and not args.event and not args.task:
            print("Error: --admin requires --query, --event, or --task")
            sys.exit(1)

    if not args.phone and not (args.admin or args.all):
        print("Error: --phone or --admin is required")
        sys.exit(1)

    # Execute query
    results = []

    if args.stats:
        # Show statistics
        stats = search.get_statistics(args.phone)
        if args.json:
            print(json.dumps(stats, indent=2, default=str))
        else:
            print(f"Conversation Statistics for {args.phone}")
            print("=" * 40)
            print(f"Total conversations: {stats.get('total', 0)}")
            print(f"First conversation: {stats.get('first_conversation', 'N/A')}")
            print(f"Last conversation: {stats.get('last_conversation', 'N/A')}")
            print(f"\nBy Channel:")
            for channel, count in stats.get("channels", {}).items():
                print(f"  {channel}: {count}")
            print(f"\nBy Context:")
            for context, count in stats.get("contexts", {}).items():
                print(f"  {context}: {count}")
            print(f"\nBy Sentiment:")
            for sentiment, count in stats.get("sentiments", {}).items():
                print(f"  {sentiment}: {count}")
        sys.exit(0)

    if args.action_items:
        # Get action items
        items = search.get_action_items(args.phone)
        if args.json:
            print(json.dumps(items, indent=2, default=str))
        else:
            print(f"Action Items for {args.phone}")
            print("=" * 40)
            for item in items:
                status = "✓" if item.get("completed") else "○"
                print(f"{status} [{item.get('date', 'unknown')[:10]}] {item['item']}")
        sys.exit(0)

    if args.event:
        # Search by event
        results = search.get_related_to_event(args.event, args.phone if args.phone else None)

    elif args.task:
        # Search by task
        results = search.get_related_to_task(args.task, args.phone if args.phone else None)

    elif args.query:
        # Text search
        if args.admin or args.all:
            results = search.search_all(
                args.query,
                context_filter=args.context,
                sentiment_filter=args.sentiment,
                date_from=date_from,
                date_to=date_to,
                total_limit=args.limit
            )
        else:
            results = search.search_user(
                args.phone,
                args.query,
                context_filter=args.context,
                sentiment_filter=args.sentiment,
                date_from=date_from,
                date_to=date_to,
                limit=args.limit
            )

    elif args.context:
        # Filter by context
        results = [
            {"conversation": c, "phone_number": args.phone}
            for c in search.get_by_context(args.phone, args.context, args.limit)
        ]

    elif args.sentiment:
        # Filter by sentiment
        results = [
            {"conversation": c, "phone_number": args.phone}
            for c in search.get_by_sentiment(args.phone, args.sentiment, args.limit)
        ]

    else:
        print("Error: Specify --query, --context, --sentiment, --event, --task, or --stats")
        sys.exit(1)

    # Output results
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"Found {len(results)} result(s)")
        print("=" * 40)
        for i, result in enumerate(results):
            if i > 0:
                print("-" * 40)
            if args.raw:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(format_search_result(result, show_phone=(args.admin or args.all)))


if __name__ == "__main__":
    main()
