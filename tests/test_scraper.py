"""Offline tests on saved pages from books.toscrape.com. Set LIVE=1 to also hit the real site."""
import csv
import json
import os
from pathlib import Path

import pytest
import requests
from openpyxl import load_workbook

import scraper
from export import summary_rows, write_all
from scraper import BASE_URL, crawl, parse_categories, parse_detail, parse_listing, parse_price

FIXTURES = Path(__file__).parent / "fixtures"
MYSTERY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
PAGES = {
    BASE_URL: "index.html",
    MYSTERY: "category_mystery_p1.html",
    MYSTERY.replace("index.html", "page-2.html"): "category_mystery_p2.html",
}


def fake_fetch(url):
    return (FIXTURES / PAGES[url]).read_bytes().decode("utf-8")


def test_categories_are_absolute_and_complete():
    categories = parse_categories(fake_fetch(BASE_URL), BASE_URL)
    assert len(categories) == 50
    assert ("Mystery", MYSTERY) in categories


def test_listing_fields_and_pagination():
    books, next_url = parse_listing(fake_fetch(MYSTERY), MYSTERY, "Mystery")
    assert len(books) == 20
    assert next_url == MYSTERY.replace("index.html", "page-2.html")
    first = books[0]
    assert first.title and first.category == "Mystery"
    assert first.currency == "GBP" and first.price > 0
    assert 1 <= first.rating <= 5
    assert first.url.startswith("https://books.toscrape.com/catalogue/")
    assert first.image_url.startswith("https://books.toscrape.com/media/")


def test_last_page_has_no_next():
    url = MYSTERY.replace("index.html", "page-2.html")
    books, next_url = parse_listing(fake_fetch(url), url, "Mystery")
    assert len(books) == 12 and next_url is None


def test_detail_page():
    detail = parse_detail((FIXTURES / "book_detail.html").read_text(encoding="utf-8"))
    assert detail["upc"] == "a897fe39b1053632"
    assert detail["stock_count"] == 22
    assert detail["description"].startswith("It's hard to imagine")


@pytest.mark.parametrize("text, expected", [("£51.77", (51.77, "GBP")), ("$1,204.50", (1204.5, "USD"))])
def test_price_parsing(text, expected):
    assert parse_price(text) == expected


def test_price_parsing_rejects_garbage():
    with pytest.raises(ValueError):
        parse_price("free")


def test_crawl_follows_pagination_and_dedupes():
    calls = []

    def counting_fetch(url):
        calls.append(url)
        return fake_fetch(url)

    books, report = crawl(counting_fetch, categories=["mystery"])
    assert len(books) == 32 and report.books_found == 32
    assert report.categories == 1 and report.pages_fetched == 3 and not report.failed_pages
    assert len({b.url for b in books}) == 32

    # the same category listed twice must not duplicate books
    books_again, report_again = crawl(fake_fetch, categories=["Mystery", "MYSTERY"])
    assert len(books_again) == 32


def test_crawl_limit_and_unknown_category():
    books, _ = crawl(fake_fetch, categories=["Mystery"], limit=5)
    assert len(books) == 5
    with pytest.raises(ValueError):
        crawl(fake_fetch, categories=["No such category"])


def test_failed_page_is_reported_not_fatal():
    def flaky(url):
        if "page-2" in url:
            raise requests.ConnectionError("boom")
        return fake_fetch(url)

    books, report = crawl(flaky, categories=["Mystery"])
    assert len(books) == 20
    assert len(report.failed_pages) == 1 and "page-2" in report.failed_pages[0]


def test_exports(tmp_path):
    books, report = crawl(fake_fetch, categories=["Mystery"])
    paths = write_all(books, report, tmp_path)
    assert [p.name for p in paths] == ["books.xlsx", "books.csv", "books.json"]

    wb = load_workbook(paths[0])
    assert wb.sheetnames == ["Books", "Summary"]
    sheet = wb["Books"]
    assert sheet.max_row == 33 and sheet["A1"].value == "Title"
    assert isinstance(sheet["C2"].value, float)
    assert wb["Summary"]["A2"].value == "Mystery" and wb["Summary"]["B2"].value == 32

    with paths[1].open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 32 and rows[0]["Currency"] == "GBP"
    assert "Â" not in paths[1].read_text(encoding="utf-8-sig")

    data = json.loads(paths[2].read_text(encoding="utf-8"))
    assert data["report"]["books_found"] == 32 and len(data["books"]) == 32

    # re-running overwrites cleanly and leaves no temp files behind
    write_all(books, report, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["books.csv", "books.json", "books.xlsx"]


def test_summary_rows():
    books, _ = crawl(fake_fetch, categories=["Mystery"])
    (row,) = summary_rows(books)
    assert row["books"] == 32 and row["min_price"] <= row["avg_price"] <= row["max_price"]


@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="set LIVE=1 to test against the real site")
def test_live_smoke():
    books, report = crawl(scraper.make_fetcher(delay=0.1), categories=["Poetry"], limit=5)
    assert len(books) == 5 and not report.failed_pages
    assert all(b.price > 0 and b.currency == "GBP" for b in books)
