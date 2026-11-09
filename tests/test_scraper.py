import csv
from pathlib import Path

import pytest

import books_scraper as bs

FIXTURES = Path(__file__).parent / "fixtures"
HOME_URL = "https://books.toscrape.com/index.html"
MYSTERY_URL = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_categories_finds_all_50():
    categories = bs.parse_categories(read("home.html"), HOME_URL)
    assert len(categories) == 50
    assert categories[0] == (
        "Travel",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
    )
    assert ("Mystery", MYSTERY_URL) in categories


@pytest.mark.parametrize(
    ("text", "expected"),
    [("£51.77", 51.77), ("Â£13.99", 13.99), ("£10.00", 10.0)],
)
def test_parse_price(text, expected):
    assert bs.parse_price(text) == expected


def test_parse_price_rejects_empty():
    with pytest.raises(ValueError):
        bs.parse_price("free")


@pytest.mark.parametrize(
    ("word", "stars"), [("One", 1), ("Two", 2), ("Three", 3), ("Four", 4), ("Five", 5)]
)
def test_parse_rating(word, stars):
    assert bs.parse_rating(["star-rating", word]) == stars


def test_parse_rating_rejects_unknown():
    with pytest.raises(ValueError):
        bs.parse_rating(["star-rating"])


def test_parse_listing_first_page_has_books_and_next_link():
    books, next_url = bs.parse_listing(read("category_page1.html"), MYSTERY_URL, "Mystery")

    assert len(books) == 20
    assert next_url == "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html"

    first = books[0]
    assert first.title == "Sharp Objects"
    assert first.price_gbp == 47.82
    assert first.rating == 4
    assert first.availability == "In stock"
    assert first.category == "Mystery"
    assert first.url == "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"


def test_parse_listing_uses_full_title_not_truncated_text():
    books, _ = bs.parse_listing(read("category_page1.html"), MYSTERY_URL, "Mystery")
    assert all("..." not in book.title for book in books)


def test_parse_listing_last_page_has_no_next_link():
    url = "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html"
    books, next_url = bs.parse_listing(read("category_last.html"), url, "Mystery")
    assert len(books) == 12
    assert next_url is None


class FakeClient:
    """Serves saved pages instead of hitting the network."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        return self.pages[url]


def test_scrape_follows_pagination(monkeypatch):
    client = FakeClient(
        {
            "https://books.toscrape.com/": read("home.html"),
            MYSTERY_URL: read("category_page1.html"),
            MYSTERY_URL.replace("index.html", "page-2.html"): read("category_last.html"),
        }
    )
    # Keep only the Mystery category so the test stays small and offline.
    monkeypatch.setattr(bs, "parse_categories", lambda html, url: [("Mystery", MYSTERY_URL)])

    books = bs.scrape(client)

    assert len(books) == 32
    assert client.requested[-1].endswith("page-2.html")
    assert {book.category for book in books} == {"Mystery"}


def test_polite_client_waits_between_requests(monkeypatch):
    client = bs.PoliteClient(delay=1.5)
    clock = iter([100.0, 100.0, 100.2, 101.7])
    sleeps = []
    monkeypatch.setattr(bs.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(bs.time, "sleep", sleeps.append)

    client._wait_turn()  # first request: no wait needed
    client._wait_turn()  # 0.2s later: must wait the remaining 1.3s

    assert sleeps == [pytest.approx(1.3)]


def test_write_csv(tmp_path):
    books = [bs.Book("A Light in the Attic", 51.77, 3, "In stock", "Poetry", "https://x/a")]
    out = tmp_path / "out" / "books.csv"
    bs.write_csv(books, out)

    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "title": "A Light in the Attic",
            "price_gbp": "51.77",
            "rating": "3",
            "availability": "In stock",
            "category": "Poetry",
            "url": "https://x/a",
        }
    ]
