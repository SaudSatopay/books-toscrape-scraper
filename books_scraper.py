"""Scrape every book on https://books.toscrape.com into a CSV file.

The site lists books in 50 categories. The scraper reads the category list
from the home page, then walks every page of every category by following the
"next" link. That gives each book's category without opening 1000 detail pages.

Run ``python books_scraper.py --help`` for options.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
USER_AGENT = "books-toscrape-scraper/1.0 (+https://github.com/SaudSatopay/books-toscrape-scraper)"
RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
EXPECTED_TOTAL = 1000

log = logging.getLogger("books_scraper")


@dataclass
class Book:
    title: str
    price_gbp: float
    rating: int
    availability: str
    category: str
    url: str


CSV_COLUMNS = [f.name for f in fields(Book)]


# --------------------------------------------------------------------------
# Parsing (pure functions, no network: easy to test)
# --------------------------------------------------------------------------


def parse_categories(html: str, page_url: str) -> list[tuple[str, str]]:
    """Return ``(category name, absolute URL)`` pairs from the side menu."""
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("div.side_categories ul li ul li a")
    return [(a.get_text(strip=True), urljoin(page_url, a["href"])) for a in links]


def parse_price(text: str) -> float:
    """Turn a price like ``"£51.77"`` into ``51.77``."""
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    if not cleaned:
        raise ValueError(f"no price found in {text!r}")
    return float(cleaned)


def parse_rating(classes: list[str]) -> int:
    """Turn ``["star-rating", "Three"]`` into ``3``."""
    for name in classes:
        if name in RATING_WORDS:
            return RATING_WORDS[name]
    raise ValueError(f"no rating found in {classes!r}")


def parse_listing(html: str, page_url: str, category: str) -> tuple[list[Book], str | None]:
    """Parse one listing page.

    Returns the books on the page and the absolute URL of the next page
    (``None`` on the last page).
    """
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        books.append(
            Book(
                # The visible link text is cut short; the title attribute is complete.
                title=link["title"].strip(),
                price_gbp=parse_price(pod.select_one("p.price_color").get_text()),
                rating=parse_rating(pod.select_one("p.star-rating")["class"]),
                availability=pod.select_one("p.availability").get_text(strip=True),
                category=category,
                url=urljoin(page_url, link["href"]),
            )
        )
    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return books, next_url


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


class PoliteClient:
    """HTTP client that waits between requests and retries on errors."""

    def __init__(self, delay: float = 1.0, retries: int = 3, timeout: float = 20.0) -> None:
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.requests_made = 0
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _wait_turn(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str) -> str:
        for attempt in range(1, self.retries + 1):
            self._wait_turn()
            try:
                response = self.session.get(url, timeout=self.timeout)
                self.requests_made += 1
                response.raise_for_status()
                # The site serves UTF-8 but does not always say so; without this
                # "£" can come back garbled.
                response.encoding = "utf-8"
                return response.text
            except requests.RequestException as error:
                if attempt == self.retries:
                    raise
                backoff = self.delay * 2**attempt
                log.warning("Request failed (%s), retrying in %.1fs: %s", error, backoff, url)
                time.sleep(backoff)
        raise AssertionError("unreachable")


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------


def scrape(client: PoliteClient, base_url: str = BASE_URL) -> list[Book]:
    categories = parse_categories(client.get(base_url), base_url)
    log.info("Found %d categories", len(categories))

    books: dict[str, Book] = {}
    for number, (category, url) in enumerate(categories, start=1):
        page = 1
        next_url: str | None = url
        while next_url:
            page_books, next_url = parse_listing(client.get(next_url), next_url, category)
            for book in page_books:
                books.setdefault(book.url, book)
            log.info(
                "[%2d/%d] %-20s page %d: %d books (total %d)",
                number, len(categories), category, page, len(page_books), len(books),
            )
            page += 1
    return list(books.values())


def write_csv(books: list[Book], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(asdict(book) for book in books)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape books.toscrape.com to CSV.")
    parser.add_argument("-o", "--output", type=Path, default=Path("data/books.csv"),
                        help="CSV file to write (default: data/books.csv)")
    parser.add_argument("-d", "--delay", type=float, default=1.0,
                        help="seconds to wait between requests (default: 1.0)")
    parser.add_argument("-r", "--retries", type=int, default=3,
                        help="attempts per page before giving up (default: 3)")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print warnings and the summary")
    args = parser.parse_args(argv)

    if args.delay < 0:
        parser.error("--delay cannot be negative")

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    client = PoliteClient(delay=args.delay, retries=args.retries)
    started = time.monotonic()
    books = scrape(client)
    write_csv(books, args.output)

    elapsed = time.monotonic() - started
    print(f"Saved {len(books)} books to {args.output} "
          f"({client.requests_made} requests in {elapsed:.0f}s)")
    if len(books) != EXPECTED_TOTAL:
        print(f"Warning: expected {EXPECTED_TOTAL} books, got {len(books)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
