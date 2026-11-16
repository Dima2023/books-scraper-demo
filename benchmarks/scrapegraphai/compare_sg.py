"""Compare ScrapeGraphAI with this repo's selector-based scraper.

Two commands:

  run      fetch each book page listed in the reference, ask ScrapeGraphAI to
           extract the fields, save the raw answers (raw_llm_output.json)
  score    compare raw answers with the reference and write results.json
           (needs no API key, so anyone can re-check the published numbers)

The reference is books.json written by `scraper.py --details`. ScrapeGraphAI
2.1.4 needs Python >= 3.12:  pip install scrapegraphai==2.1.4

  python compare_sg.py run   <reference books.json> <file with OpenAI key> <model> <out dir>
  python compare_sg.py score <reference books.json> <raw_llm_output.json> <results.json>

The key is read from the file and never printed.
"""
import json
import sys
import time
from pathlib import Path

PROMPT = (
    "Extract the book on this page as JSON with keys: "
    "title (string), price (number, without currency sign), currency (ISO code), "
    "rating (integer 1-5 from the star rating), stock_count (integer, copies available), "
    "upc (string), description (string, full product description)."
)
FIELDS = ["title", "price", "currency", "rating", "stock_count", "upc", "description"]
MISSING = object()  # missing or invalid value; see same()


def unwrap(result):
    """ScrapeGraphAI sometimes wraps the answer in {'content': ...} or a list."""
    if isinstance(result, dict) and set(result) == {"content"}:
        result = result["content"]
    if isinstance(result, list) and result:
        result = result[0]
    return result if isinstance(result, dict) else {}


def run(ref_path, key_path, model, out_dir):
    import requests
    from scrapegraphai.graphs import SmartScraperGraph

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "raw_llm_output.json"
    key = Path(key_path).expanduser().read_text().strip()
    books = json.loads(Path(ref_path).read_text())["books"]
    session = requests.Session()
    session.headers["User-Agent"] = "books-scraper-demo comparison (portfolio test)"

    rows, started = [], time.monotonic()
    for book in books:
        row = {"url": book["url"], "stage": None, "error": None, "got": {},
               "seconds": None, "tokens": 0, "cost_usd": 0.0}
        t0 = time.monotonic()
        try:
            row["stage"] = "fetch"
            response = session.get(book["url"], timeout=15)
            response.raise_for_status()
            html = response.content.decode("utf-8")
            row["stage"] = "setup"
            graph = SmartScraperGraph(
                prompt=PROMPT,
                source=html,
                config={"llm": {"api_key": key, "model": f"openai/{model}", "temperature": 0},
                        "verbose": False, "headless": True},
            )
            row["stage"] = "extract"
            row["got"] = unwrap(graph.run())
            for info in graph.get_execution_info() or []:
                if info.get("node_name") == "TOTAL RESULT":
                    row["tokens"] = int(info.get("total_tokens") or 0)
                    row["cost_usd"] = float(info.get("total_cost_USD") or 0)
            row["stage"] = "done"
        except Exception as exc:  # noqa: BLE001 - record the failed page and its stage, keep going
            row["error"] = type(exc).__name__
        row["seconds"] = round(time.monotonic() - t0, 1)
        rows.append(row)
        # Save after every page, so a crash later does not lose the pages already done.
        raw = {"model": model, "seconds_total": round(time.monotonic() - started, 1), "rows": rows}
        raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1))
        time.sleep(0.1)
    print(f"saved {raw_path}")


def as_int(value):
    """Integer or MISSING; '3' and 3.0 pass, 3.5 and 'three' do not."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MISSING
    return int(number) if number.is_integer() else MISSING


def as_price(value):
    try:
        return round(float(str(value).replace("£", "").strip()), 2)
    except ValueError:
        return MISSING


def field_value(field, record):
    if field not in record or record[field] is None:
        return MISSING
    value = record[field]
    if field in ("rating", "stock_count"):
        return as_int(value)
    if field == "price":
        return as_price(value)
    return str(value).strip()


def same(a, b):
    """Equal and present on both sides: a field missing from both never counts as agreement."""
    return a is not MISSING and b is not MISSING and a == b


def score(ref_path, raw_path, results_path):
    reference = {b["url"]: b for b in json.loads(Path(ref_path).read_text())["books"]}
    raw = json.loads(Path(raw_path).read_text())
    pages = []
    for row in raw["rows"]:
        ref, got = reference[row["url"]], row.get("got") or {}
        match = {f: same(field_value(f, got), field_value(f, ref)) for f in FIELDS}
        ref_desc, got_desc = field_value("description", ref), field_value("description", got)
        match["description_whitespace_normalized"] = (
            got_desc is not MISSING and ref_desc is not MISSING
            and " ".join(got_desc.split()) == " ".join(ref_desc.split()))
        pages.append({"title": ref["title"], "url": row["url"], "seconds": row.get("seconds"),
                      "error": row.get("error"), "rating_reference": ref.get("rating"),
                      "rating_llm": got.get("rating"), "match": match})
    keys = FIELDS + ["description_whitespace_normalized"]
    summary = {
        "model": raw.get("model"),
        "pages": len(pages),
        "errors": sum(1 for p in pages if p["error"]),
        "agreement_with_reference": {k: sum(p["match"][k] for p in pages) for k in keys},
    }
    if "summary" in raw:  # raw file from the first script version (commit 1e388c9)
        for k in ("model", "seconds_total", "tokens_total", "cost_usd_reported"):
            summary[k] = raw["summary"][k]
    else:
        summary["seconds_total"] = raw.get("seconds_total")
        summary["tokens_total"] = sum(r.get("tokens", 0) for r in raw["rows"])
        summary["cost_usd_reported"] = round(sum(r.get("cost_usd", 0) for r in raw["rows"]), 4)
    Path(results_path).write_text(json.dumps({"summary": summary, "pages": pages},
                                             ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    command, args = sys.argv[1], sys.argv[2:]
    {"run": run, "score": score}[command](*args)
