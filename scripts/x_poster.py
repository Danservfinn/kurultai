#!/usr/bin/env python3
"""
OpenClaw X/Twitter Poster
Automated posting system for OpenClaw updates with approval workflow
"""

import os
import sys
import json
import time
import hashlib
import logging
import sqlite3
import urllib.parse
import hmac
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import requests

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from x_content_generator import ContentGenerator, PostCategory, GeneratedPost
except ImportError:
    # Fallback definitions
    class PostCategory(Enum):
        STATUS = "status"
        MILESTONE = "milestone"
        FEATURE = "feature"
        WEEKLY = "weekly"
        BUILD_PUBLIC = "build_public"

    @dataclass
    class GeneratedPost:
        text: str
        category: PostCategory
        hashtags: List[str]
        scheduled_for: Optional[datetime] = None
        media_path: Optional[str] = None
        thread_items: Optional[List[str]] = None


# Configuration
BASE_DIR = Path("/Users/kublai/.openclaw/agents/main")
DATA_DIR = Path("/Users/kublai/.openclaw/data")
LOG_DIR = Path("/Users/kublai/.openclaw/logs")
DB_PATH = DATA_DIR / "openclaw_x_posts.db"
LOG_PATH = LOG_DIR / "openclaw-x-poster.log"
CREDENTIALS_PATH = BASE_DIR / ".x_api_credentials"
PAUSE_FLAG_PATH = DATA_DIR / "x_posting_paused"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class PostStatus(Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"


@dataclass
class QueuedPost:
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


class XAPIClient:
    """X/Twitter API v2 Client with OAuth 1.0a - Reused from twitter_maintenance.py"""

    def __init__(self, credentials_path: Path):
        self.credentials = self._load_credentials(credentials_path)
        self.base_url = "https://api.twitter.com/2"
        self.rate_limit_remaining = {}
        self.rate_limit_reset = {}

    def _load_credentials(self, path: Path) -> Dict[str, str]:
        """Load credentials from env file"""
        credentials = {}
        if not path.exists():
            raise FileNotFoundError(f"Credentials file not found: {path}")

        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    credentials[key] = value
        return credentials

    def _generate_oauth_signature(self, method: str, url: str, params: Dict[str, str]) -> str:
        """Generate OAuth 1.0a signature"""
        consumer_secret = self.credentials.get('X_API_SECRET', '')
        token_secret = self.credentials.get('X_ACCESS_TOKEN_SECRET', '')

        sorted_params = sorted(params.items())
        param_string = '&'.join([f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" for k, v in sorted_params])

        base_url = url.split('?')[0]
        signature_base = f"{method.upper()}&{urllib.parse.quote(base_url, safe='')}&{urllib.parse.quote(param_string, safe='')}"

        signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

        signature = hmac.new(
            signing_key.encode('utf-8'),
            signature_base.encode('utf-8'),
            hashlib.sha1
        ).digest()

        return base64.b64encode(signature).decode('utf-8')

    def _get_oauth_header(self, method: str, url: str) -> str:
        """Generate OAuth 1.0a Authorization header"""
        timestamp = str(int(time.time()))
        nonce = hashlib.sha256(os.urandom(32)).hexdigest()[:32]

        params = {
            'oauth_consumer_key': self.credentials.get('X_API_KEY', ''),
            'oauth_token': self.credentials.get('X_ACCESS_TOKEN', ''),
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': timestamp,
            'oauth_nonce': nonce,
            'oauth_version': '1.0'
        }

        signature = self._generate_oauth_signature(method, url, params)
        params['oauth_signature'] = signature

        header_parts = [f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in params.items()]
        return 'OAuth ' + ', '.join(header_parts)

    def _check_rate_limit(self, endpoint: str) -> bool:
        """Check if we can make a request"""
        if endpoint in self.rate_limit_reset:
            reset_time = self.rate_limit_reset[endpoint]
            if datetime.now().timestamp() < reset_time and self.rate_limit_remaining.get(endpoint, 1) <= 0:
                logger.warning(f"Rate limit hit for {endpoint}")
                return False
        return True

    def _update_rate_limit(self, response: requests.Response, endpoint: str):
        """Update rate limit info from response headers"""
        if 'x-rate-limit-remaining' in response.headers:
            self.rate_limit_remaining[endpoint] = int(response.headers['x-rate-limit-remaining'])
        if 'x-rate-limit-reset' in response.headers:
            self.rate_limit_reset[endpoint] = int(response.headers['x-rate-limit-reset'])

    def post_tweet(self, text: str, reply_to: Optional[str] = None,
                   media_ids: Optional[List[str]] = None) -> Optional[Dict]:
        """Post a tweet"""
        url = f"{self.base_url}/tweets"

        if not self._check_rate_limit("tweet_post"):
            return None

        payload = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}

        headers = {
            "Authorization": self._get_oauth_header("POST", url),
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            self._update_rate_limit(response, "tweet_post")

            if response.status_code == 201:
                logger.info(f"Tweet posted: {text[:50]}...")
                return response.json()
            elif response.status_code == 429:
                logger.error("Rate limit exceeded")
                return None
            else:
                logger.error(f"Failed to post: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error posting tweet: {e}")
            return None

    def upload_media(self, media_path: str) -> Optional[str]:
        """Upload media and return media ID"""
        url = "https://upload.twitter.com/1.1/media/upload.json"

        if not Path(media_path).exists():
            logger.error(f"Media file not found: {media_path}")
            return None

        headers = {
            "Authorization": self._get_oauth_header("POST", url)
        }

        try:
            with open(media_path, 'rb') as f:
                files = {'media': f}
                response = requests.post(url, files=files, headers=headers)

            if response.status_code in [200, 201]:
                return response.json().get('media_id_string')
            else:
                logger.error(f"Media upload failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error uploading media: {e}")
            return None


class PostQueue:
    """SQLite-based queue for draft and scheduled posts"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                scheduled_for TEXT,
                posted_at TEXT,
                thread_items TEXT,
                hashtags TEXT,
                media_path TEXT,
                error_message TEXT,
                tweet_id TEXT
            )
        ''')

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS milestones (
                milestone_type TEXT,
                milestone_value INTEGER,
                posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (milestone_type, milestone_value)
            )
        ''')

        conn.commit()
        conn.close()

    def add_post(self, text: str, category: str, thread_items: Optional[List[str]] = None,
                 hashtags: Optional[List[str]] = None, media_path: Optional[str] = None,
                 scheduled_for: Optional[datetime] = None) -> str:
        """Add a post to the queue"""
        post_id = hashlib.sha256(f"{text}{time.time()}".encode()).hexdigest()[:16]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO posts (id, text, category, status, thread_items, hashtags, media_path, scheduled_for)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_id, text, category, PostStatus.DRAFT.value,
                json.dumps(thread_items) if thread_items else None,
                json.dumps(hashtags) if hashtags else None,
                media_path,
                scheduled_for.isoformat() if scheduled_for else None
            ))
            conn.commit()
            logger.info(f"Added post to queue: {text[:50]}...")
            return post_id
        except sqlite3.IntegrityError:
            logger.warning("Duplicate post detected")
            return None
        finally:
            conn.close()

    def get_posts(self, status: Optional[PostStatus] = None, limit: int = 50) -> List[QueuedPost]:
        """Get posts from queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status:
            cursor.execute('''
                SELECT * FROM posts WHERE status = ? ORDER BY created_at LIMIT ?
            ''', (status.value, limit))
        else:
            cursor.execute('''
                SELECT * FROM posts ORDER BY created_at LIMIT ?
            ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        posts = []
        for row in rows:
            posts.append(QueuedPost(
                id=row[0],
                text=row[1],
                category=row[2],
                status=PostStatus(row[3]),
                created_at=row[4],
                scheduled_for=row[5],
                posted_at=row[6],
                thread_items=json.loads(row[7]) if row[7] else None,
                hashtags=json.loads(row[8]) if row[8] else [],
                media_path=row[9],
                error_message=row[10],
                tweet_id=row[11]
            ))
        return posts

    def approve_post(self, post_id: str) -> bool:
        """Approve a draft post"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE posts SET status = ? WHERE id = ?
        ''', (PostStatus.APPROVED.value, post_id))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if success:
            logger.info(f"Post approved: {post_id}")

        return success

    def mark_posted(self, post_id: str, success: bool, tweet_id: Optional[str] = None,
                    error: Optional[str] = None):
        """Mark a post as posted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        posted_at = datetime.now().isoformat()
        status = PostStatus.POSTED if success else PostStatus.FAILED

        cursor.execute('''
            UPDATE posts
            SET status = ?, posted_at = ?, tweet_id = ?, error_message = ?
            WHERE id = ?
        ''', (status.value, posted_at, tweet_id, error, post_id))

        cursor.execute('''
            INSERT INTO post_log (post_id, posted_at, success, error, tweet_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (post_id, posted_at, 1 if success else 0, error, tweet_id))

        conn.commit()
        conn.close()

    def check_milestone(self, milestone_type: str, milestone_value: int) -> bool:
        """Check if milestone has been posted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*) FROM milestones
            WHERE milestone_type = ? AND milestone_value = ?
        ''', (milestone_type, milestone_value))

        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    def record_milestone(self, milestone_type: str, milestone_value: int):
        """Record that a milestone was posted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO milestones (milestone_type, milestone_value, posted_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (milestone_type, milestone_value))

        conn.commit()
        conn.close()

    def get_due_scheduled_posts(self) -> List[QueuedPost]:
        """Get posts that are scheduled for now or past"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute('''
            SELECT * FROM posts
            WHERE status = ? AND scheduled_for IS NOT NULL AND scheduled_for <= ?
            ORDER BY scheduled_for
        ''', (PostStatus.SCHEDULED.value, now))

        rows = cursor.fetchall()
        conn.close()

        posts = []
        for row in rows:
            posts.append(QueuedPost(
                id=row[0], text=row[1], category=row[2], status=PostStatus(row[3]),
                created_at=row[4], scheduled_for=row[5], posted_at=row[6],
                thread_items=json.loads(row[7]) if row[7] else None,
                hashtags=json.loads(row[8]) if row[8] else [],
                media_path=row[9], error_message=row[10], tweet_id=row[11]
            ))
        return posts


class XPoster:
    """Main OpenClaw X posting orchestrator"""

    def __init__(self):
        self.client = XAPIClient(CREDENTIALS_PATH)
        self.queue = PostQueue(DB_PATH)
        self.generator = ContentGenerator()
        self._paused = PAUSE_FLAG_PATH.exists()

    def is_paused(self) -> bool:
        """Check if posting is paused"""
        return PAUSE_FLAG_PATH.exists()

    def emergency_pause(self):
        """Pause all posting"""
        PAUSE_FLAG_PATH.touch()
        logger.warning("X posting paused via emergency pause")
        self._paused = True

    def resume(self):
        """Resume posting"""
        if PAUSE_FLAG_PATH.exists():
            PAUSE_FLAG_PATH.unlink()
        logger.info("X posting resumed")
        self._paused = False

    def post_status_update(self, dry_run: bool = False) -> bool:
        """Generate and post daily status update"""
        if self.is_paused():
            logger.info("Posting paused, skipping status update")
            return False

        post = self.generator.generate_status_update()

        if dry_run:
            logger.info(f"DRY RUN: Would post: {post.text}")
            return True

        # Add to queue as approved
        post_id = self.queue.add_post(
            text=post.text,
            category=post.category.value,
            hashtags=post.hashtags
        )
        if post_id:
            self.queue.approve_post(post_id)
            return self._post_queued(post_id)
        return False

    def post_milestone(self, milestone_type: str, value: int, dry_run: bool = False) -> bool:
        """Post milestone celebration"""
        if self.is_paused():
            logger.info("Posting paused, skipping milestone")
            return False

        # Check if already posted
        if self.queue.check_milestone(milestone_type, value):
            logger.info(f"Milestone {milestone_type}={value} already posted")
            return False

        post = self.generator.generate_milestone_post(milestone_type, value)

        if dry_run:
            logger.info(f"DRY RUN: Would post milestone: {post.text}")
            return True

        post_id = self.queue.add_post(
            text=post.text,
            category=post.category.value,
            hashtags=post.hashtags
        )
        if post_id:
            self.queue.approve_post(post_id)
            success = self._post_queued(post_id)
            if success:
                self.queue.record_milestone(milestone_type, value)
            return success
        return False

    def post_feature_showcase(self, feature_name: str, description: str,
                              dry_run: bool = False) -> bool:
        """Post new feature announcement"""
        if self.is_paused():
            logger.info("Posting paused, skipping feature showcase")
            return False

        post = self.generator.generate_feature_showcase(feature_name, description)

        if dry_run:
            logger.info(f"DRY RUN: Would post feature: {post.text}")
            return True

        post_id = self.queue.add_post(
            text=post.text,
            category=post.category.value,
            hashtags=post.hashtags
        )
        if post_id:
            self.queue.approve_post(post_id)
            return self._post_queued(post_id)
        return False

    def schedule_post(self, content: str, scheduled_time: datetime,
                      category: str = "custom") -> str:
        """Schedule a post for future"""
        post_id = self.queue.add_post(
            text=content,
            category=category,
            scheduled_for=scheduled_time
        )

        # Mark as scheduled
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE posts SET status = ? WHERE id = ?
        ''', (PostStatus.SCHEDULED.value, post_id))
        conn.commit()
        conn.close()

        logger.info(f"Scheduled post {post_id} for {scheduled_time}")
        return post_id

    def generate_thread(self, topic: str, points: List[str],
                        dry_run: bool = False) -> bool:
        """Post a multi-tweet thread"""
        if self.is_paused():
            logger.info("Posting paused, skipping thread")
            return False

        # Build thread from topic + points
        thread = [topic] + points

        if dry_run:
            logger.info(f"DRY RUN: Would post thread with {len(thread)} tweets")
            for i, tweet in enumerate(thread):
                logger.info(f"  [{i+1}] {tweet[:60]}...")
            return True

        post_id = self.queue.add_post(
            text=thread[0],
            category="thread",
            thread_items=thread[1:]
        )
        if post_id:
            self.queue.approve_post(post_id)
            return self._post_thread(post_id, thread)
        return False

    def get_pending_posts(self) -> List[Dict]:
        """Get posts awaiting approval"""
        posts = self.queue.get_posts(status=PostStatus.DRAFT)
        return [{"id": p.id, "text": p.text, "category": p.category} for p in posts]

    def approve_post(self, post_id: str) -> bool:
        """Approve a draft post"""
        return self.queue.approve_post(post_id)

    def post_build_public(self, dry_run: bool = False) -> bool:
        """Post 'building in public' update"""
        if self.is_paused():
            logger.info("Posting paused, skipping build public")
            return False

        post = self.generator.generate_build_public()

        if dry_run:
            logger.info(f"DRY RUN: Would post: {post.text}")
            return True

        post_id = self.queue.add_post(
            text=post.text,
            category=post.category.value,
            hashtags=post.hashtags
        )
        if post_id:
            self.queue.approve_post(post_id)
            return self._post_queued(post_id)
        return False

    def post_weekly_review(self, dry_run: bool = False) -> bool:
        """Post weekly summary thread (Fridays only)"""
        if datetime.now().weekday() != 4:  # Friday
            logger.info("Weekly review only runs on Fridays")
            return False

        if self.is_paused():
            logger.info("Posting paused, skipping weekly review")
            return False

        post = self.generator.generate_weekly_thread()

        if dry_run:
            logger.info(f"DRY RUN: Would post weekly thread")
            return True

        post_id = self.queue.add_post(
            text=post.text,
            category=post.category.value,
            thread_items=post.thread_items
        )
        if post_id:
            self.queue.approve_post(post_id)
            return self._post_thread(post_id, [post.text] + (post.thread_items or []))
        return False

    def process_scheduled_posts(self) -> int:
        """Process posts that are due"""
        due_posts = self.queue.get_due_scheduled_posts()
        count = 0

        for post in due_posts:
            if self._post_queued(post.id):
                count += 1

        return count

    def _post_queued(self, post_id: str) -> bool:
        """Post a queued item"""
        posts = self.queue.get_posts(status=PostStatus.APPROVED, limit=100)
        post = next((p for p in posts if p.id == post_id), None)

        if not post:
            logger.error(f"Post {post_id} not found or not approved")
            return False

        result = self.client.post_tweet(post.text, media_ids=None)

        if result:
            tweet_id = result.get("data", {}).get("id")
            self.queue.mark_posted(post_id, True, tweet_id=tweet_id)

            # Handle thread if present
            if post.thread_items:
                self._continue_thread(post.thread_items, tweet_id)

            return True
        else:
            self.queue.mark_posted(post_id, False, error="API error or rate limit")
            return False

    def _post_thread(self, post_id: str, tweets: List[str]) -> bool:
        """Post a full thread"""
        prev_tweet_id = None

        for i, tweet_text in enumerate(tweets):
            result = self.client.post_tweet(tweet_text, reply_to=prev_tweet_id)

            if result:
                prev_tweet_id = result.get("data", {}).get("id")
                time.sleep(2)  # Small delay between thread tweets
            else:
                logger.error(f"Failed to post thread tweet {i+1}")
                return False

        self.queue.mark_posted(post_id, True, tweet_id=prev_tweet_id)
        return True

    def _continue_thread(self, thread_items: List[str], reply_to: str):
        """Continue a thread from an existing tweet"""
        prev_tweet_id = reply_to

        for item in thread_items:
            result = self.client.post_tweet(item, reply_to=prev_tweet_id)
            if result:
                prev_tweet_id = result.get("data", {}).get("id")
                time.sleep(2)
            else:
                break

    def get_status(self) -> Dict:
        """Get current system status"""
        draft_count = len(self.queue.get_posts(status=PostStatus.DRAFT))
        approved_count = len(self.queue.get_posts(status=PostStatus.APPROVED))
        scheduled_count = len(self.queue.get_posts(status=PostStatus.SCHEDULED))

        return {
            "paused": self.is_paused(),
            "draft": draft_count,
            "approved": approved_count,
            "scheduled": scheduled_count,
            "rate_limit_remaining": self.client.rate_limit_remaining,
            "timestamp": datetime.now().isoformat()
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OpenClaw X Poster")
    parser.add_argument("command", choices=[
        "status", "post_status", "post_build_public", "post_weekly",
        "approve", "list_pending", "pause", "resume", "process_scheduled",
        "milestone", "feature", "thread"
    ], help="Command to run")
    parser.add_argument("--post-id", help="Post ID for approval")
    parser.add_argument("--milestone-type", help="Milestone type")
    parser.add_argument("--milestone-value", type=int, help="Milestone value")
    parser.add_argument("--feature-name", help="Feature name")
    parser.add_argument("--feature-desc", help="Feature description")
    parser.add_argument("--topic", help="Thread topic")
    parser.add_argument("--points", nargs="+", help="Thread points")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually post")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    poster = XPoster()

    if args.command == "status":
        status = poster.get_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"Paused: {status['paused']}")
            print(f"Draft: {status['draft']}")
            print(f"Approved: {status['approved']}")
            print(f"Scheduled: {status['scheduled']}")

    elif args.command == "post_status":
        success = poster.post_status_update(dry_run=args.dry_run)
        print(f"{'Posted' if success else 'Failed'}: Status update")

    elif args.command == "post_build_public":
        success = poster.post_build_public(dry_run=args.dry_run)
        print(f"{'Posted' if success else 'Failed'}: Build in public")

    elif args.command == "post_weekly":
        success = poster.post_weekly_review(dry_run=args.dry_run)
        print(f"{'Posted' if success else 'Failed'}: Weekly review")

    elif args.command == "approve":
        if not args.post_id:
            print("Error: --post-id required for approve")
            sys.exit(1)
        success = poster.approve_post(args.post_id)
        print(f"{'Approved' if success else 'Failed'}: Post {args.post_id}")

    elif args.command == "list_pending":
        pending = poster.get_pending_posts()
        if args.json:
            print(json.dumps(pending, indent=2))
        else:
            for p in pending:
                print(f"[{p['id']}] {p['text'][:60]}... ({p['category']})")

    elif args.command == "pause":
        poster.emergency_pause()
        print("X posting paused")

    elif args.command == "resume":
        poster.resume()
        print("X posting resumed")

    elif args.command == "process_scheduled":
        count = poster.process_scheduled_posts()
        print(f"Processed {count} scheduled posts")

    elif args.command == "milestone":
        if not args.milestone_type or args.milestone_value is None:
            print("Error: --milestone-type and --milestone-value required")
            sys.exit(1)
        success = poster.post_milestone(args.milestone_type, args.milestone_value, dry_run=args.dry_run)
        print(f"{'Posted' if success else 'Failed'}: Milestone {args.milestone_type}={args.milestone_value}")

    elif args.command == "feature":
        if not args.feature_name or not args.feature_desc:
            print("Error: --feature-name and --feature-desc required")
            sys.exit(1)
        success = poster.post_feature_showcase(args.feature_name, args.feature_desc, dry_run=args.dry_run)
        print(f"{'Posted' if success else 'Failed'}: Feature {args.feature_name}")

    elif args.command == "thread":
        if not args.topic or not args.points:
            print("Error: --topic and --points required")
            sys.exit(1)
        success = poster.generate_thread(args.topic, args.points, dry_run=args.dry_run)
        print(f"{'Posted' if success else 'Failed'}: Thread")


if __name__ == "__main__":
    main()
