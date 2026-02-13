# tests/test_summarizer.py
import json
from unittest.mock import MagicMock, patch
from datetime import date
from src.summarizer import build_selection_prompt, build_summary_prompt, parse_selection_response
from src.scraper import ThreadInfo


def _make_thread(subject, author, d=date(2026, 2, 13)):
    return ThreadInfo(
        subject=subject, author=author, time="10:00",
        date=d, message_id_path="/message-id/test",
        message_url="https://www.postgresql.org/message-id/test",
    )


def test_build_selection_prompt_includes_all_subjects():
    threads = [
        _make_thread("Re: B-tree optimization", "Alice"),
        _make_thread("[PATCH] Fix WAL summary", "Bob"),
        _make_thread("Re: B-tree optimization", "Charlie"),
    ]
    prompt = build_selection_prompt(threads, previous_digests=[])
    assert "B-tree optimization" in prompt
    assert "Fix WAL summary" in prompt
    assert "Alice" in prompt
    assert "Bob" in prompt


def test_build_selection_prompt_includes_previous_digests():
    threads = [_make_thread("Some thread", "Alice")]
    prompt = build_selection_prompt(threads, previous_digests=["Yesterday: B-tree stuff"])
    assert "B-tree stuff" in prompt


def test_parse_selection_response():
    response = json.dumps({"selected_indices": [0, 3, 7]})
    result = parse_selection_response(response)
    assert result == [0, 3, 7]


def test_build_summary_prompt_includes_content():
    threads = [_make_thread("B-tree proposal", "Alice")]
    contents = ["Hello, this is a proposal for a new B-tree access method."]
    prompt = build_summary_prompt(threads, contents, previous_digests=[])
    assert "B-tree proposal" in prompt
    assert "new B-tree access method" in prompt
