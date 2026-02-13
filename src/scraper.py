# src/scraper.py
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

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


def parse_archive_page(html: str) -> List[ThreadInfo]:
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


def _parse_date_header(text: str) -> Optional[date]:
    """Parse date headers like 'Feb. 1, 2026' or 'February 1, 2026'."""
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


def scrape_recent_threads(since_date: date) -> List[ThreadInfo]:
    """Scrape all threads since the given date."""
    html = fetch_archive_page(since_date)
    threads = parse_archive_page(html)
    return [t for t in threads if t.date >= since_date]
