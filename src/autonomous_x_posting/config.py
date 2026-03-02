import os
import logging
from dotenv import load_dotenv

# Load credentials from .x_api_credentials securely
load_dotenv('/Users/kublai/.openclaw/agents/main/.x_api_credentials')

# X API Credentials
X_API_KEY = os.getenv('X_API_KEY')
X_API_SECRET = os.getenv('X_API_SECRET')
X_ACCESS_TOKEN = os.getenv('X_ACCESS_TOKEN')
X_ACCESS_TOKEN_SECRET = os.getenv('X_ACCESS_TOKEN_SECRET')

# Parse Platform API
PARSE_API_URL = "https://www.parsethe.media/api/v1/article/analyze"

# RSS Feeds (Technology & AI news)
RSS_FEEDS = [
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/rss",
    "https://arxiv.org/rss/cs.AI",
]

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/twitter_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
