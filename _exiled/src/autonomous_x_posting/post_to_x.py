import time
from typing import List
from requests_oauthlib import OAuth1Session
from config import X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET, logger

def create_twitter_session() -> OAuth1Session:
    """Creates an authenticated OAuth 1.0a session for the X API."""
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
        logger.error("Missing X API credentials. Please check .x_api_credentials file.")
        raise ValueError("Missing X API credentials")
        
    return OAuth1Session(
        X_API_KEY,
        client_secret=X_API_SECRET,
        resource_owner_key=X_ACCESS_TOKEN,
        resource_owner_secret=X_ACCESS_TOKEN_SECRET
    )

def post_thread(tweets: List[str]) -> bool:
    """Posts a list of strings as a threaded tweet sequence to X."""
    if not tweets:
        logger.warning("Empty thread provided. Nothing to post.")
        return False
        
    try:
        session = create_twitter_session()
        url = "https://api.twitter.com/2/tweets"
        
        previous_tweet_id = None
        
        for i, tweet in enumerate(tweets):
            payload = {"text": tweet}
            if previous_tweet_id:
                payload["reply"] = {"in_reply_to_tweet_id": previous_tweet_id}
                
            response = session.post(url, json=payload)
            response.raise_for_status()
            
            response_json = response.json()
            previous_tweet_id = response_json["data"]["id"]
            logger.info(f"Successfully posted tweet {i+1}/{len(tweets)}: {previous_tweet_id}")
            
            # Rate limiting / polite pause
            time.sleep(2)
            
        logger.info("Thread posted successfully.")
        return True
        
    except Exception as e:
        logger.error(f"Error posting thread to X: {e}")
        return False
