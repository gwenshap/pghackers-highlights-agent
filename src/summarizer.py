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
