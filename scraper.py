#!/usr/bin/env python3
"""Scrape a product catalogue into Excel, CSV and JSON.

Demo target: https://books.toscrape.com — a public sandbox built for scraping practice.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://books.toscrape.com/index.html"
USER_AGENT = "books-scraper-demo/1.0 (+https://github.com/Dima2023/books-scraper-demo)"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

Fetch = Callable[[str], str]


@dataclass
class Book:
    title: str
    category: str
    price: float
    currency: str
    rating: int
    in_stock: bool
    url: str
    image_url: str
    upc: str = ""
    stock_count: int | None = None
    description: str = ""


@dataclass
class RunReport:
    pages_fetched: int = 0
    books_found: int = 0
    duplicates_skipped: int = 0
    categories: int = 0
    failed_pages: list[str] = field(default_factory=list)
    seconds: float = 0.0


# ---------------------------------------------------------------- fetching

def make_fetcher(delay: float = 0.2, timeout: float = 15.0) -> Fetch:
    """HTTP GET with retries, backoff, a polite delay and forced UTF-8 decoding."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=4, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))

    def fetch(url: str) -> str:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if delay:
            time.sleep(delay)
        # The server omits a charset; requests would guess ISO-8859-1 and turn "£" into "Â£".
        return response.content.decode("utf-8")

    return fetch


# ---------------------------------------------------------------- parsing

def parse_categories(html: str, page_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("div.side_categories ul li ul li a")
    return [(a.get_text(strip=True), urljoin(page_url, a["href"])) for a in links]


def parse_price(text: str) -> tuple[float, str]:
    match = re.search(r"([£$€])\s*([\d,]+(?:\.\d+)?)", text)
    if not match:
        raise ValueError(f"unrecognised price: {text!r}")
    return float(match.group(2).replace(",", "")), {"£": "GBP", "$": "USD", "€": "EUR"}[match.group(1)]


def parse_listing(html: str, page_url: str, category: str) -> tuple[list[Book], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        price, currency = parse_price(pod.select_one("p.price_color").get_text())
        rating_class = next((c for c in pod.select_one("p.star-rating")["class"] if c in RATINGS), None)
        books.append(Book(
            title=link["title"].strip(),
            category=category,
            price=price,
            currency=currency,
            rating=RATINGS.get(rating_class, 0),
            in_stock="in stock" in pod.select_one("p.availability").get_text(" ", strip=True).lower(),
            url=urljoin(page_url, link["href"]),
            image_url=urljoin(page_url, pod.select_one("img")["src"]),
        ))
    next_link = soup.select_one("li.next a")
    return books, urljoin(page_url, next_link["href"]) if next_link else None


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = {row.th.get_text(strip=True): row.td.get_text(strip=True)
             for row in soup.select("table.table-striped tr")}
    stock = re.search(r"\((\d+) available\)", table.get("Availability", ""))
    description = soup.select_one("#product_description + p")
    return {
        "upc": table.get("UPC", ""),
        "stock_count": int(stock.group(1)) if stock else 0,
        "description": description.get_text(strip=True) if description else "",
    }


# ---------------------------------------------------------------- crawling

def crawl(fetch: Fetch, start_url: str = BASE_URL, *, categories: Iterable[str] | None = None,
          limit: int | None = None, details: bool = False,
          log: Callable[[str], None] = lambda message: None) -> tuple[list[Book], RunReport]:
    """Walk every category and its pagination; de-duplicate by product URL."""
    started = time.monotonic()
    report = RunReport()
    wanted = {name.lower() for name in categories} if categories else None
    found = parse_categories(fetch(start_url), start_url)
    report.pages_fetched += 1
    if not found:
        raise ValueError("no categories found on the start page (site layout changed?)")
    selected = [(name, url) for name, url in found if wanted is None or name.lower() in wanted]
    if wanted and not selected:
        raise ValueError("none of the requested categories exist on the site")
    report.categories = len(selected)

    books: list[Book] = []
    seen: set[str] = set()
    for name, url in selected:
        page_url: str | None = url
        while page_url and (limit is None or len(books) < limit):
            try:
                html = fetch(page_url)
            except requests.RequestException as exc:
                report.failed_pages.append(f"{page_url} ({exc.__class__.__name__})")
                log(f"  ! failed {page_url}: {exc}")
                break
            report.pages_fetched += 1
            current = page_url
            try:
                page_books, page_url = parse_listing(html, current, name)
            except (ValueError, KeyError, AttributeError, TypeError) as exc:
                report.failed_pages.append(f"{current} (unexpected page structure: {exc.__class__.__name__})")
                log(f"  ! could not parse {current}")
                break
            if not page_books:
                report.failed_pages.append(f"{current} (no products found)")
                log(f"  ! no products on {current}")
                break
            for book in page_books:
                if book.url in seen:
                    report.duplicates_skipped += 1
                    continue
                seen.add(book.url)
                books.append(book)
                if limit is not None and len(books) >= limit:
                    break
        log(f"  {name}: {sum(b.category == name for b in books)} books")
        if limit is not None and len(books) >= limit:
            break

    if details:
        for index, book in enumerate(books, 1):
            try:
                detail = parse_detail(fetch(book.url))
                report.pages_fetched += 1
                if not detail["upc"]:
                    raise ValueError("no product table")
                for key, value in detail.items():
                    setattr(book, key, value)
            except (requests.RequestException, ValueError, AttributeError, TypeError) as exc:
                report.failed_pages.append(f"{book.url} ({exc.__class__.__name__})")
            if index % 100 == 0:
                log(f"  details: {index}/{len(books)}")

    report.books_found = len(books)
    report.seconds = round(time.monotonic() - started, 1)
    return books, report


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    from export import write_all

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("output"), help="output folder (default: output)")
    parser.add_argument("--category", action="append", help="only this category; repeat for several")
    parser.add_argument("--limit", type=int, help="stop after N books (quick test runs)")
    parser.add_argument("--details", action="store_true", help="also open each book page for UPC, stock count and description")
    parser.add_argument("--delay", type=float, default=0.2, help="pause between requests, seconds (default 0.2)")
    args = parser.parse_args(argv)

    print(f"Scraping {BASE_URL} ...")
    try:
        books, report = crawl(make_fetcher(delay=args.delay), categories=args.category,
                              limit=args.limit, details=args.details, log=print)
    except (requests.RequestException, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not books:
        print("error: no books found", file=sys.stderr)
        return 2
    files = write_all(books, report, args.out)
    print(f"\nDone: {report.books_found} books from {report.categories} categories, "
          f"{report.pages_fetched} pages in {report.seconds}s, {len(report.failed_pages)} failed pages.")
    for path in files:
        print(f"  -> {path}")
    return 0 if not report.failed_pages else 1


if __name__ == "__main__":
    sys.exit(main())
