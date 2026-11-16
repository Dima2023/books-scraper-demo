"""Compare ScrapeGraphAI with this repo's selector-based scraper.

Both get the same book pages; the reference is books.json written by
`scraper.py --details`. Needs Python >= 3.12 and `pip install scrapegraphai==2.1.4`.

Usage: python compare_sg.py <reference books.json> <file with OpenAI key> <model> <out dir>
The key is read from the file and never printed.
"""
import json
import sys
import time
from pathlib import Path

import requests
from scrapegraphai.graphs import SmartScraperGraph

PROMPT = (
    "Extract the book on this page as JSON with keys: "
    "title (string), price (number, without currency sign), currency (ISO code), "
    "rating (integer 1-5 from the star rating), stock_count (integer, copies available), "
    "upc (string), description (string, full product description)."
)
FIELDS = ["title", "price", "currency", "rating", "stock_count", "upc", "description"]


def norm(field, value):
    if value is None:
        return None
    if field == "price":
        try:
            return round(float(str(value).replace("£", "").strip()), 2)
        except ValueError:
            return str(value)
    if field in ("rating", "stock_count"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return str(value)
    return " ".join(str(value).split())


def unwrap(result):
    """ScrapeGraphAI sometimes wraps the answer in {'content': ...} or a list."""
    if isinstance(result, dict) and set(result) == {"content"}:
        result = result["content"]
    if isinstance(result, list) and result:
        result = result[0]
    return result if isinstance(result, dict) else {}


def main(ref_path, key_path, model, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key = Path(key_path).expanduser().read_text().strip()
    books = json.loads(Path(ref_path).read_text())["books"]

    session = requests.Session()
    session.headers["User-Agent"] = "books-scraper-demo comparison (portfolio test)"

    rows, tokens, cost, started = [], 0, 0.0, time.monotonic()
    for book in books:
        html = session.get(book["url"], timeout=15).content.decode("utf-8")
        graph = SmartScraperGraph(
            prompt=PROMPT,
            source=html,
            config={"llm": {"api_key": key, "model": f"openai/{model}", "temperature": 0},
                    "verbose": False, "headless": True},
        )
        t0 = time.monotonic()
        try:
            got = unwrap(graph.run())
            error = None
        except Exception as exc:  # noqa: BLE001 - record the failed page, keep going
            got, error = {}, type(exc).__name__
        seconds = time.monotonic() - t0
        for info in graph.get_execution_info() or []:
            if info.get("node_name") == "TOTAL RESULT":
                tokens += int(info.get("total_tokens") or 0)
                cost += float(info.get("total_cost_USD") or 0)
        match = {f: norm(f, got.get(f)) == norm(f, book.get(f)) for f in FIELDS}
        rows.append({"url": book["url"], "seconds": round(seconds, 1), "error": error,
                     "match": match, "got": got})
        time.sleep(0.1)

    total = time.monotonic() - started
    per_field = {f: sum(r["match"][f] for r in rows) for f in FIELDS}
    summary = {
        "model": model, "pages": len(rows), "seconds_total": round(total, 1),
        "tokens_total": tokens, "cost_usd_reported": round(cost, 4),
        "errors": sum(1 for r in rows if r["error"]),
        "fields_correct": per_field,
        "pages_all_fields_correct": sum(all(r["match"].values()) for r in rows),
    }
    (out / "sg_result.json").write_text(json.dumps({"summary": summary, "rows": rows},
                                                   ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
