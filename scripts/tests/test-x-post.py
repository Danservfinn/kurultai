#!/usr/bin/env python3
"""
Test X/Twitter posting with OAuth 1.0a
"""
import os
import requests
from requests_oauthlib import OAuth1

# Load credentials
api_key = os.environ.get('X_API_KEY')
api_secret = os.environ.get('X_API_SECRET')
access_token = os.environ.get('X_ACCESS_TOKEN')
access_token_secret = os.environ.get('X_ACCESS_TOKEN_SECRET')

# Create OAuth1 auth
auth = OAuth1(
    api_key,
    api_secret,
    access_token,
    access_token_secret
)

# Test posting a tweet
tweet_text = "🚀 Parse Platform - AI-powered media analysis is now live! Testing autonomous posting. #AI #MediaLiteracy #Parse"

response = requests.post(
    "https://api.twitter.com/2/tweets",
    auth=auth,
    json={"text": tweet_text}
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 201:
    print("\n✅ SUCCESS! Tweet posted!")
    tweet_id = response.json()['data']['id']
    print(f"Tweet ID: {tweet_id}")
    print(f"View at: https://twitter.com/i/status/{tweet_id}")
else:
    print("\n❌ Failed to post")
    print(f"Error: {response.json()}")
