![Website to Excel scraper](cover.png)

# Website → Excel scraper

Turns a whole online catalogue into a clean **Excel workbook**, plus CSV and JSON, in one command.

![Result in Excel](examples/screenshot.png)

## What a real run produced

Target: [books.toscrape.com](https://books.toscrape.com), a public site built for scraping practice.

| | |
|---|---|
| Products | **1,000** from **50** categories |
| Pages visited | 1,081 (category pages + every product page) |
| Time | ~3 minutes at a polite 0.1 s delay |
| Failed pages | 0 |

Download the actual output: [books.xlsx](examples/books.xlsx) · [books.csv](examples/books.csv) · [books.json](examples/books.json)

The exact command was `python scraper.py --details --delay 0.1 --out examples`; the run report (pages, failures, duplicates, seconds) is saved at the top of `books.json`.

**In the Excel file**
- **Books** sheet: title, category, price, rating, stock, clickable product link, UPC, description; filters and frozen header.
- **Summary** sheet: number of books, average / min / max price and average rating per category, totals, and a chart of the top 10 categories.

## Run it

```sh
pip install -r requirements.txt
python scraper.py                                  # all categories -> output/
python scraper.py --category Poetry --limit 20     # quick test
python scraper.py --details                        # also open every product page (UPC, stock, description)
```

## Built to run unattended

- **Polite and resilient:** delay between requests, automatic retries with back-off on 429/5xx, timeouts, an honest User-Agent.
- **Correct text:** the site sends no charset, so a naive scraper turns `£` into `Â£`; this one decodes UTF-8 explicitly. The CSV opens correctly in Excel.
- **No duplicates, no silent gaps:** products are de-duplicated by URL. Pages that fail to load, listing pages that come back without products (an error or maintenance page) or with an unexpected layout, and product pages missing their UPC or stock line are listed in the run report instead of crashing the run or being skipped quietly.
- **No half-written files:** each output is written to a temporary file and swapped in only when complete.
- **Safe to open in Excel:** scraped text that starts like a formula (`=`, `+`, `-`, `@`) is stored as plain text, so a hostile product title cannot run as a formula when someone opens the file.
- **Tested:** 20 automated tests on saved and synthetic pages (pagination, prices, ratings, product pages, duplicates, error and truncated pages, formula-like text, exports) plus a live smoke test: `pip install -r requirements-dev.txt && LIVE=1 pytest`.

## Adapting it to another site

Most catalogue and listing sites follow the same shape: categories → paginated lists → detail pages. For a new site you change the CSS selectors in `parse_listing` and `parse_detail`; crawling, retries, de-duplication and exports stay as they are. Sites behind logins or CAPTCHAs, or whose terms forbid automated access, are out of scope.

## Why selectors and not an "AI scraper"

LLM scrapers that take a plain-English prompt are popular, so I ran one against this scraper on the same 19 book pages (Poetry category, 16 Nov 2026): [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai) 2.1.4 with `gpt-4.1-mini`, temperature 0. Single run; scores are agreement with this scraper's output.

| | This scraper | ScrapeGraphAI |
|---|---|---|
| Time (single run) | 6.4 s | 81 s |
| Model / API fees | none | $0.018 for 19 pages |
| Title, price, currency, stock, UPC | reference | 19 / 19 agree |
| Star rating | reference | 2 / 19 agree |
| Description, character for character | reference | 2 / 19 agree |
| Installed packages (fresh venv) | 10 | 97, needs Python ≥ 3.12 |

- **Ratings:** the site shows stars only as a CSS class (`star-rating Four`). ScrapeGraphAI converts the page to Markdown before the model sees it, and the class does not survive, so the rating never reaches the model.
- **Descriptions:** the prompt asked for the full description, not for it verbatim, and the output came back cleaned up: a passage the site prints twice and the trailing "...more" were dropped, missing spaces added, apostrophes changed. The Markdown sent to the model still had the original text, so the changes came from the model step. Readable, but no longer what the site says, and nothing in the output marks the change.

For this catalogue, selectors were faster, had no model fees and kept the text as published. That is a trade-off, not a rule: selectors need maintenance when a site changes, and an LLM extractor can save time on a one-off job across many differently built sites, as long as its output is spot-checked against the pages.

Method, raw model answers, scoring script and evidence: [`benchmarks/scrapegraphai/`](benchmarks/scrapegraphai/).

---
Portfolio demo built with AI assistance. Data comes from a public practice site; no client data.
