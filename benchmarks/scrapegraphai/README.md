# Benchmark: selector scraper vs ScrapeGraphAI

A single run on 16 Nov 2026, kept so every number in the main README can be checked.

## What was compared

- **Pages:** the 19 book pages of the Poetry category on books.toscrape.com, a public practice site.
- **Reference:** `reference_books.json`, the output of `python scraper.py --category Poetry --details --delay 0.1` (commit `4f982a9`). Scores are **agreement with this reference**, not independently verified ground truth; spot checks against the live pages are in [EVIDENCE.md](EVIDENCE.md).
- **LLM tool:** ScrapeGraphAI 2.1.4, `SmartScraperGraph`, `gpt-4.1-mini`, temperature 0, one call per page. Prompt: see `PROMPT` in `compare_sg.py`.
- **Raw answers:** `raw_llm_output.json`, exactly as saved by the run (it used the first version of `compare_sg.py`, commit `1e388c9`; `score` reads that format).
- **Scores:** `results.json`, produced by the `score` command below. No API key is needed for this step.

## Environment

Linux aarch64 VM on an Apple M1 Max MacBook Pro, home connection. Selector scraper: Python 3.10.12. ScrapeGraphAI: Python 3.12.16 (the package declares `Requires-Python >=3.12`).

Installed distributions in a fresh virtual environment, counted the same way for both (all distributions, minus pip, setuptools and wheel): **10** for `requirements.txt`, **97** for `scrapegraphai==2.1.4`.

## Timing: what each number covers

- **6.4 s, selector scraper:** the run's own report. 21 requests (category list, listing page, 19 book pages), 0.1 s pause between requests.
- **81.0 s, ScrapeGraphAI:** wall time of the `run` loop. 19 requests for the book pages (URLs taken from the reference), one model call per page, 0.1 s pause between pages.

Both are single runs, so treat them as an order of magnitude, not a precise ratio. The token count and cost ($0.0182, 30,526 tokens) are what ScrapeGraphAI reported for the run.

## Reproduce

From the repository root. The two tools need separate environments, because ScrapeGraphAI needs Python 3.12 or newer.

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scraper.py --category Poetry --details --delay 0.1 --out ref

python3.12 -m venv .venv-sg && .venv-sg/bin/pip install scrapegraphai==2.1.4 requests
.venv-sg/bin/python benchmarks/scrapegraphai/compare_sg.py run ref/books.json ~/openai_key.txt gpt-4.1-mini out
.venv-sg/bin/python benchmarks/scrapegraphai/compare_sg.py score ref/books.json out/raw_llm_output.json out/results.json
```

To re-check the published scores without an API key (any Python 3.10+):

```sh
python benchmarks/scrapegraphai/compare_sg.py score benchmarks/scrapegraphai/reference_books.json benchmarks/scrapegraphai/raw_llm_output.json /tmp/results.json
```

`score` counts every reference page: a page missing from an interrupted run counts as wrong, and duplicate or unknown URLs stop the scoring.

Model answers vary between runs and model versions, so a new run will not match these numbers exactly.
