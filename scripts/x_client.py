#!/usr/bin/env python3
"""
X/Twitter API Client - Unified client for X/Twitter API v2.

Consolidates XAPIClient implementations from x_poster.py and twitter_maintenance.py
into a single canonical module with OAuth 1.0a authentication.

Usage:
    from x_client import XAPIClient

    client = XAPIClient()
    result = client.post_tweet("Hello world!")
    media_id = client.upload_media("/path/to/image.png")
"""

import os
import sys
import time
import hashlib
import hmac
import base64
import urllib.parse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests


# Default credentials path (can be overridden)
DEFAULT_CREDENTIALS_PATH = Path.home() / ".openclaw" / "credentials" / "x-api.env"

# Setup logging
logger = logging.getLogger(__name__)


class XAPIError(Exception):
    """Base exception for X API errors."""
    pass


class RateLimitError(XAPIError):
    """Raised when rate limit is exceeded."""
    def __init__(self, endpoint: str, reset_time: Optional[int] = None):
        self.endpoint = endpoint
        self.reset_time = reset_time
        super().__init__(f"Rate limit exceeded for {endpoint}")


class AuthenticationError(XAPIError):
    """Raised when authentication fails."""
    pass


class XAPIClient:
    """Unified X/Twitter API v2 Client with OAuth 1.0a.

    This is the canonical X API client for the Kurultai system.
    All scripts should use this class instead of implementing their own.

    Features:
    - OAuth 1.0a authentication
    - Automatic rate limit tracking
    - Tweet posting with reply and media support
    - Media upload
    - Tweet engagement (like, retweet)
    - Tweet search

    Example:
        client = XAPIClient()
        result = client.post_tweet("Hello from Kurultai!")
        if result:
            print(f"Posted tweet: {result['data']['id']}")
    """

    def __init__(self, credentials_path: Optional[Path] = None):
        """Initialize the X API client.

        Args:
            credentials_path: Path to credentials file. Defaults to
                ~/.openclaw/credentials/x-api.env
        """
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.credentials = self._load_credentials()
        self.base_url = "https://api.twitter.com/2"
        self.upload_url = "https://upload.twitter.com/1.1"

        # Rate limit tracking
        self.rate_limit_remaining: Dict[str, int] = {}
        self.rate_limit_reset: Dict[str, int] = {}

    def _load_credentials(self) -> Dict[str, str]:
        """Load credentials from env file.

        File format:
            X_API_KEY=...
            X_API_SECRET=...
            X_ACCESS_TOKEN=...
            X_ACCESS_TOKEN_SECRET=...

        Returns:
            Dict of credential key-value pairs

        Raises:
            FileNotFoundError: If credentials file doesn't exist
            AuthenticationError: If required credentials are missing
        """
        credentials = {}

        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"X API credentials not found: {self.credentials_path}\n"
                f"Create the file with:\n"
                f"  X_API_KEY=your_key\n"
                f"  X_API_SECRET=your_secret\n"
                f"  X_ACCESS_TOKEN=your_token\n"
                f"  X_ACCESS_TOKEN_SECRET=your_token_secret"
            )

        with open(self.credentials_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    credentials[key.strip()] = value.strip()

        # Validate required credentials
        required = ['X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET']
        missing = [k for k in required if k not in credentials]
        if missing:
            raise AuthenticationError(f"Missing required credentials: {missing}")

        return credentials

    def _generate_oauth_signature(self, method: str, url: str,
                                   params: Dict[str, str]) -> str:
        """Generate OAuth 1.0a signature.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL (without query params)
            params: OAuth parameters

        Returns:
            Base64-encoded signature
        """
        consumer_secret = self.credentials.get('X_API_SECRET', '')
        token_secret = self.credentials.get('X_ACCESS_TOKEN_SECRET', '')

        # Create parameter string (sorted, percent-encoded)
        sorted_params = sorted(params.items())
        param_string = '&'.join([
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted_params
        ])

        # Create signature base string
        base_url = url.split('?')[0]
        signature_base = (
            f"{method.upper()}&"
            f"{urllib.parse.quote(base_url, safe='')}&"
            f"{urllib.parse.quote(param_string, safe='')}"
        )

        # Create signing key
        signing_key = (
            f"{urllib.parse.quote(consumer_secret, safe='')}&"
            f"{urllib.parse.quote(token_secret, safe='')}"
        )

        # Generate HMAC-SHA1 signature
        signature = hmac.new(
            signing_key.encode('utf-8'),
            signature_base.encode('utf-8'),
            hashlib.sha1
        ).digest()

        return base64.b64encode(signature).decode('utf-8')

    def _get_oauth_header(self, method: str, url: str,
                          extra_params: Optional[Dict[str, str]] = None) -> str:
        """Generate OAuth 1.0a Authorization header.

        Args:
            method: HTTP method
            url: Request URL
            extra_params: Additional parameters to include in signature

        Returns:
            OAuth Authorization header value
        """
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

        # Include extra params in signature base
        if extra_params:
            params.update(extra_params)

        signature = self._generate_oauth_signature(method, url, params)
        params['oauth_signature'] = signature

        # Build header string
        header_parts = [
            f'{k}="{urllib.parse.quote(v, safe="")}"'
            for k, v in params.items()
        ]
        return 'OAuth ' + ', '.join(header_parts)

    def _check_rate_limit(self, endpoint: str) -> bool:
        """Check if we can make a request to this endpoint.

        Args:
            endpoint: API endpoint identifier

        Returns:
            True if request is allowed, False if rate limited
        """
        if endpoint in self.rate_limit_reset:
            reset_time = self.rate_limit_reset[endpoint]
            if (datetime.now().timestamp() < reset_time and
                    self.rate_limit_remaining.get(endpoint, 1) <= 0):
                logger.warning(f"Rate limit hit for {endpoint}. "
                              f"Reset at {datetime.fromtimestamp(reset_time)}")
                return False
        return True

    def _update_rate_limit(self, response: requests.Response, endpoint: str):
        """Update rate limit info from response headers.

        Args:
            response: HTTP response
            endpoint: API endpoint identifier
        """
        if 'x-rate-limit-remaining' in response.headers:
            self.rate_limit_remaining[endpoint] = int(
                response.headers['x-rate-limit-remaining']
            )
        if 'x-rate-limit-reset' in response.headers:
            self.rate_limit_reset[endpoint] = int(
                response.headers['x-rate-limit-reset']
            )

    def post_tweet(self, text: str, reply_to: Optional[str] = None,
                   media_ids: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Post a tweet.

        Args:
            text: Tweet text (max 280 characters)
            reply_to: Optional tweet ID to reply to
            media_ids: Optional list of media IDs to attach

        Returns:
            Response data dict on success, None on failure

        Example:
            result = client.post_tweet("Hello world!")
            tweet_id = result['data']['id']
        """
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
                data = response.json()
                logger.info(f"Tweet posted: {text[:50]}...")
                return data
            elif response.status_code == 429:
                logger.error("Rate limit exceeded for tweets")
                return None
            else:
                logger.error(f"Failed to post tweet: {response.status_code} - "
                           f"{response.text}")
                return None
        except Exception as e:
            logger.error(f"Error posting tweet: {e}")
            return None

    def upload_media(self, media_path: str) -> Optional[str]:
        """Upload media and return media ID.

        Args:
            media_path: Path to media file (image, video, gif)

        Returns:
            Media ID string on success, None on failure

        Example:
            media_id = client.upload_media("/path/to/image.png")
            if media_id:
                client.post_tweet("Check this out!", media_ids=[media_id])
        """
        url = f"{self.upload_url}/media/upload.json"

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
                media_id = response.json().get('media_id_string')
                logger.info(f"Media uploaded: {media_id}")
                return media_id
            else:
                logger.error(f"Media upload failed: {response.status_code} - "
                           f"{response.text}")
                return None
        except Exception as e:
            logger.error(f"Error uploading media: {e}")
            return None

    def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet.

        Args:
            tweet_id: Tweet ID to like

        Returns:
            True on success, False on failure
        """
        user_id = self.credentials.get('X_ACCESS_TOKEN', '').split('-')[0]
        url = f"{self.base_url}/users/{user_id}/likes"

        if not self._check_rate_limit("likes"):
            return False

        headers = {
            "Authorization": self._get_oauth_header("POST", url),
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                url, json={"tweet_id": tweet_id}, headers=headers
            )
            self._update_rate_limit(response, "likes")
            return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Error liking tweet: {e}")
            return False

    def retweet(self, tweet_id: str) -> bool:
        """Retweet a tweet.

        Args:
            tweet_id: Tweet ID to retweet

        Returns:
            True on success, False on failure
        """
        user_id = self.credentials.get('X_ACCESS_TOKEN', '').split('-')[0]
        url = f"{self.base_url}/users/{user_id}/retweets"

        if not self._check_rate_limit("retweets"):
            return False

        headers = {
            "Authorization": self._get_oauth_header("POST", url),
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                url, json={"tweet_id": tweet_id}, headers=headers
            )
            self._update_rate_limit(response, "retweets")
            return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Error retweeting: {e}")
            return False

    def search_tweets(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search for recent tweets.

        Args:
            query: Search query
            max_results: Maximum results to return (1-100)

        Returns:
            List of tweet dicts
        """
        url = f"{self.base_url}/tweets/search/recent"
        params = {"query": query, "max_results": min(max_results, 100)}

        headers = {
            "Authorization": self._get_oauth_header(
                "GET", url + "?" + urllib.parse.urlencode(params)
            )
        }

        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                logger.error(f"Search failed: {response.status_code} - "
                           f"{response.text}")
                return []
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
            return []


# Convenience function for quick access
def get_x_client() -> XAPIClient:
    """Get a configured X API client.

    Returns:
        XAPIClient instance
    """
    return XAPIClient()
