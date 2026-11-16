"""Scoring of the ScrapeGraphAI benchmark: no network, no API key."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "benchmarks" / "scrapegraphai" / "compare_sg.py"
REFERENCE = {"books": [
    {"url": "u1", "title": "A", "price": 1.5, "rating": 3, "description": "Same text."},
    {"url": "u2", "title": "B", "price": 2.0, "rating": 4, "description": None},
]}


def score(tmp_path, rows):
    (tmp_path / "ref.json").write_text(json.dumps(REFERENCE))
    (tmp_path / "raw.json").write_text(json.dumps({"model": "m", "seconds_total": 1, "rows": rows}))
    return subprocess.run(
        [sys.executable, str(SCRIPT), "score", str(tmp_path / "ref.json"), str(tmp_path / "raw.json"),
         str(tmp_path / "results.json")], capture_output=True, text=True)


def test_interrupted_run_counts_missing_pages_as_wrong(tmp_path):
    done = score(tmp_path, [{"url": "u1", "error": None,
                             "got": {"title": "A", "price": "£1.50", "rating": "3",
                                     "description": "Same  text."}}])
    assert done.returncode == 0, done.stderr
    summary = json.loads((tmp_path / "results.json").read_text())["summary"]
    assert (summary["pages_expected"], summary["pages_completed"], summary["pages_missing"]) == (2, 1, 1)
    agreement = summary["agreement_with_reference"]
    assert agreement["title"] == 1 and agreement["price"] == 1 and agreement["rating"] == 1
    # Literal comparison fails on the double space; the normalized one passes.
    assert agreement["description"] == 0 and agreement["description_whitespace_normalized"] == 1


def test_missing_on_both_sides_and_non_integer_rating_do_not_agree(tmp_path):
    done = score(tmp_path, [{"url": "u1", "error": None, "got": {"rating": 3.5}},
                            {"url": "u2", "error": None, "got": {}}])
    assert done.returncode == 0, done.stderr
    agreement = json.loads((tmp_path / "results.json").read_text())["summary"]["agreement_with_reference"]
    assert agreement["rating"] == 0 and agreement["description"] == 0 and agreement["title"] == 0


def test_duplicate_or_unexpected_urls_are_rejected(tmp_path):
    assert score(tmp_path, [{"url": "u1", "got": {}}, {"url": "u1", "got": {}}]).returncode != 0
    assert score(tmp_path, [{"url": "zz", "got": {}}]).returncode != 0
