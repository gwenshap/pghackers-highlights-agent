# src/main.py
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import anthropic
from slack_sdk import WebClient

from src.scraper import scrape_recent_threads
from src.slack_poster import format_slack_message, post_digest
from src.summarizer import run_two_pass_summarization

logger = logging.getLogger(__name__)

SLACK_USER_ID = "U030NAS0AJ1"
DIGESTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "digests")


def load_previous_digests(digests_dir: str, today: date, days: int = 3) -> list[str]:
    """Load the last N days of digest files for de-duplication context."""
    digests = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        path = os.path.join(digests_dir, f"{d.isoformat()}.md")
        if os.path.exists(path):
            with open(path) as f:
                digests.append(f.read())
    return digests


def save_digest(digests_dir: str, today: date, content: str) -> str:
    """Save the digest to a markdown file. Returns the file path."""
    os.makedirs(digests_dir, exist_ok=True)
    path = os.path.join(digests_dir, f"{today.isoformat()}.md")
    with open(path, "w") as f:
        f.write(content)
    logger.info(f"Digest saved to {path}")
    return path


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    slack_token = os.environ.get("SLACK_BOT_TOKEN")

    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)
    if not slack_token:
        logger.error("SLACK_BOT_TOKEN not set")
        sys.exit(1)

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Step 1: Scrape
    logger.info(f"Scraping pgsql-hackers since {yesterday}...")
    try:
        threads = scrape_recent_threads(yesterday)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        sys.exit(1)

    if not threads:
        logger.info("No new messages. Skipping digest.")
        sys.exit(0)

    logger.info(f"Found {len(threads)} messages.")

    # Step 2: Summarize
    claude_client = anthropic.Anthropic(api_key=anthropic_key)
    previous_digests = load_previous_digests(DIGESTS_DIR, today)

    try:
        digest_body = run_two_pass_summarization(claude_client, threads, previous_digests)
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        sys.exit(1)

    if not digest_body:
        logger.info("No notable threads selected. Skipping digest.")
        sys.exit(0)

    # Step 3: Save digest
    message = format_slack_message(digest_body, today)
    save_digest(DIGESTS_DIR, today, message)

    # Step 4: Post to Slack
    slack_client = WebClient(token=slack_token)
    try:
        post_digest(slack_client, SLACK_USER_ID, message)
    except Exception as e:
        logger.error(f"Slack posting failed: {e}")
        sys.exit(1)

    logger.info("Done!")


if __name__ == "__main__":
    main()
