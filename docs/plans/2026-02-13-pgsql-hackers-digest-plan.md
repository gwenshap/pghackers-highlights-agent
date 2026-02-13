# pgsql-hackers Daily Digest Agent — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated agent that scrapes the PostgreSQL hackers mailing list daily, uses Claude to curate the most interesting threads, and sends a digest via Slack DM.

**Architecture:** A Python script orchestrates three stages: (1) scrape the pgsql-hackers web archive for the last 24h of messages, (2) two-pass Claude summarization to pick and describe the top ~10 threads, (3) post the formatted digest to Slack and commit it to the repo. Runs daily via GitHub Actions cron.

**Tech Stack:** Python 3.12, requests, beautifulsoup4, anthropic SDK, slack_sdk, GitHub Actions.

**Design doc:** `docs/plans/2026-02-13-pgsql-hackers-digest-design.md`

---

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `digests/.gitkeep`

**Step 1: Create requirements.txt**

```
requests>=2.31.0
beautifulsoup4>=4.12.0
anthropic>=0.43.0
slack_sdk>=3.27.0
pytest>=8.0.0
```

**Step 2: Create directory structure**

```bash
mkdir -p src tests digests
touch src/__init__.py tests/__init__.py digests/.gitkeep
```

**Step 3: Install dependencies**

Run: `pip install -r requirements.txt`

**Step 4: Commit**

```bash
git add requirements.txt src/__init__.py tests/__init__.py digests/.gitkeep
git commit -m "chore: initial project setup with dependencies"
```

---

### Task 2: Scraper — Parse Archive Page

The archive page at `https://www.postgresql.org/list/pgsql-hackers/since/YYYYMMDD0000` contains:
- `<h2>` tags with dates like `Feb. 1, 2026`
- `<table class="thread-list">` per day with rows: `<th><a href="/message-id/{id}">Subject</a></th><td>Author</td><td>HH:MM</td>`

**Files:**
- Create: `tests/test_scraper.py`
- Create: `src/scraper.py`

**Step 1: Write the failing tests**

```python
# tests/test_scraper.py
from datetime import date
from src.scraper import parse_archive_page, fetch_message_content, ThreadInfo

SAMPLE_HTML = """
<h2>Feb. 1, 2026</h2>
<table class="table table-striped table-sm thread-list">
  <thead><tr><th>Thread</th><th>Author</th><th>Time</th></tr></thead>
  <tbody>
    <tr>
      <th scope="row">
        <a href="/message-id/abc123%40mail.gmail.com">Re: Reduce timing overhead of EXPLAIN ANALYZE</a>
      </th>
      <td>Lukas Fittl</td>
      <td>03:14</td>
    </tr>
    <tr>
      <th scope="row">
        <a href="/message-id/def456%40outlook.com">New access method for b-tree. &#x1f4ce;</a>
      </th>
      <td>Alexandre Felipe</td>
      <td>10:02</td>
    </tr>
  </tbody>
</table>
<h2>Feb. 2, 2026</h2>
<table class="table table-striped table-sm thread-list">
  <thead><tr><th>Thread</th><th>Author</th><th>Time</th></tr></thead>
  <tbody>
    <tr>
      <th scope="row">
        <a href="/message-id/ghi789%40qq.com">[PATCH] Fix error message in RemoveWalSummary</a>
      </th>
      <td>zengman</td>
      <td>14:43</td>
    </tr>
  </tbody>
</table>
"""

SAMPLE_MESSAGE_HTML = """
<div class="message-content"><p>Hello Hackers,</p>
<p>Please check this out, it is an access method.</p></div>
"""


def test_parse_archive_page_extracts_all_threads():
    threads = parse_archive_page(SAMPLE_HTML)
    assert len(threads) == 3


def test_parse_archive_page_extracts_fields():
    threads = parse_archive_page(SAMPLE_HTML)
    t = threads[0]
    assert t.subject == "Re: Reduce timing overhead of EXPLAIN ANALYZE"
    assert t.author == "Lukas Fittl"
    assert t.time == "03:14"
    assert t.date == date(2026, 2, 1)
    assert t.message_url == "https://www.postgresql.org/message-id/abc123%40mail.gmail.com"


def test_parse_archive_page_strips_attachment_emoji():
    threads = parse_archive_page(SAMPLE_HTML)
    t = threads[1]
    assert t.subject == "New access method for b-tree."
    assert "\U0001f4ce" not in t.subject


def test_parse_archive_page_multiple_dates():
    threads = parse_archive_page(SAMPLE_HTML)
    assert threads[0].date == date(2026, 2, 1)
    assert threads[2].date == date(2026, 2, 2)


def test_parse_message_content():
    content = fetch_message_content(SAMPLE_MESSAGE_HTML, parse_only=True)
    assert "Hello Hackers" in content
    assert "access method" in content
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scraper.py -v`
Expected: FAIL with `ImportError` (module doesn't exist yet)

**Step 3: Write the implementation**

```python
# src/scraper.py
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.postgresql.org"


@dataclass
class ThreadInfo:
    subject: str
    author: str
    time: str
    date: date
    message_id_path: str
    message_url: str


def parse_archive_page(html: str) -> list[ThreadInfo]:
    """Parse the pgsql-hackers archive HTML and extract thread info."""
    soup = BeautifulSoup(html, "html.parser")
    threads = []
    current_date = None

    for element in soup.find_all(["h2", "tr"]):
        if element.name == "h2":
            text = element.get_text(strip=True)
            parsed = _parse_date_header(text)
            if parsed:
                current_date = parsed
            continue

        if current_date is None:
            continue

        th = element.find("th", scope="row")
        if not th:
            continue

        link = th.find("a")
        if not link:
            continue

        href = link.get("href", "")
        if "/message-id/" not in href:
            continue

        subject = link.get_text(strip=True)
        # Strip attachment emoji (paperclip U+1F4CE)
        subject = subject.replace("\U0001f4ce", "").strip()

        tds = element.find_all("td")
        author = tds[0].get_text(strip=True) if len(tds) > 0 else ""
        time_str = tds[1].get_text(strip=True) if len(tds) > 1 else ""

        threads.append(ThreadInfo(
            subject=subject,
            author=author,
            time=time_str,
            date=current_date,
            message_id_path=href,
            message_url=f"{BASE_URL}{href}",
        ))

    return threads


def _parse_date_header(text: str) -> date | None:
    """Parse date headers like 'Feb. 1, 2026' or 'February 1, 2026'."""
    # Normalize abbreviated months with periods
    normalized = text.replace(".", "")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def fetch_archive_page(target_date: date) -> str:
    """Fetch the archive page showing messages since the given date."""
    date_str = target_date.strftime("%Y%m%d0000")
    url = f"{BASE_URL}/list/pgsql-hackers/since/{date_str}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_message_content(html_or_url: str, parse_only: bool = False) -> str:
    """Fetch and extract the text content of an individual message.

    If parse_only=True, treat html_or_url as raw HTML (for testing).
    Otherwise, treat it as a URL to fetch.
    """
    if parse_only:
        html = html_or_url
    else:
        resp = requests.get(html_or_url, timeout=30)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find("div", class_="message-content")
    if not content_div:
        return ""
    return content_div.get_text(separator="\n", strip=True)


def scrape_recent_threads(since_date: date) -> list[ThreadInfo]:
    """Scrape all threads since the given date."""
    html = fetch_archive_page(since_date)
    threads = parse_archive_page(html)
    return [t for t in threads if t.date >= since_date]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scraper.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/scraper.py tests/test_scraper.py
git commit -m "feat: add scraper to parse pgsql-hackers archive pages"
```

---

### Task 3: Summarizer — Two-Pass Claude Summarization

**Files:**
- Create: `tests/test_summarizer.py`
- Create: `src/summarizer.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

```python
# src/summarizer.py
import json
import logging

import anthropic

from src.scraper import ThreadInfo, fetch_message_content

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"
MAX_CONTENT_CHARS = 2000


def build_selection_prompt(threads: list[ThreadInfo], previous_digests: list[str]) -> str:
    """Build the Pass 1 prompt: select the most interesting threads."""
    thread_list = "\n".join(
        f"[{i}] \"{t.subject}\" — {t.author} ({t.date} {t.time})"
        for i, t in enumerate(threads)
    )

    previous = ""
    if previous_digests:
        previous = (
            "\n\n## Recently Highlighted Threads\n"
            "These threads were covered in recent digests. Only select them again "
            "if there is significant new development.\n\n"
            + "\n---\n".join(previous_digests)
        )

    return f"""You are an expert PostgreSQL developer reviewing the pgsql-hackers mailing list.

Below is a list of messages posted in the last 24 hours. Select the ~10 most interesting
or notable threads for a daily digest. Prioritize:
- New feature proposals and significant patches
- Important design discussions and architectural debates
- Performance improvements
- Release-related discussions
- Bug fixes for serious issues

De-prioritize:
- Minor typo/doc fixes
- Routine CI/build farm chatter
- Duplicate replies in the same thread (pick the most relevant one per thread)
{previous}

## Today's Messages

{thread_list}

Respond with ONLY a JSON object: {{"selected_indices": [list of integer indices]}}"""


def parse_selection_response(response_text: str) -> list[int]:
    """Parse Claude's Pass 1 response into a list of thread indices."""
    # Handle markdown code fences
    text = response_text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[:-3]
    data = json.loads(text.strip())
    return data["selected_indices"]


def build_summary_prompt(
    threads: list[ThreadInfo],
    contents: list[str],
    previous_digests: list[str],
) -> str:
    """Build the Pass 2 prompt: summarize selected threads."""
    entries = []
    for thread, content in zip(threads, contents):
        entries.append(
            f"### {thread.subject}\n"
            f"**Author:** {thread.author} | **Date:** {thread.date} {thread.time}\n"
            f"**URL:** {thread.message_url}\n\n"
            f"{content[:MAX_CONTENT_CHARS]}"
        )

    previous = ""
    if previous_digests:
        previous = (
            "\n\n## Context: Recent Digests\n"
            "Avoid repeating the same points. Focus on what's new.\n\n"
            + "\n---\n".join(previous_digests[-3:])
        )

    return f"""You are writing a daily digest of the PostgreSQL hackers mailing list.

For each thread below, write a concise 1-3 sentence summary explaining what it's about
and why it's interesting to PostgreSQL developers. Keep it accessible but technically accurate.

Format your response as a numbered markdown list. Each item should have:
- A bold short title
- The summary text
- The URL in [link] format

Example:
1. **B-tree merge access method** — Alexandre Felipe proposes a new access method that can stream sorted rows directly from disk for multi-column index scans, reducing I/O from O(N*Nx) to O(M+Nx). <URL>
{previous}

## Selected Threads

{chr(10).join(entries)}

Write the digest now. End with a line: _Based on N messages from the last 24h_ where N is the total count."""


def select_top_threads(
    client: anthropic.Anthropic,
    threads: list[ThreadInfo],
    previous_digests: list[str],
) -> list[int]:
    """Pass 1: Ask Claude to select the most interesting threads."""
    prompt = build_selection_prompt(threads, previous_digests)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_selection_response(response.content[0].text)


def summarize_threads(
    client: anthropic.Anthropic,
    threads: list[ThreadInfo],
    contents: list[str],
    previous_digests: list[str],
    total_message_count: int,
) -> str:
    """Pass 2: Ask Claude to write summaries of the selected threads."""
    prompt = build_summary_prompt(threads, contents, previous_digests)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def run_two_pass_summarization(
    client: anthropic.Anthropic,
    threads: list[ThreadInfo],
    previous_digests: list[str],
) -> str | None:
    """Run the full two-pass summarization pipeline. Returns the formatted digest or None."""
    if not threads:
        logger.info("No threads to summarize.")
        return None

    # Pass 1: select top threads
    logger.info(f"Pass 1: Selecting from {len(threads)} threads...")
    selected_indices = select_top_threads(client, threads, previous_digests)
    selected_indices = [i for i in selected_indices if 0 <= i < len(threads)]

    if not selected_indices:
        logger.info("No threads selected.")
        return None

    selected_threads = [threads[i] for i in selected_indices]

    # Fetch message content for selected threads
    logger.info(f"Fetching content for {len(selected_threads)} selected threads...")
    contents = []
    for thread in selected_threads:
        try:
            content = fetch_message_content(thread.message_url)
            contents.append(content)
        except Exception as e:
            logger.warning(f"Failed to fetch {thread.message_url}: {e}")
            contents.append(f"[Content unavailable: {thread.subject}]")

    # Pass 2: summarize
    logger.info("Pass 2: Generating summaries...")
    return summarize_threads(
        client, selected_threads, contents, previous_digests, len(threads)
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_summarizer.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/summarizer.py tests/test_summarizer.py
git commit -m "feat: add two-pass Claude summarizer for thread curation"
```

---

### Task 4: Slack Poster

**Files:**
- Create: `tests/test_slack_poster.py`
- Create: `src/slack_poster.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_slack_poster.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_slack_poster.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/slack_poster.py tests/test_slack_poster.py
git commit -m "feat: add Slack poster for digest delivery"
```

---

### Task 5: Main Orchestrator

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

**Step 1: Write the failing test**

```python
# tests/test_main.py
import os
from datetime import date
from src.main import load_previous_digests, save_digest


def test_load_previous_digests_reads_recent_files(tmp_path):
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    (digests_dir / "2026-02-10.md").write_text("digest 10")
    (digests_dir / "2026-02-11.md").write_text("digest 11")
    (digests_dir / "2026-02-12.md").write_text("digest 12")
    (digests_dir / "2026-02-08.md").write_text("digest 08")

    result = load_previous_digests(str(digests_dir), date(2026, 2, 13), days=3)
    assert len(result) == 3
    assert "digest 10" in result[0]
    assert "digest 12" in result[2]


def test_save_digest_creates_file(tmp_path):
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    save_digest(str(digests_dir), date(2026, 2, 13), "my digest content")
    path = digests_dir / "2026-02-13.md"
    assert path.exists()
    assert path.read_text() == "my digest content"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add main orchestrator"
```

---

### Task 6: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/daily-digest.yml`

**Step 1: Create the workflow**

```yaml
# .github/workflows/daily-digest.yml
name: Daily pgsql-hackers Digest

on:
  schedule:
    # Run at 8:00 AM UTC every day
    - cron: '0 8 * * *'
  workflow_dispatch: # Allow manual triggering

permissions:
  contents: write

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run digest agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
        run: python -m src.main

      - name: Commit digest
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add digests/
          git diff --staged --quiet || git commit -m "chore: add digest for $(date +%Y-%m-%d)"
          git push
```

**Step 2: Validate the YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily-digest.yml'))"`

**Step 3: Commit**

```bash
git add .github/workflows/daily-digest.yml
git commit -m "ci: add GitHub Actions workflow for daily digest"
```

---

### Task 7: Manual End-to-End Test

**Step 1: Run the scraper standalone to verify it works against the live site**

```bash
python -c "
from src.scraper import scrape_recent_threads
from datetime import date, timedelta
threads = scrape_recent_threads(date.today() - timedelta(days=1))
for t in threads[:5]:
    print(f'{t.date} {t.time} | {t.author} | {t.subject}')
print(f'Total: {len(threads)}')
"
```

Expected: A list of recent threads from pgsql-hackers.

**Step 2: Run the full pipeline (requires env vars)**

```bash
ANTHROPIC_API_KEY=<your-key> SLACK_BOT_TOKEN=<your-token> python -m src.main
```

Expected: A digest appears in your Slack DMs and a file is created in `digests/`.

**Step 3: Verify the digest file**

Run: `cat digests/$(date +%Y-%m-%d).md`

Expected: A formatted digest with numbered highlights and links.

**Step 4: Final commit if any adjustments were needed**

```bash
git add -A
git diff --staged --quiet || git commit -m "fix: adjustments from manual testing"
```

---

### Task 8: Push & Configure GitHub

**Step 1: Create GitHub repo and push**

```bash
gh repo create hackers-agent --private --source=. --push
```

**Step 2: Add secrets**

```bash
gh secret set ANTHROPIC_API_KEY
gh secret set SLACK_BOT_TOKEN
```

**Step 3: Trigger a test run**

```bash
gh workflow run daily-digest.yml
gh run watch
```

Expected: Workflow runs successfully, digest appears in Slack, `digests/` file is committed.
