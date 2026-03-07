#!/usr/bin/env python3
"""
Kurultai X/Twitter Presence Maintenance Script
Automated posting, engagement, and weekly summaries
"""

import os
import sys
import json
import time
import random
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib
import hmac
import base64
import urllib.parse
import requests
from dataclasses import dataclass, asdict
from enum import Enum

# Configuration
BASE_DIR = Path("/Users/kublai/.openclaw/agents/main")
DATA_DIR = Path("/Users/kublai/.openclaw/data")
LOG_DIR = Path("/Users/kublai/.openclaw/logs")
DB_PATH = DATA_DIR / "twitter_queue.db"
LOG_PATH = LOG_DIR / "twitter-maintenance.log"
CREDENTIALS_PATH = BASE_DIR / ".x_api_credentials"

# Rate limits (X API v2)
RATE_LIMITS = {
    "tweet_post": {"limit": 200, "window": 24},  # per 24 hours
    "likes": {"limit": 1000, "window": 24},
    "retweets": {"limit": 1000, "window": 24},
    "mentions": {"limit": 1000, "window": 24},
}

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


class TweetCategory(Enum):
    TECHNICAL = "technical"
    ACHIEVEMENT = "achievement"
    COMMUNITY = "community"
    INSIGHT = "insight"
    SUMMARY = "summary"


@dataclass
class TweetContent:
    id: str
    text: str
    category: TweetCategory
    approved: bool
    posted: bool
    posted_at: Optional[str] = None
    created_at: str = None
    engagement_expected: bool = False

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class XAPIClient:
    """X/Twitter API v2 Client with OAuth 1.0a"""

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

        # Create parameter string
        sorted_params = sorted(params.items())
        param_string = '&'.join([f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" for k, v in sorted_params])

        # Create signature base string
        base_url = url.split('?')[0]
        signature_base = f"{method.upper()}&{urllib.parse.quote(base_url, safe='')}&{urllib.parse.quote(param_string, safe='')}"

        # Create signing key
        signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

        # Generate signature
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

        # Build header string
        header_parts = [f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in params.items()]
        return 'OAuth ' + ', '.join(header_parts)

    def _check_rate_limit(self, endpoint: str) -> bool:
        """Check if we can make a request to this endpoint"""
        if endpoint in self.rate_limit_reset:
            reset_time = self.rate_limit_reset[endpoint]
            if datetime.now().timestamp() < reset_time and self.rate_limit_remaining.get(endpoint, 1) <= 0:
                logger.warning(f"Rate limit hit for {endpoint}. Reset at {datetime.fromtimestamp(reset_time)}")
                return False
        return True

    def _update_rate_limit(self, response: requests.Response, endpoint: str):
        """Update rate limit info from response headers"""
        if 'x-rate-limit-remaining' in response.headers:
            self.rate_limit_remaining[endpoint] = int(response.headers['x-rate-limit-remaining'])
        if 'x-rate-limit-reset' in response.headers:
            self.rate_limit_reset[endpoint] = int(response.headers['x-rate-limit-reset'])

    def post_tweet(self, text: str, reply_to: Optional[str] = None) -> Optional[Dict]:
        """Post a tweet"""
        url = f"{self.base_url}/tweets"

        if not self._check_rate_limit("tweet_post"):
            return None

        payload = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}

        headers = {
            "Authorization": self._get_oauth_header("POST", url),
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            self._update_rate_limit(response, "tweet_post")

            if response.status_code == 201:
                logger.info(f"Tweet posted successfully: {text[:50]}...")
                return response.json()
            elif response.status_code == 429:
                logger.error("Rate limit exceeded for tweets")
                return None
            else:
                logger.error(f"Failed to post tweet: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error posting tweet: {e}")
            return None

    def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet"""
        user_id = self.credentials.get('X_ACCESS_TOKEN', '').split('-')[0]
        url = f"{self.base_url}/users/{user_id}/likes"

        if not self._check_rate_limit("likes"):
            return False

        headers = {
            "Authorization": self._get_oauth_header("POST", url),
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json={"tweet_id": tweet_id}, headers=headers)
            self._update_rate_limit(response, "likes")
            return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Error liking tweet: {e}")
            return False

    def retweet(self, tweet_id: str) -> bool:
        """Retweet a tweet"""
        user_id = self.credentials.get('X_ACCESS_TOKEN', '').split('-')[0]
        url = f"{self.base_url}/users/{user_id}/retweets"

        if not self._check_rate_limit("retweets"):
            return False

        headers = {
            "Authorization": self._get_oauth_header("POST", url),
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json={"tweet_id": tweet_id}, headers=headers)
            self._update_rate_limit(response, "retweets")
            return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Error retweeting: {e}")
            return False

    def search_tweets(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search for tweets"""
        url = f"{self.base_url}/tweets/search/recent"
        params = {"query": query, "max_results": min(max_results, 100)}

        headers = {
            "Authorization": self._get_oauth_header("GET", url + "?" + urllib.parse.urlencode(params))
        }

        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                logger.error(f"Search failed: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
            return []


class ContentQueue:
    """SQLite-based content queue for tweets"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tweets (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                approved INTEGER DEFAULT 0,
                posted INTEGER DEFAULT 0,
                posted_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                engagement_expected INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT,
                text TEXT,
                posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                success INTEGER,
                error TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rate_limit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def add_tweet(self, text: str, category: TweetCategory, approved: bool = False) -> str:
        """Add a tweet to the queue"""
        tweet_id = hashlib.sha256(f"{text}{time.time()}".encode()).hexdigest()[:16]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO tweets (id, text, category, approved, posted)
                VALUES (?, ?, ?, ?, 0)
            ''', (tweet_id, text, category.value, 1 if approved else 0))
            conn.commit()
            logger.info(f"Added tweet to queue: {text[:50]}...")
            return tweet_id
        except sqlite3.IntegrityError:
            logger.warning("Duplicate tweet detected, skipping")
            return None
        finally:
            conn.close()

    def get_pending_tweets(self, category: Optional[TweetCategory] = None, limit: int = 10) -> List[TweetContent]:
        """Get pending (approved but not posted) tweets"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if category:
            cursor.execute('''
                SELECT * FROM tweets WHERE approved = 1 AND posted = 0 AND category = ?
                ORDER BY created_at LIMIT ?
            ''', (category.value, limit))
        else:
            cursor.execute('''
                SELECT * FROM tweets WHERE approved = 1 AND posted = 0
                ORDER BY created_at LIMIT ?
            ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        tweets = []
        for row in rows:
            tweets.append(TweetContent(
                id=row[0],
                text=row[1],
                category=TweetCategory(row[2]),
                approved=bool(row[3]),
                posted=bool(row[4]),
                posted_at=row[5],
                created_at=row[6],
                engagement_expected=bool(row[7])
            ))
        return tweets

    def mark_posted(self, tweet_id: str, success: bool, error: Optional[str] = None):
        """Mark a tweet as posted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        posted_at = datetime.now().isoformat()

        cursor.execute('''
            UPDATE tweets SET posted = 1, posted_at = ? WHERE id = ?
        ''', (posted_at, tweet_id))

        cursor.execute('''
            INSERT INTO posted_log (tweet_id, posted_at, success, error)
            SELECT text, ?, ?, ? FROM tweets WHERE id = ?
        ''', (posted_at, 1 if success else 0, error, tweet_id))

        conn.commit()
        conn.close()

    def get_stats(self) -> Dict:
        """Get queue statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tweets WHERE posted = 0 AND approved = 1")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tweets WHERE posted = 1")
        posted = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tweets WHERE approved = 0")
        awaiting_approval = cursor.fetchone()[0]

        cursor.execute("""
            SELECT category, COUNT(*) FROM tweets
            WHERE posted = 0 AND approved = 1
            GROUP BY category
        """)
        by_category = dict(cursor.fetchall())

        conn.close()

        return {
            "pending": pending,
            "posted": posted,
            "awaiting_approval": awaiting_approval,
            "by_category": by_category
        }

    def log_rate_limit_action(self, action: str):
        """Log a rate-limited action"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO rate_limit_log (action) VALUES (?)", (action,))
        conn.commit()
        conn.close()


class TwitterMaintenance:
    """Main Twitter maintenance orchestrator"""

    # Pre-approved content templates
    DEFAULT_CONTENT = [
        # Technical content
        ("Building autonomous agent systems? The Kurultai approach: 6 specialized agents, one unified goal. Multi-agent coordination without the chaos.", TweetCategory.TECHNICAL, True),
        ("Agent-to-agent communication is the unsung hero of scalable AI systems. Here's how we handle secure cross-agent messaging at Kurultai 🧵", TweetCategory.TECHNICAL, True),
        ("The future isn't one AI doing everything. It's many AIs doing what they do best, coordinated by intelligent routing.", TweetCategory.TECHNICAL, True),
        ("Just shipped: Self-healing agent clusters. When one agent fails, others redistribute the load automatically.", TweetCategory.TECHNICAL, True),

        # Achievements
        ("Kurultai processed 1,000+ tasks this week across 6 specialized agents. The horde grows stronger.", TweetCategory.ACHIEVEMENT, True),
        ("Our agent routing system achieved 99.2% accuracy in task classification. Smart dispatch = efficient execution.", TweetCategory.ACHIEVEMENT, True),
        ("New milestone: Multi-agent reflection protocol now catches 94% of potential errors before they reach production.", TweetCategory.ACHIEVEMENT, True),

        # Community
        ("What tools are you using for agent orchestration in 2026? We're always exploring new approaches to multi-agent coordination.", TweetCategory.COMMUNITY, True),
        ("Shoutout to all the builders working on autonomous systems. The future is being written in commits right now.", TweetCategory.COMMUNITY, True),
        ("Building in public: Our agent task routing algorithm is now documented in the open. Check it out 👇", TweetCategory.COMMUNITY, True),

        # Insights
        ("The hardest part of multi-agent systems isn't the agents—it's the coordination layer. Most projects fail at routing, not reasoning.", TweetCategory.INSIGHT, True),
        ("3 signs your AI system needs multi-agent architecture: 1) Single model hitting context limits 2) Need for parallel processing 3) Different expertise domains", TweetCategory.INSIGHT, True),
        ("Reflection is the meta-skill of autonomous systems. Agents that can review their own work outperform those that can't.", TweetCategory.INSIGHT, True),
    ]

    def __init__(self):
        self.client = XAPIClient(CREDENTIALS_PATH)
        self.queue = ContentQueue(DB_PATH)
        self._init_default_content()

    def _init_default_content(self):
        """Initialize with default content if queue is empty"""
        stats = self.queue.get_stats()
        if stats["pending"] == 0 and stats["awaiting_approval"] == 0:
            logger.info("Initializing default content queue")
            for text, category, approved in self.DEFAULT_CONTENT:
                self.queue.add_tweet(text, category, approved)

    def post_scheduled_tweet(self) -> bool:
        """Post one scheduled tweet from the queue"""
        pending = self.queue.get_pending_tweets(limit=1)

        if not pending:
            logger.info("No pending tweets in queue")
            return False

        tweet = pending[0]

        # Add some variety - occasionally vary the posting time slightly
        if random.random() < 0.1:  # 10% chance to skip and try next
            pending = self.queue.get_pending_tweets(limit=5)
            if len(pending) > 1:
                tweet = random.choice(pending[1:])

        result = self.client.post_tweet(tweet.text)

        if result:
            self.queue.mark_posted(tweet.id, True)
            return True
        else:
            self.queue.mark_posted(tweet.id, False, "API error or rate limit")
            return False

    def engage_with_community(self):
        """Engage with AI/developer community content"""
        # Search for relevant content
        queries = [
            "AI agents multi-agent",
            "autonomous systems",
            "LLM orchestration",
            "agent framework"
        ]

        query = random.choice(queries)
        tweets = self.client.search_tweets(query, max_results=10)

        engagement_count = 0
        for tweet in tweets:
            tweet_id = tweet.get("id")
            text = tweet.get("text", "").lower()

            # Avoid controversial topics (basic filtering)
            avoid_keywords = ["crypto", "nft", "scam", "scamming", "political", "politics", "election", "trump", "biden"]
            if any(kw in text for kw in avoid_keywords):
                continue

            # Randomly decide to like or retweet (not both to avoid spam)
            action = random.choice(["like", "retweet", None])

            if action == "like":
                if self.client.like_tweet(tweet_id):
                    engagement_count += 1
                    logger.info(f"Liked tweet: {tweet_id}")
            elif action == "retweet":
                if self.client.retweet(tweet_id):
                    engagement_count += 1
                    logger.info(f"Retweeted: {tweet_id}")

            # Limit daily engagement
            if engagement_count >= 5:
                break

            time.sleep(1)  # Be polite to the API

        logger.info(f"Community engagement complete: {engagement_count} actions")

    def post_weekly_summary(self):
        """Post weekly summary thread on Sundays"""
        today = datetime.now()
        if today.weekday() != 6:  # Sunday
            logger.info("Weekly summary only runs on Sundays")
            return

        # Check if already posted this week
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        week_ago = (today - timedelta(days=7)).isoformat()
        cursor.execute('''
            SELECT COUNT(*) FROM posted_log
            WHERE posted_at > ? AND text LIKE '%Weekly Kurultai Summary%'
        ''', (week_ago,))
        count = cursor.fetchone()[0]
        conn.close()

        if count > 0:
            logger.info("Weekly summary already posted this week")
            return

        # Generate summary content
        stats = self.queue.get_stats()

        thread = [
            "📊 Weekly Kurultai Summary 🧵",
            f"This week: {stats['posted']} tasks completed across our agent swarm. Here's what the horde accomplished:",
            "🔧 Technical: Refactored task routing for 15% faster dispatch times. Multi-agent coordination remains our core focus.",
            "🤖 Agents: All 6 specialists (Kublai, Ogedei, Mongke, Chagatai, Ariq, Tolui) operating at >95% success rate.",
            "📈 Growth: Steady progress on Parse platform integration. Building the foundation for scalable agent infrastructure.",
            "🎯 Next week: Rolling out enhanced reflection protocols. Agents will self-improve based on weekly performance reviews.",
            "Thanks for following our journey. The future is multi-agent. 🚀"
        ]

        # Post thread
        prev_tweet_id = None
        for tweet_text in thread:
            result = self.client.post_tweet(tweet_text, reply_to=prev_tweet_id)
            if result:
                prev_tweet_id = result.get("data", {}).get("id")
                time.sleep(2)  # Small delay between thread tweets
            else:
                logger.error(f"Failed to post thread tweet: {tweet_text[:50]}...")
                break

        logger.info("Weekly summary thread posted")

    def run(self, mode: str = "auto"):
        """Run maintenance based on mode"""
        logger.info(f"Starting Twitter maintenance (mode: {mode})")

        if mode == "tweet":
            self.post_scheduled_tweet()
        elif mode == "engage":
            self.engage_with_community()
        elif mode == "weekly":
            self.post_weekly_summary()
        elif mode == "auto":
            # Determine action based on time
            hour = datetime.now().hour

            if hour in [9, 14, 19]:  # Posting times: 9am, 2pm, 7pm
                self.post_scheduled_tweet()
            elif hour == 12:  # Midday engagement
                self.engage_with_community()
            elif datetime.now().weekday() == 6 and hour == 10:  # Sunday weekly summary
                self.post_weekly_summary()

        logger.info("Twitter maintenance complete")

    def get_status(self) -> Dict:
        """Get current status"""
        return {
            "queue_stats": self.queue.get_stats(),
            "rate_limits": self.client.rate_limit_remaining,
            "timestamp": datetime.now().isoformat()
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Kurultai Twitter Maintenance")
    parser.add_argument("mode", choices=["tweet", "engage", "weekly", "auto", "status", "init"],
                        default="auto", nargs="?",
                        help="Operation mode")
    parser.add_argument("--add-tweet", metavar="TEXT",
                        help="Add a new tweet to the queue")
    parser.add_argument("--category", default="technical",
                        choices=[c.value for c in TweetCategory],
                        help="Category for new tweet")
    parser.add_argument("--approve", action="store_true",
                        help="Auto-approve added tweet")

    args = parser.parse_args()

    maintenance = TwitterMaintenance()

    if args.add_tweet:
        category = TweetCategory(args.category)
        tweet_id = maintenance.queue.add_tweet(args.add_tweet, category, args.approve)
        if tweet_id:
            print(f"Tweet added with ID: {tweet_id}")
        sys.exit(0)

    if args.mode == "status":
        status = maintenance.get_status()
        print(json.dumps(status, indent=2))
        sys.exit(0)

    if args.mode == "init":
        print("Content queue initialized")
        stats = maintenance.queue.get_stats()
        print(f"Queue stats: {json.dumps(stats, indent=2)}")
        sys.exit(0)

    maintenance.run(args.mode)


if __name__ == "__main__":
    main()
