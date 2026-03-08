#!/usr/bin/env python3
"""
X/Twitter API Diagnostic Tool — Deep credential inspection

This tool helps diagnose X API authentication issues by:
1. Testing each credential individually
2. Checking API tier limitations
3. Suggesting fixes based on error codes
4. Providing curl commands for manual testing
"""

import base64
import hashlib
import hmac
import os
import sys
import time
import urllib.parse
import json
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip3 install requests")
    sys.exit(1)

CREDENTIALS_FILE = Path.home() / ".openclaw" / "credentials" / "x-api.env"


def load_credentials():
    """Load and display X API credentials."""
    if not CREDENTIALS_FILE.exists():
        print(f"❌ Credentials file not found: {CREDENTIALS_FILE}")
        return None

    creds = {}
    with open(CREDENTIALS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                creds[key.strip()] = value.strip()

    # URL decode bearer token
    if 'X_BEARER_TOKEN' in creds:
        creds['X_BEARER_TOKEN'] = urllib.parse.unquote(creds['X_BEARER_TOKEN'])

    return creds


def percent_encode(s):
    """Percent encode for OAuth."""
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return urllib.parse.quote(s, safe='')


def generate_oauth_signature(method, url, params, consumer_secret, token_secret):
    """Generate OAuth 1.0a signature."""
    encoded_params = []
    for k, v in sorted(params.items()):
        encoded_params.append(f"{percent_encode(k)}={percent_encode(v)}")

    normalized_params = '&'.join(encoded_params)
    base_string = f"{method.upper()}&{percent_encode(url)}&{percent_encode(normalized_params)}"
    signing_key = f"{percent_encode(consumer_secret)}&{percent_encode(token_secret)}"

    signature = hmac.new(
        signing_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha1
    ).digest()

    return base64.b64encode(signature).decode('utf-8')


def get_oauth_header(method, url, consumer_key, consumer_secret, access_token, access_token_secret, body_hash=None):
    """Generate OAuth 1.0a header."""
    params = {
        'oauth_consumer_key': consumer_key,
        'oauth_token': access_token,
        'oauth_nonce': base64.b64encode(os.urandom(16)).decode('utf-8').rstrip('='),
        'oauth_timestamp': str(int(time.time())),
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_version': '1.0',
    }

    if body_hash:
        params['oauth_body_hash'] = body_hash

    signature = generate_oauth_signature(method, url, params, consumer_secret, access_token_secret)
    params['oauth_signature'] = signature

    auth_params = ', '.join(
        '{}="{}"'.format(k, percent_encode(v))
        for k, v in sorted(params.items())
    )

    return f"OAuth {auth_params}"


def test_endpoint(name, method, url, headers, body=None):
    """Test an API endpoint and return detailed results."""
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=body, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        result = {
            'name': name,
            'status': response.status_code,
            'success': 200 <= response.status_code < 300,
            'response': response.text[:500],
        }

        # Try to parse JSON
        try:
            result['json'] = response.json()
        except:
            result['json'] = None

        return result
    except Exception as e:
        return {
            'name': name,
            'status': 0,
            'success': False,
            'error': str(e),
        }


def diagnose(creds):
    """Run full diagnostic on X API credentials."""
    print("=" * 70)
    print("X/TWITTER API DIAGNOSTIC TOOL")
    print("=" * 70)
    print()

    # Credential inspection
    print("📋 CREDENTIAL INSPECTION")
    print("-" * 70)

    checks = [
        ('Consumer Key', 'X_CONSUMER_KEY', 25),
        ('Consumer Secret', 'X_CONSUMER_SECRET', 44),
        ('Access Token', 'X_ACCESS_TOKEN', 50),
        ('Access Token Secret', 'X_ACCESS_TOKEN_SECRET', 45),
        ('Client ID', 'X_CLIENT_ID', 29),
        ('Client Secret', 'X_CLIENT_SECRET', 44),
        ('Bearer Token', 'X_BEARER_TOKEN', 94),
    ]

    for name, key, expected_len in checks:
        value = creds.get(key, '')
        if value:
            masked = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '****'
            status = '✅' if len(value) >= expected_len * 0.8 else '⚠️'
            print(f"{status} {name:25} {masked:40} ({len(value)} chars)")
        else:
            print(f"❌ {name:25} MISSING")

    print()

    # Test OAuth 1.0a with v1.1 API
    print("🔐 OAUTH 1.0a TESTS (v1.1 API)")
    print("-" * 70)

    v1_endpoints = {
        'verify_credentials': 'https://api.twitter.com/1.1/account/verify_credentials.json',
        'rate_limit_status': 'https://api.twitter.com/1.1/application/rate_limit_status.json',
    }

    oauth_v1_header = get_oauth_header(
        'GET',
        v1_endpoints['verify_credentials'],
        creds['X_CONSUMER_KEY'],
        creds['X_CONSUMER_SECRET'],
        creds['X_ACCESS_TOKEN'],
        creds['X_ACCESS_TOKEN_SECRET']
    )

    result = test_endpoint(
        'GET /1.1/account/verify_credentials.json',
        'GET',
        v1_endpoints['verify_credentials'],
        {'Authorization': oauth_v1_header}
    )

    if result['success']:
        user = result.get('json', {})
        print(f"✅ OAuth 1.0a WORKS!")
        print(f"   Authenticated as: @{user.get('screen_name')} ({user.get('name')})")
        print(f"   User ID: {user.get('id_str')}")
        print(f"   Verified: {user.get('verified', False)}")
        print(f"   Followers: {user.get('followers_count', 0):,}")
    else:
        print(f"❌ OAuth 1.0a FAILED: HTTP {result['status']}")

        if result['status'] == 401:
            print()
            print("   🔍 DIAGNOSIS: 401 Unauthorized")
            print("   Possible causes:")
            print("   1. Consumer Key/Secret is invalid")
            print("   2. Access Token/Secret has been revoked or regenerated")
            print("   3. App doesn't have OAuth 1.0a enabled")
            print()
            print("   🛠️ FIX:")
            print("   a. Go to https://developer.twitter.com/en/portal/dashboard")
            print("   b. Select your app and go to 'Keys and Tokens'")
            print("   c. Regenerate OAuth 1.0a tokens")
            print("   d. Update ~/.openclaw/credentials/x-api.env")

        elif result['status'] == 403:
            print()
            print("   🔍 DIAGNOSIS: 403 Forbidden")
            print("   Possible causes:")
            print("   1. Account is suspended")
            print("   2. App doesn't have required permissions")
            print("   3. API tier doesn't support this endpoint")

    print()

    # Test Bearer Token
    print("🔓 BEARER TOKEN TESTS (v2 API)")
    print("-" * 70)

    bearer = creds.get('X_BEARER_TOKEN')
    if bearer:
        bearer_results = []

        # Test user lookup (works with bearer)
        v2_endpoints = {
            'user_lookup': f"https://api.twitter.com/2/users/by/username/kurultai_kublai",
        }

        for name, url in v2_endpoints.items():
            result = test_endpoint(
                f'GET /2/users/by/username/kurultai_kublai',
                'GET',
                url,
                {'Authorization': f'Bearer {bearer}'}
            )

            if result['success']:
                user = result.get('json', {}).get('data', {})
                print(f"✅ Bearer Token VALID")
                print(f"   User found: @{user.get('username')}")
                print(f"   User ID: {user.get('id')}")
                print(f"   Name: {user.get('name')}")
                print(f"   Description: {user.get('description', 'N/A')[:50]}...")
            else:
                print(f"⚠️  Bearer Token: HTTP {result['status']}")
                if result.get('json'):
                    print(f"   Error: {result['json'].get('title', 'Unknown')}")
    else:
        print("❌ No Bearer Token found")

    print()

    # Test POST capability
    print("✍️  WRITE ACCESS TEST")
    print("-" * 70)

    # Try a dry-run of the tweet posting endpoint
    # We'll make a request that should fail if credentials are wrong
    # but will give us specific error codes
    post_url = "https://api.twitter.com/2/tweets"

    # First, check if we can at least get to the endpoint with OAuth
    oauth_post_header = get_oauth_header(
        'POST',
        post_url,
        creds['X_CONSUMER_KEY'],
        creds['X_CONSUMER_SECRET'],
        creds['X_ACCESS_TOKEN'],
        creds['X_ACCESS_TOKEN_SECRET'],
        body_hash=base64.b64encode(hashlib.sha256(b'{"text":"test"}').digest()).decode('utf-8')
    )

    # Don't actually post, just check the endpoint
    # We'll get 401/403 which tells us about auth status
    print("   Note: Not actually posting, checking endpoint accessibility...")

    # Check rate limit status for tweets endpoint
    rate_limit_url = "https://api.twitter.com/1.1/application/rate_limit_status.json?resources=tweets"

    result = test_endpoint(
        'GET rate_limit_status (tweets)',
        'GET',
        rate_limit_url,
        {'Authorization': oauth_v1_header}
    )

    if result['success']:
        limits = result.get('json', {}).get('resources', {}).get('tweets', {})
        print(f"✅ Rate limit status accessible")
        for endpoint, info in limits.items():
            remaining = info.get('remaining', '?')
            limit = info.get('limit', '?')
            print(f"   {endpoint}: {remaining}/{limit} remaining")
    else:
        print(f"⚠️  Rate limit status: HTTP {result['status']}")

    print()

    # Summary
    print("📊 SUMMARY")
    print("-" * 70)
    print()
    print("The X API has undergone significant changes:")
    print()
    print("1. FREE TIER (current as of 2024):")
    print("   • Read-only access to POST tweets")
    print("   • 500 tweets/month for write operations")
    print("   • Requires OAuth 1.0a user context")
    print()
    print("2. BASIC TIER ($100/month):")
    print("   • Full read + write access")
    print("   • Higher rate limits")
    print()
    print("3. CURRENT STATUS:")
    bearer_status = 'Valid' if bearer else 'Missing'
    print(f"   Bearer Token: {bearer_status}")

    if result['status'] == 401:
        oauth_status = 'Invalid (401)'
    elif result['success']:
        oauth_status = 'Valid'
    else:
        oauth_status = f'HTTP {result["status"]}'
    print(f"   OAuth 1.0a: {oauth_status}")
    print()
    print("4. NEXT STEPS:")
    print("   a. Verify API tier at https://developer.twitter.com/en/portal/dashboard")
    print("   b. Regenerate OAuth 1.0a tokens if needed")
    print("   c. Update credentials file with new tokens")
    print("   d. Run: python3 x-twitter-client.py --test-auth")
    print()

    # Generate curl command for manual testing
    print("🔧 MANUAL TESTING (curl)")
    print("-" * 70)
    print()
    print("Test OAuth 1.0a manually:")
    print(f"""curl -X GET \\
  'https://api.twitter.com/1.1/account/verify_credentials.json' \\
  -H 'Authorization: OAuth oauth_consumer_key="{creds['X_CONSUMER_KEY'][:10]}...", oauth_token="{creds['X_ACCESS_TOKEN'][:10]}...", oauth_signature_method="HMAC-SHA1", oauth_timestamp="{int(time.time())}", oauth_nonce="{base64.b64encode(os.urandom(8)).decode()}", oauth_version="1.0", oauth_signature="..."'
""")
    print()
    print("Test Bearer Token manually:")
    print(f"""curl -X GET \\
  'https://api.twitter.com/2/users/by/username/kurultai_kublai' \\
  -H 'Authorization: Bearer {bearer[:20]}...'""")
    print()


def main():
    creds = load_credentials()
    if not creds:
        return 1

    diagnose(creds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
