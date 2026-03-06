import time
import random
from apscheduler.schedulers.background import BackgroundScheduler
from config import logger
from fetch_parse_analysis import fetch_latest_articles, get_parse_analysis
from generate_thread import generate_thread_from_analysis, generate_capabilities_thread
from post_to_x import post_thread

# In-memory store to prevent re-posting the same article URL
processed_urls = set()

def job_post_article_analysis():
    """Scheduled job to fetch an article, request analysis, and post a thread."""
    logger.info("Starting article analysis job...")
    articles = fetch_latest_articles(limit=10)
    
    # Filter for unprocessed articles
    unprocessed_articles = [a for a in articles if a['link'] not in processed_urls]
    
    if not unprocessed_articles:
        logger.info("No new articles to process at this time.")
        return
        
    # Pick a random fresh article
    article = random.choice(unprocessed_articles)
    logger.info(f"Selected article for analysis: {article['title']}")
    
    analysis = get_parse_analysis(article['link'])
    
    if analysis:
        thread = generate_thread_from_analysis(analysis, article)
        success = post_thread(thread)
        if success:
            processed_urls.add(article['link'])
            logger.info(f"Successfully posted thread for: {article['link']}")
        else:
            logger.error("Thread posting failed.")
    else:
        logger.error("Failed to receive valid analysis from Parse Platform.")

def job_post_capabilities():
    """Scheduled job to post about Agent Parse capabilities."""
    logger.info("Starting capabilities promotional thread job...")
    thread = generate_capabilities_thread()
    post_thread(thread)

def run_scheduler():
    """Initializes and runs the APScheduler loop."""
    logger.info("Initializing X Posting Scheduler...")
    
    scheduler = BackgroundScheduler()
    
    # Schedule article analyses 3 times a day (9 AM, 2 PM, 7 PM EST)
    scheduler.add_job(job_post_article_analysis, 'cron', hour='14,19,0', minute=0)
    
    # Schedule capability spotlight once every 2 days at 12:00 PM EST
    scheduler.add_job(job_post_capabilities, 'cron', day='*/2', hour=17, minute=0)
    
    scheduler.start()
    logger.info("Scheduler successfully started. Press Ctrl+C to exit.")
    
    try:
        # Keep the main process running
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler shut down successfully.")

if __name__ == "__main__":
    run_scheduler()
