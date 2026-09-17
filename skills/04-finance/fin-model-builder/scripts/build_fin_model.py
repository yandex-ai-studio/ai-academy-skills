#!/usr/bin/env python3
"""fin-model-builder: помесячный P&L pivot из транзакций CSV."""

import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402
from tabular import input_artifact_type  # noqa: E402
from finance import add_columns_arg, parse_amount, parse_month, read_transactions


parse_date = parse_month


def main():
    parser = argparse.ArgumentParser(description="Помесячный отчёт о доходах и расходах из CSV/XLSX.")
    parser.add_argument("input", help="CSV или XLSX транзакций / categorized")
    parser.add_argument("--out-csv", default="pl_pivot.csv", help="Pivot CSV")
    parser.add_argument("--report", default="pl_report.md", help="Markdown P&L")
    add_manifest_args(parser)
    add_columns_arg(parser)
    args = parser.parse_args()

    src = Path(args.input)
    try:
        rows, mapping = read_transactions(src, args.columns, require_date=True)
    except ValueError as exc:
        parser.error(str(exc))
    pivot = defaultdict(lambda: defaultdict(Decimal))
    uncategorized = 0
    for row in rows:
        month = row["month"]
        cat = row["category"] or "Без категории"
        uncategorized += not bool(row["category"])
        amount = row["amount"]
        pivot[cat][month] += amount

    months = sorted({m for cats in pivot.values() for m in cats})
    out_csv = Path(args.out_csv)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["category"] + months)
        for cat in sorted(pivot):
            writer.writerow([cat] + [round(pivot[cat].get(m, 0), 2) for m in months])

    lines = ["# Отчёт о доходах и расходах из выгрузки", "", f"- Источник: `{src.name}`",
             "- Группировка по датам платежей: основа P&L, без корректировок на начисления, займы и переводы. Это не полноценная финансовая модель.",
             "- Использованы категории входного файла; пропуски выделены как «Без категории» для ручного уточнения.",
             f"- Соответствие колонок: {mapping}", "", "| Категория | " + " | ".join(months) + " |", "| --- | " + " | ".join(["---"] * len(months)) + " |"]
    for cat in sorted(pivot):
        vals = " | ".join(f"{pivot[cat].get(m, 0):,.2f}" for m in months)
        lines.append(f"| {cat} | {vals} |")
    lines.append("| Итого | " + " | ".join(f"{sum(pivot[c].get(m, 0) for c in pivot):,.2f}" for m in months) + " |")
    lines.append("")
    report_path = Path(args.report)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_csv)
    write_manifest(
        manifest_path,
        skill="fin-model-builder",
        status="warning" if uncategorized else "ok",
        inputs=[artifact(src, input_artifact_type(src), "data")],
        outputs=[
            artifact(out_csv, "csv", "model"),
            artifact(report_path, "markdown", "report"),
        ],
        metrics={"categories": len(pivot), "months": len(months), "uncategorized": uncategorized, "total": str(sum(r["amount"] for r in rows))},
        suggested_next=["report-builder"],
    )
    print(f"Pivot: {out_csv}")
    print(f"Отчёт: {report_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
