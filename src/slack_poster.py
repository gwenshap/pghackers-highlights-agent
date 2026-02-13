# src/slack_poster.py
import logging
from datetime import date

from slack_sdk import WebClient

logger = logging.getLogger(__name__)


def format_slack_message(digest_body: str, today: date) -> str:
    """Format the digest for Slack."""
    date_str = today.strftime("%b %d, %Y")
    return f"*pgsql-hackers digest — {date_str}*\n\n{digest_body}"


def post_digest(client: WebClient, user_id: str, message: str) -> None:
    """Post the digest as a DM to the given user."""
    response = client.chat_postMessage(channel=user_id, text=message)
    if not response.get("ok"):
        raise RuntimeError(f"Slack API error: {response.get('error', 'unknown')}")
    logger.info(f"Digest posted to {user_id}")
