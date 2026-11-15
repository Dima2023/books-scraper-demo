"""Write scraped books to Excel (with a summary sheet and chart), CSV and JSON."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from collections import defaultdict
from dataclasses import asdict, fields
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from scraper import Book, RunReport

HEADERS = {
    "title": "Title", "category": "Category", "price": "Price", "currency": "Currency",
    "rating": "Rating (1-5)", "in_stock": "In stock", "url": "Product URL", "image_url": "Image URL",
    "upc": "UPC", "stock_count": "Units available", "description": "Description",
}


def _columns(books: list[Book]) -> list[str]:
    """Skip detail-only columns when --details was not used."""
    names = [f.name for f in fields(Book)]
    if not any(b.upc for b in books):
        names = [n for n in names if n not in ("upc", "stock_count", "description")]
    return names


def _replace(path: Path, write) -> None:
    """Write to a temp file in the same folder, then swap it in (no half-written files)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        write(Path(tmp))
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)  # mkstemp creates 0600; give the result normal file permissions
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def summary_rows(books: list[Book]) -> list[dict]:
    groups: dict[str, list[Book]] = defaultdict(list)
    for book in books:
        groups[book.category].append(book)
    rows = []
    for category, items in groups.items():
        prices = [b.price for b in items]
        rows.append({
            "category": category,
            "books": len(items),
            "avg_price": round(sum(prices) / len(prices), 2),
            "min_price": min(prices),
            "max_price": max(prices),
            "avg_rating": round(sum(b.rating for b in items) / len(items), 2),
        })
    return sorted(rows, key=lambda r: (-r["books"], r["category"]))


def write_xlsx(books: list[Book], path: Path) -> None:
    columns = _columns(books)
    wb = Workbook()
    ws = wb.active
    ws.title = "Books"
    ws.append([HEADERS[c] for c in columns])
    for book in books:
        data = asdict(book)
        data["in_stock"] = "Yes" if book.in_stock else "No"
        ws.append([data[c] for c in columns])

    widths = {"title": 48, "category": 18, "price": 10, "currency": 10, "rating": 12, "in_stock": 10,
              "url": 40, "image_url": 40, "upc": 18, "stock_count": 15, "description": 60}
    for index, column in enumerate(columns, 1):
        letter = get_column_letter(index)
        ws.column_dimensions[letter].width = widths[column]
        if column == "price":
            for cell in ws[letter][1:]:
                cell.number_format = "#,##0.00"
        if column == "url":
            for cell in ws[letter][1:]:
                cell.hyperlink = cell.value
                cell.style = "Hyperlink"
    last = f"{get_column_letter(len(columns))}{len(books) + 1}"
    table = Table(displayName="Books", ref=f"A1:{last}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)
    ws.freeze_panes = "A2"

    summary = wb.create_sheet("Summary")
    rows = summary_rows(books)
    summary.append(["Category", "Books", "Avg price", "Min price", "Max price", "Avg rating"])
    for row in rows:
        summary.append(list(row.values()))
    total_row = len(rows) + 2
    price = f"Books!${get_column_letter(columns.index('price') + 1)}$2:${get_column_letter(columns.index('price') + 1)}${len(books) + 1}"
    rating = f"Books!${get_column_letter(columns.index('rating') + 1)}$2:${get_column_letter(columns.index('rating') + 1)}${len(books) + 1}"
    summary.append(["TOTAL", f"=SUM(B2:B{total_row - 1})", f"=ROUND(AVERAGE({price}),2)",
                    f"=MIN({price})", f"=MAX({price})", f"=ROUND(AVERAGE({rating}),2)"])
    for cell in summary[1] + summary[total_row]:
        cell.font = Font(bold=True)
    for cell in summary[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    for letter, width in zip("ABCDEF", (22, 9, 11, 11, 11, 11)):
        summary.column_dimensions[letter].width = width
    for row in summary.iter_rows(min_row=2, min_col=3, max_col=5):
        for cell in row:
            cell.number_format = "#,##0.00"
    summary.freeze_panes = "A2"

    top = min(10, len(rows))
    chart = BarChart()
    chart.type = "bar"
    chart.title = f"Top {top} categories by number of books"
    chart.y_axis.title = "Books"
    chart.legend = None
    chart.add_data(Reference(summary, min_col=2, min_row=1, max_row=top + 1), titles_from_data=True)
    chart.set_categories(Reference(summary, min_col=1, min_row=2, max_row=top + 1))
    chart.x_axis.scaling.orientation = "maxMin"
    chart.height, chart.width = 9, 16
    summary.add_chart(chart, "H2")

    _replace(path, lambda tmp: wb.save(tmp))


def write_csv(books: list[Book], path: Path) -> None:
    columns = _columns(books)

    def write(tmp: Path) -> None:
        # utf-8-sig so Excel opens "£" and non-English titles correctly on double-click.
        with tmp.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow([HEADERS[c] for c in columns])
            for book in books:
                data = asdict(book)
                writer.writerow([data[c] for c in columns])

    _replace(path, write)


def write_json(books: list[Book], report: RunReport, path: Path) -> None:
    columns = _columns(books)
    payload = {"report": asdict(report),
               "books": [{c: asdict(b)[c] for c in columns} for b in books]}
    _replace(path, lambda tmp: tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8"))


def write_all(books: list[Book], report: RunReport, folder: Path) -> list[Path]:
    paths = [folder / "books.xlsx", folder / "books.csv", folder / "books.json"]
    write_xlsx(books, paths[0])
    write_csv(books, paths[1])
    write_json(books, report, paths[2])
    return paths
