#!/usr/bin/env python3
"""
X/Twitter Post Queue - Unified SQLite-based queue for X posts.

Consolidates PostQueue (from x_poster.py) and ContentQueue (from twitter_maintenance.py)
into a single canonical module with draft, approval, and scheduling support.

Usage:
    from x_queue import XPostQueue

    queue = XPostQueue()

    # Add a draft post
    post_id = queue.add_post(
        text="Check out this new feature!",
        category="feature",
        hashtags=["buildinpublic", "ai"]
    )

    # Approve and post
    queue.approve_post(post_id)
    queue.mark_posted(post_id, success=True, tweet_id="1234567890")
"""

import os
import sys
import json
import time
import hashlib
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


# Default database path
DEFAULT_DB_PATH = Path.home() / ".openclaw" / "data" / "x_posts.db"

# Setup logging
logger = logging.getLogger(__name__)


class PostStatus(Enum):
    """Status of a queued post."""
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PostCategory(Enum):
    """Categories for X posts."""
    STATUS = "status"
    MILESTONE = "milestone"
    FEATURE = "feature"
    WEEKLY = "weekly"
    BUILD_PUBLIC = "build_public"
    TECHNICAL = "technical"
    ACHIEVEMENT = "achievement"
    COMMUNITY = "community"
    INSIGHT = "insight"
    SUMMARY = "summary"


@dataclass
class QueuedPost:
    """Represents a post in the queue."""
    id: str
    text: str
    category: str
    status: PostStatus
    created_at: str
    scheduled_for: Optional[str] = None
    posted_at: Optional[str] = None
    thread_items: Optional[List[str]] = None
    hashtags: List[str] = field(default_factory=list)
    media_path: Optional[str] = None
    error_message: Optional[str] = None
    tweet_id: Optional[str] = None
    engagement_expected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['status'] = self.status.value
        data['thread_items'] = json.dumps(self.thread_items) if self.thread_items else None
        data['hashtags'] = json.dumps(self.hashtags) if self.hashtags else None
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> 'QueuedPost':
        """Create from database row."""
        return cls(
            id=row['id'],
            text=row['text'],
            category=row['category'],
            status=PostStatus(row['status']),
            created_at=row['created_at'],
            scheduled_for=row['scheduled_for'],
            posted_at=row['posted_at'],
            thread_items=json.loads(row['thread_items']) if row['thread_items'] else None,
            hashtags=json.loads(row['hashtags']) if row['hashtags'] else [],
            media_path=row['media_path'],
            error_message=row['error_message'],
            tweet_id=row['tweet_id'],
            engagement_expected=bool(row.get('engagement_expected', 0))
        )


class XPostQueue:
    """Unified SQLite-based queue for X posts.

    Features:
    - Draft posts with approval workflow
    - Scheduled posting
    - Thread support
    - Media attachment tracking
    - Milestone tracking to prevent duplicates
    - Posting history log

    Example:
        queue = XPostQueue()

        # Add draft
        post_id = queue.add_post(
            text="New feature shipped!",
            category="feature",
            hashtags=["buildinpublic"]
        )

        # Review and approve
        drafts = queue.get_posts(status=PostStatus.DRAFT)
        queue.approve_post(post_id)

        # Mark as posted
        queue.mark_posted(post_id, success=True, tweet_id="123456")
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the post queue.

        Args:
            db_path: Path to SQLite database. Defaults to
                ~/.openclaw/data/x_posts.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Main posts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                scheduled_for TEXT,
                posted_at TEXT,
                thread_items TEXT,
                hashtags TEXT,
                media_path TEXT,
                error_message TEXT,
                tweet_id TEXT,
                engagement_expected INTEGER DEFAULT 0
            )
        ''')

        # Posting log for history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                success INTEGER,
                error TEXT,
                tweet_id TEXT
            )
        ''')

        # Milestone tracking (prevent duplicate milestone posts)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS milestones (
                milestone_type TEXT,
                milestone_value INTEGER,
                posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                tweet_id TEXT,
                PRIMARY KEY (milestone_type, milestone_value)
            )
        ''')

        # Create indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_posts_status
            ON posts(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_posts_scheduled
            ON posts(scheduled_for)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_posts_category
            ON posts(category)
        ''')

        conn.commit()
        conn.close()

    def add_post(self, text: str, category: str,
                 thread_items: Optional[List[str]] = None,
                 hashtags: Optional[List[str]] = None,
                 media_path: Optional[str] = None,
                 scheduled_for: Optional[datetime] = None,
                 auto_approve: bool = False) -> str:
        """Add a post to the queue.

        Args:
            text: Post text
            category: Post category (from PostCategory enum)
            thread_items: Optional list of thread continuation texts
            hashtags: Optional list of hashtags
            media_path: Optional path to media file
            scheduled_for: Optional scheduled posting time
            auto_approve: If True, set status to APPROVED immediately

        Returns:
            Post ID
        """
        post_id = hashlib.sha256(f"{text}{time.time()}".encode()).hexdigest()[:16]
        status = PostStatus.APPROVED if auto_approve else PostStatus.DRAFT

        if scheduled_for:
            status = PostStatus.SCHEDULED

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO posts (id, text, category, status, scheduled_for,
                              thread_items, hashtags, media_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_id, text, category, status.value,
            scheduled_for.isoformat() if scheduled_for else None,
            json.dumps(thread_items) if thread_items else None,
            json.dumps(hashtags) if hashtags else None,
            media_path
        ))

        conn.commit()
        conn.close()

        logger.info(f"Added post {post_id}: {text[:50]}... [{status.value}]")
        return post_id

    def get_posts(self, status: Optional[PostStatus] = None,
                  category: Optional[str] = None,
                  limit: int = 50) -> List[QueuedPost]:
        """Get posts from queue.

        Args:
            status: Optional status filter
            category: Optional category filter
            limit: Maximum results

        Returns:
            List of QueuedPost objects
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM posts WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status.value)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [QueuedPost.from_row(row) for row in rows]

    def get_post(self, post_id: str) -> Optional[QueuedPost]:
        """Get a single post by ID.

        Args:
            post_id: Post ID

        Returns:
            QueuedPost or None
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        conn.close()

        return QueuedPost.from_row(row) if row else None

    def approve_post(self, post_id: str) -> bool:
        """Approve a draft post.

        Args:
            post_id: Post ID

        Returns:
            True if approved, False if not found or not a draft
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE posts SET status = ?
            WHERE id = ? AND status = ?
        ''', (PostStatus.APPROVED.value, post_id, PostStatus.DRAFT.value))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if success:
            logger.info(f"Approved post {post_id}")
        return success

    def cancel_post(self, post_id: str) -> bool:
        """Cancel a post.

        Args:
            post_id: Post ID

        Returns:
            True if cancelled
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE posts SET status = ?
            WHERE id = ? AND status IN (?, ?, ?)
        ''', (PostStatus.CANCELLED.value, post_id,
              PostStatus.DRAFT.value, PostStatus.APPROVED.value,
              PostStatus.SCHEDULED.value))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if success:
            logger.info(f"Cancelled post {post_id}")
        return success

    def mark_posted(self, post_id: str, success: bool,
                    tweet_id: Optional[str] = None,
                    error: Optional[str] = None) -> bool:
        """Mark a post as posted (or failed).

        Args:
            post_id: Post ID
            success: Whether posting succeeded
            tweet_id: X tweet ID on success
            error: Error message on failure

        Returns:
            True if updated
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        status = PostStatus.POSTED if success else PostStatus.FAILED
        posted_at = datetime.now().isoformat() if success else None

        cursor.execute('''
            UPDATE posts SET status = ?, posted_at = ?, tweet_id = ?, error_message = ?
            WHERE id = ?
        ''', (status.value, posted_at, tweet_id, error, post_id))

        # Log the attempt
        cursor.execute('''
            INSERT INTO post_log (post_id, success, error, tweet_id)
            VALUES (?, ?, ?, ?)
        ''', (post_id, int(success), error, tweet_id))

        conn.commit()
        conn.close()

        logger.info(f"Marked post {post_id} as {status.value}")
        return True

    def get_scheduled_posts(self, due_now: bool = True) -> List[QueuedPost]:
        """Get posts scheduled for posting.

        Args:
            due_now: If True, only return posts whose scheduled time has passed

        Returns:
            List of scheduled QueuedPost objects
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM posts WHERE status = ?"
        params = [PostStatus.SCHEDULED.value]

        if due_now:
            query += " AND scheduled_for <= ?"
            params.append(datetime.now().isoformat())

        query += " ORDER BY scheduled_for ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [QueuedPost.from_row(row) for row in rows]

    def get_due_posts(self) -> List[QueuedPost]:
        """Get posts ready to be posted (approved and due).

        Returns:
            List of QueuedPost objects ready for posting
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get approved posts OR scheduled posts that are due
        cursor.execute('''
            SELECT * FROM posts
            WHERE status = ?
               OR (status = ? AND scheduled_for <= ?)
            ORDER BY created_at ASC
        ''', (PostStatus.APPROVED.value, PostStatus.SCHEDULED.value,
              datetime.now().isoformat()))

        rows = cursor.fetchall()
        conn.close()

        return [QueuedPost.from_row(row) for row in rows]

    # ==========================================================================
    # Milestone Tracking
    # ==========================================================================

    def is_milestone_posted(self, milestone_type: str, milestone_value: int) -> bool:
        """Check if a milestone has already been posted.

        Args:
            milestone_type: Type of milestone (e.g., "tasks_completed")
            milestone_value: Milestone value (e.g., 100)

        Returns:
            True if already posted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 1 FROM milestones
            WHERE milestone_type = ? AND milestone_value = ?
        ''', (milestone_type, milestone_value))

        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def mark_milestone_posted(self, milestone_type: str, milestone_value: int,
                              tweet_id: Optional[str] = None) -> bool:
        """Mark a milestone as posted.

        Args:
            milestone_type: Type of milestone
            milestone_value: Milestone value
            tweet_id: Associated tweet ID

        Returns:
            True if newly recorded, False if already exists
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO milestones (milestone_type, milestone_value, tweet_id)
                VALUES (?, ?, ?)
            ''', (milestone_type, milestone_value, tweet_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.

        Returns:
            Dict with counts by status
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM posts
            GROUP BY status
        ''')

        stats = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        # Ensure all statuses are present
        for status in PostStatus:
            stats.setdefault(status.value, 0)

        return stats


# Convenience function
def get_x_queue() -> XPostQueue:
    """Get a configured X post queue.

    Returns:
        XPostQueue instance
    """
    return XPostQueue()
