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
