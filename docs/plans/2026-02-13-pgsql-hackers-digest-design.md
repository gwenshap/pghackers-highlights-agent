# pgsql-hackers Daily Digest Agent — Design

## Purpose

An automated agent that scans the PostgreSQL hackers mailing list daily, uses Claude to curate the most interesting threads, and sends a digest with links via Slack DM.

## Architecture

```
GitHub Actions (cron 8am UTC)
  → Scrape pgsql-hackers archive (last 24h threads)
  → Two-pass Claude summarization (pick top threads, then summarize)
  → Post digest to Slack DM (@gwen, U030NAS0AJ1)
  → Commit digest to repo
```

## Data Source

- Monthly archive page: `https://www.postgresql.org/list/pgsql-hackers/YYYY-MM/`
- Individual messages: `https://www.postgresql.org/message-id/{message-id}`
- Archive pages list threads by date with subject, author, time, and message-id links
- Web scraping with requests + BeautifulSoup

## Two-Pass Summarization

Token usage concern: 50-100+ messages/day with full bodies could be 200k+ tokens.

**Pass 1 (cheap):** Send only subject lines + authors to Claude. Ask it to pick the ~10 most interesting/notable threads.

**Pass 2:** Fetch full message bodies only for the ~10 selected threads (truncated to first 2000 chars as safety net). Ask Claude to write a brief summary of each.

## Repetition Avoidance

- Store each day's digest as `digests/YYYY-MM-DD.md` in the repo
- The GitHub Action commits and pushes after each run
- Before generating today's digest, read the last 3-5 days' digest files
- Include them in the Claude prompt: "these threads were already highlighted recently — only mention them again if there's significant new development"

## Error Handling

- **Scraping fails:** Log error, exit without posting. No broken digests.
- **Claude API fails:** Log error, exit. Retry next day.
- **No new messages:** Skip posting entirely (no noise on quiet days).
- **Slack post fails:** Log error. Digest is already committed to repo, so nothing lost.

## Repo Structure

```
hackers-agent/
├── .github/
│   └── workflows/
│       └── daily-digest.yml     # GitHub Actions workflow (cron 8am UTC)
├── src/
│   ├── scraper.py               # Fetch & parse the archive page
│   ├── summarizer.py            # Two-pass Claude summarization
│   ├── slack_poster.py          # Post digest to Slack DM
│   └── main.py                  # Orchestrator
├── digests/                     # Auto-committed daily digests
│   └── 2026-02-13.md
├── requirements.txt             # requests, beautifulsoup4, anthropic, slack_sdk
└── README.md
```

## Slack Message Format

```
pgsql-hackers digest — Feb 13, 2026

1. New B-tree access method proposal — Alexandre Felipe proposes a new access method... [link]
2. EXPLAIN ANALYZE timing overhead — Discussion on using rdtsc to reduce... [link]
...

Based on 47 messages from the last 24h
```

## Secrets Required (GitHub repo settings)

- `ANTHROPIC_API_KEY` — Claude API key for summarization
- `SLACK_BOT_TOKEN` — Slack bot token with `chat:write` scope

## Tech Stack

- Python 3.12
- requests + beautifulsoup4 (scraping)
- anthropic SDK (summarization)
- slack_sdk (posting)
- GitHub Actions (scheduling + CI)
