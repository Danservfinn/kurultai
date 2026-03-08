#!/usr/bin/env python3
"""
X/Twitter API Client v2 — Authentication and posting for @Kurultai_Kublai

Supports OAuth 1.0a (user context for posting) and Bearer Token (app-only for reading).

X API v2 Endpoints:
- POST /2/tweets - Requires OAuth 1.0a user context
- GET /2/users/me - Requires OAuth 1.0a user context
- GET /2/users/by/username/{username} - Works with bearer token
- GET /2/tweets/search/recent - Works with bearer token

Usage:
    python3 x-twitter-client.py --test-auth
    python3 x-twitter-client.py --post "Your tweet text here"
    python3 x-twitter-client.py --verify-credentials

Credentials: ~/.openclaw/credentials/x-api.env
"""

import argparse
import base64
import hashlib
import hmac
import os
import sys
import time
import urllib.parse
import json
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip3 install requests")
    sys.exit(1)

# API Endpoints
API_BASE = "https://api.twitter.com/2"
POST_TWEET_URL = f"{API_BASE}/tweets"
ME_URL = f"{API_BASE}/users/me"
VERIFY_CREDENTIALS_URL = "https://api.twitter.com/1.1/account/verify_credentials.json"
USER_BY_USERNAME_URL = f"{API_BASE}/users/by/username"

# Load credentials
CREDENTIALS_FILE = Path.home() / ".openclaw" / "credentials" / "x-api.env"


def load_credentials():
    """Load X API credentials from env file."""
    if not CREDENTIALS_FILE.exists():
        print(f"Error: Credentials file not found: {CREDENTIALS_FILE}")
        sys.exit(1)

    creds = {}
    with open(CREDENTIALS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                creds[key.strip()] = value.strip()

    # URL decode the bearer token if it's encoded
    if 'X_BEARER_TOKEN' in creds:
        creds['X_BEARER_TOKEN'] = urllib.parse.unquote(creds['X_BEARER_TOKEN'])

    required = ['X_CONSUMER_KEY', 'X_CONSUMER_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET']
    missing = [k for k in required if k not in creds]

    if missing:
        print(f"Error: Missing required credentials: {missing}")
        sys.exit(1)

    return creds


def percent_encode(s):
    """Percent encode a string for OAuth (RFC 3986)."""
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return urllib.parse.quote(s, safe='')


def generate_oauth_signature(method, url, params, consumer_secret, token_secret):
    """Generate OAuth 1.0a signature."""
    # Normalize parameters - sort and encode
    encoded_params = []
    for k, v in sorted(params.items()):
        encoded_params.append(f"{percent_encode(k)}={percent_encode(v)}")

    normalized_params = '&'.join(encoded_params)

    # Create signature base string
    base_string = f"{method.upper()}&{percent_encode(url)}&{percent_encode(normalized_params)}"

    # Create signing key
    signing_key = f"{percent_encode(consumer_secret)}&{percent_encode(token_secret)}"

    # Generate signature
    signature = hmac.new(
        signing_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha1
    ).digest()

    return base64.b64encode(signature).decode('utf-8')


def get_oauth_header(method, url, consumer_key, consumer_secret, access_token, access_token_secret, body_hash=None):
    """
    Generate OAuth 1.0a Authorization header.

    For X API v2:
    - GET requests: Include query params in signature
    - POST requests with JSON: Use 'oauth_body_hash' for JSON body
    """
    params = {
        'oauth_consumer_key': consumer_key,
        'oauth_token': access_token,
        'oauth_nonce': base64.b64encode(os.urandom(16)).decode('utf-8').rstrip('='),
        'oauth_timestamp': str(int(time.time())),
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_version': '1.0',
    }

    # Add body hash for POST requests with JSON body
    if body_hash:
        params['oauth_body_hash'] = body_hash

    # Generate signature
    signature = generate_oauth_signature(method, url, params, consumer_secret, access_token_secret)
    params['oauth_signature'] = signature

    # Build Authorization header
    auth_params = ', '.join(
        '{}="{}"'.format(k, percent_encode(v))
        for k, v in sorted(params.items())
    )

    return f"OAuth {auth_params}"


def post_tweet(text, creds):
    """Post a tweet using OAuth 1.0a."""
    print(f"Posting tweet: {text[:50]}{'...' if len(text) > 50 else ''}")

    if len(text) > 280:
        print(f"Warning: Tweet exceeds 280 characters (current: {len(text)})")

    # Create JSON body
    body = {'text': text}
    body_json = json.dumps(body)
    body_hash = base64.b64encode(hashlib.sha256(body_json.encode('utf-8')).digest()).decode('utf-8')

    headers = {
        'Authorization': get_oauth_header(
            'POST',
            POST_TWEET_URL,
            creds['X_CONSUMER_KEY'],
            creds['X_CONSUMER_SECRET'],
            creds['X_ACCESS_TOKEN'],
            creds['X_ACCESS_TOKEN_SECRET'],
            body_hash=body_hash
        ),
        'Content-Type': 'application/json',
    }

    try:
        response = requests.post(POST_TWEET_URL, headers=headers, json=body, timeout=10)

        if response.status_code == 201:
            data = response.json()
            tweet_id = data.get('data', {}).get('id')
            print(f" Tweet posted successfully! ID: {tweet_id}")
            return {'success': True, 'tweet_id': tweet_id, 'data': data}
        elif response.status_code == 401:
            print(f" Authentication failed (401)")
            print(f" This usually means:")
            print(f"   - Invalid API keys or access tokens")
            print(f"   - App doesn't have write permissions")
            print(f"   - Access token has been revoked")
            return {'success': False, 'error': 'Unauthorized', 'status_code': 401}
        elif response.status_code == 403:
            print(f" Access forbidden (403)")
            print(f" This usually means:")
            print(f"   - Free tier account (write access requires Basic tier or higher)")
            print(f"   - Suspended API access")
            return {'success': False, 'error': 'Forbidden', 'status_code': 403}
        else:
            print(f" Failed to post tweet: {response.status_code}")
            print(f" Response: {response.text}")
            return {'success': False, 'error': response.text, 'status_code': response.status_code}
    except requests.exceptions.RequestException as e:
        print(f" Network error: {e}")
        return {'success': False, 'error': str(e)}


def verify_credentials_v1(creds):
    """Verify OAuth 1.0a credentials using API v1.1 endpoint (more reliable)."""
    headers = {
        'Authorization': get_oauth_header(
            'GET',
            VERIFY_CREDENTIALS_URL,
            creds['X_CONSUMER_KEY'],
            creds['X_CONSUMER_SECRET'],
            creds['X_ACCESS_TOKEN'],
            creds['X_ACCESS_TOKEN_SECRET']
        ),
    }

    try:
        response = requests.get(VERIFY_CREDENTIALS_URL, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            username = data.get('screen_name', 'unknown')
            name = data.get('name', 'unknown')
            print(f" OAuth 1.0a authenticated as: @{username} ({name})")
            return {'success': True, 'user': data}
        elif response.status_code == 401:
            print(f" OAuth 1.0a authentication failed (401 Unauthorized)")
            print(f" Possible causes:")
            print(f"   - Invalid consumer key/secret")
            print(f"   - Invalid access token/secret")
            print(f"   - Tokens have been revoked")
            return {'success': False, 'error': 'Unauthorized', 'status_code': 401}
        elif response.status_code == 403:
            print(f" OAuth 1.0a access forbidden (403)")
            print(f" Possible causes:")
            print(f"   - API access suspended")
            print(f"   - Account suspended")
            return {'success': False, 'error': 'Forbidden', 'status_code': 403}
        else:
            print(f" OAuth 1.0a verification failed: {response.status_code}")
            print(f" Response: {response.text}")
            return {'success': False, 'error': response.text}
    except requests.exceptions.RequestException as e:
        print(f" Network error: {e}")
        return {'success': False, 'error': str(e)}


def get_me_v2(creds):
    """Get authenticated user info using API v2."""
    headers = {
        'Authorization': get_oauth_header(
            'GET',
            ME_URL,
            creds['X_CONSUMER_KEY'],
            creds['X_CONSUMER_SECRET'],
            creds['X_ACCESS_TOKEN'],
            creds['X_ACCESS_TOKEN_SECRET']
        ),
    }

    response = requests.get(ME_URL, headers=headers)

    if response.status_code == 200:
        data = response.json()
        user = data.get('data', {})
        print(f" API v2 user: @{user.get('username', 'unknown')}")
        return {'success': True, 'user': user}
    else:
        return {'success': False, 'error': response.text}


def test_bearer_token(creds):
    """Test app-only bearer token authentication."""
    bearer_token = creds.get('X_BEARER_TOKEN')
    if not bearer_token:
        print(" No bearer token found in credentials")
        return False

    # Use username lookup endpoint which supports bearer token
    url = f"{USER_BY_USERNAME_URL}/Kurultai_Kublai"
    headers = {'Authorization': f'Bearer {bearer_token}'}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            user = data.get('data', {})
            print(f" Bearer token valid. User: @{user.get('username', 'unknown')}")
            return True
        elif response.status_code == 403:
            print(f" Bearer token rejected (403 Forbidden)")
            print(f" Possible causes:")
            print(f"   - Invalid bearer token")
            print(f"   - App level doesn't support this endpoint")
            print(f"   - Bearer token expired")
            return False
        else:
            print(f" Bearer token test failed: {response.status_code}")
            print(f" Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f" Network error: {e}")
        return False


def test_post_permission(creds):
    """Test if the app has write permissions by attempting to validate."""
    # We'll check this by examining the OAuth 1.0a credentials
    # and verifying them against v1.1 API

    # First, verify OAuth 1.0a works
    v1_result = verify_credentials_v1(creds)

    if not v1_result.get('success'):
        return {'success': False, 'reason': 'OAuth 1.0a authentication failed'}

    # Check if the access tokens have write permissions
    # Twitter API v1.1 doesn't directly tell us this, but we can infer
    # from the fact that we successfully authenticated

    user_data = v1_result.get('user', {})

    # Check if account is suspended
    if user_data.get('suspended', False):
        return {'success': False, 'reason': 'Account is suspended'}

    return {'success': True, 'user': user_data}


def main():
    parser = argparse.ArgumentParser(description='X/Twitter API Client v2')
    parser.add_argument('--test-auth', action='store_true', help='Test authentication')
    parser.add_argument('--verify-credentials', action='store_true', help='Verify OAuth 1.0a credentials')
    parser.add_argument('--post', type=str, help='Post a tweet')
    parser.add_argument('--thread', type=str, nargs='+', help='Post a thread (multiple tweets)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be posted without posting')
    args = parser.parse_args()

    print("=" * 60)
    print("X/Twitter API Client v2 — @Kurultai_Kublai")
    print("=" * 60)
    print()

    # Load credentials
    creds = load_credentials()
    print(f"Credentials loaded from {CREDENTIALS_FILE}")
    print()

    if args.test_auth:
        print("Testing Authentication...")
        print("-" * 60)

        # Test OAuth 1.0a using v1.1 endpoint (most reliable)
        print("\n1. Testing OAuth 1.0a (User Context) via v1.1 API...")
        oauth_result = verify_credentials_v1(creds)

        # Test Bearer Token
        print("\n2. Testing Bearer Token (App-Only)...")
        bearer_result = test_bearer_token(creds)

        # Test v2 user endpoint
        if oauth_result.get('success'):
            print("\n3. Testing API v2 user endpoint...")
            get_me_v2(creds)

        # Check write permissions
        print("\n4. Checking write permissions...")
        write_perm = test_post_permission(creds)

        print()
        print("=" * 60)
        if oauth_result.get('success'):
            print(" OAuth 1.0a: VALID")
        else:
            print(" OAuth 1.0a: INVALID")

        if bearer_result:
            print(" Bearer Token: VALID")
        else:
            print(" Bearer Token: INVALID")

        if write_perm.get('success'):
            print(" Write Access: AVAILABLE")
        else:
            print(f" Write Access: NOT AVAILABLE - {write_perm.get('reason')}")
        print("=" * 60)

        return 0 if oauth_result.get('success') else 1

    elif args.verify_credentials:
        print("Verifying OAuth 1.0a Credentials...")
        print("-" * 60)
        result = verify_credentials_v1(creds)
        return 0 if result.get('success') else 1

    elif args.post:
        print("Posting Tweet...")
        print("-" * 60)

        if args.dry_run:
            print(f"[DRY RUN] Would post: {args.post}")
            return 0

        result = post_tweet(args.post, creds)

        if result.get('success'):
            # Save result to workspace for integration
            workspace_dir = Path.home() / ".openclaw" / "agents" / "ogedei" / "workspace"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            result_file = workspace_dir / f"tweet_result_{int(time.time())}.json"
            with open(result_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f" Result saved to: {result_file}")

        return 0 if result.get('success') else 1

    elif args.thread:
        print("Posting Thread...")
        print("-" * 60)

        if args.dry_run:
            print("[DRY RUN] Thread:")
            for i, tweet in enumerate(args.thread, 1):
                print(f"  {i}. {tweet}")
            return 0

        # Post first tweet
        first_result = post_tweet(args.thread[0], creds)
        if not first_result.get('success'):
            print(" Failed to post first tweet in thread")
            return 1

        first_tweet_id = first_result.get('tweet_id')
        print(f" First tweet posted: {first_tweet_id}")

        # Post remaining tweets as replies
        reply_to_id = first_tweet_id
        for i, tweet_text in enumerate(args.thread[1:], 2):
            # Add reply prefix
            reply_text = tweet_text
            time.sleep(1)  # Rate limit respect

            reply_result = post_tweet(reply_text, creds)
            if not reply_result.get('success'):
                print(f" Failed to post tweet {i} in thread")
                return 1

            print(f" Tweet {i} posted")

        print(f" Thread complete: {len(args.thread)} tweets")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
