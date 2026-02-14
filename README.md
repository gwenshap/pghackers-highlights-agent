# pgsql-hackers Highlights Agent

An AI-powered daily digest of the [PostgreSQL hackers mailing list](https://www.postgresql.org/list/pgsql-hackers/). Every morning, it scrapes the latest messages, uses Claude to pick the most interesting threads, and delivers a curated summary to your Slack DMs.

## Example Digest

> **pgsql-hackers digest -- Feb 13, 2026**
>
> 1. **HEAP_XMAX_COMMITTED flag incompatibility with multixacts** -- Andy Fan questions why PostgreSQL deliberately discards the HEAP_XMAX_COMMITTED hint bit when converting a transaction ID to a multixact...
>
> 2. **64-bit XID patch debate continues** -- Maxim Orlov pushes back on committer feedback rejecting his approach to make all XIDs 64-bit...
>
> 3. **ON CONFLICT DO SELECT committed** -- Dean Rasheed announces the commit of the ON CONFLICT DO SELECT feature...
>
> _Based on 200 messages from the last 24h_

## How It Works

1. **Scrape** -- Fetches the [pgsql-hackers web archive](https://www.postgresql.org/list/pgsql-hackers/) for the last 24 hours of messages
2. **Select** (Pass 1) -- Sends all subject lines to Claude, which picks the ~10 most interesting threads
3. **Summarize** (Pass 2) -- Fetches the full content of the selected threads, then Claude writes a concise summary of each
4. **Deliver** -- Posts the formatted digest to your Slack DMs
5. **Archive** -- Commits the digest to `digests/` so the agent avoids repeating the same highlights day after day

Runs daily via GitHub Actions on a cron schedule.

## Fork & Set Up Your Own

1. **Fork this repo**

2. **Add secrets** in your fork's Settings > Secrets and variables > Actions:
   - `ANTHROPIC_API_KEY` -- your [Anthropic API key](https://console.anthropic.com/)
   - `SLACK_BOT_TOKEN` -- a Slack bot token with `chat:write` scope ([create a Slack app](https://api.slack.com/apps))

3. **Find your Slack user ID** -- In Slack, click your profile > three dots > "Copy member ID"

4. **Update the user ID** in `src/main.py`:
   ```python
   SLACK_USER_ID = "YOUR_SLACK_USER_ID"
   ```

5. **Adjust the schedule** in `.github/workflows/daily-digest.yml`:
   ```yaml
   schedule:
     - cron: '0 14 * * *'  # 6am PST / 2pm UTC
   ```

6. **Test it** -- Go to Actions > "Daily pgsql-hackers Digest" > "Run workflow"

## Customization

**Different mailing list?** Modify the URL in `src/scraper.py` -- the parsing works with any `postgresql.org/list/` archive page. For non-PostgreSQL lists, you'd need to adapt the HTML parsing.

**Post to a channel instead of DM?** Change `SLACK_USER_ID` to a channel ID.

**Change what gets highlighted?** Edit the prioritization criteria in the selection prompt in `src/summarizer.py`.

## Project Structure

```
src/
  scraper.py       # Fetches & parses the archive page
  summarizer.py    # Two-pass Claude summarization
  slack_poster.py  # Formats & posts to Slack
  main.py          # Orchestrator
tests/             # Unit tests (pytest)
digests/           # Auto-committed daily digests
.github/workflows/ # GitHub Actions cron workflow
```

## Running Locally

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY="your-key"
export SLACK_BOT_TOKEN="your-token"

python -m src.main
```

## License

MIT
