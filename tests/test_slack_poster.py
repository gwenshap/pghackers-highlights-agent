# tests/test_slack_poster.py
from unittest.mock import MagicMock
from datetime import date
from src.slack_poster import format_slack_message, post_digest

SAMPLE_DIGEST = """1. **B-tree merge access method** — A proposal for streaming sorted rows. https://www.postgresql.org/message-id/test1

2. **EXPLAIN ANALYZE timing** — Discussion on rdtsc usage. https://www.postgresql.org/message-id/test2

_Based on 47 messages from the last 24h_"""


def test_format_slack_message():
    msg = format_slack_message(SAMPLE_DIGEST, date(2026, 2, 13))
    assert "pgsql-hackers digest" in msg
    assert "Feb 13, 2026" in msg
    assert "B-tree merge" in msg


def test_post_digest_calls_slack_api():
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = MagicMock(data={"ok": True})
    post_digest(mock_client, "U030NAS0AJ1", "test message")
    mock_client.chat_postMessage.assert_called_once()
    call_kwargs = mock_client.chat_postMessage.call_args[1]
    assert call_kwargs["channel"] == "U030NAS0AJ1"
    assert call_kwargs["text"] == "test message"
