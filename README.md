# books-toscrape-scraper

[![CI](https://github.com/SaudSatopay/books-toscrape-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/SaudSatopay/books-toscrape-scraper/actions/workflows/ci.yml)

A Python scraper that collects **all 1000 books** from the practice site [books.toscrape.com](https://books.toscrape.com) and saves them to a CSV file with each book's **title, price, rating, availability and category**.

The output from a full run is committed at [`data/books.csv`](data/books.csv).

## How it works

1. Reads the list of 50 categories from the home page.
2. Opens each category and **follows the "next" link through every page** until the last one.
3. Reads every book card on each page and saves the results to CSV.

Crawling by category means every book gets its category straight from the listing, without opening 1000 separate book pages. A full run takes about **81 requests and 81 seconds**.

**Polite scraping:**

- Waits **1 second between requests** by default (change it with `--delay`).
- Sends one request at a time, never in parallel.
- Retries failed requests up to 3 times, with a growing wait between attempts.
- Identifies itself with a clear User-Agent.

## Output

`data/books.csv`, UTF-8, one row per book:

| Column | Example | Notes |
| --- | --- | --- |
| `title` | `A Light in the Attic` | Full title (the listing shortens long titles; the scraper reads the full one) |
| `price_gbp` | `51.77` | Price in pounds, as a number |
| `rating` | `3` | Star rating from 1 to 5 |
| `availability` | `In stock` | Stock status as shown on the site |
| `category` | `Poetry` | One of the site's 50 categories |
| `url` | `https://books.toscrape.com/catalogue/...` | Link to the book's page |

## Setup

Requirements: Python 3.10 or newer, and Git.

```bash
git clone https://github.com/SaudSatopay/books-toscrape-scraper.git
cd books-toscrape-scraper
python -m venv .venv
```

Activate the virtual environment:

- Windows: `.venv\Scripts\activate`
- macOS / Linux: `source .venv/bin/activate`

Install the dependencies (`requests` and `beautifulsoup4`):

```bash
pip install -r requirements.txt
```

## Run

```bash
python books_scraper.py
```

This writes `data/books.csv` and prints a summary such as:

```
Saved 1000 books to data/books.csv (81 requests in 81s)
```

The script exits with code 1 if it collects anything other than 1000 books.

### Options

| Option | Default | What it does |
| --- | --- | --- |
| `-o`, `--output` | `data/books.csv` | Where to write the CSV |
| `-d`, `--delay` | `1.0` | Seconds to wait between requests |
| `-r`, `--retries` | `3` | Attempts per page before giving up |
| `-q`, `--quiet` | off | Hide progress, show only warnings and the summary |

Example: `python books_scraper.py --delay 2 --output books.csv`

## Tests

The tests run offline against saved copies of the site's pages in `tests/fixtures/`. They cover parsing, pagination, the delay between requests and CSV writing.

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

GitHub Actions runs the linter and tests on Python 3.10, 3.12 and 3.13 for every push and pull request. It also checks that `data/books.csv` has 1000 unique books with every field filled in.

## Project layout

```
books_scraper.py           The scraper (parsing, polite HTTP client, crawl, CSV)
data/books.csv             Output from a full run (1000 books)
tests/test_scraper.py      Tests
tests/fixtures/            Saved pages used by the tests
.github/workflows/ci.yml   CI: lint, tests, CSV check
```

## License

MIT
