#!/usr/bin/env python3
"""engagement-survey: eNPS и метрики вовлечённости из CSV опроса."""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402
from tabular import input_artifact_type, load_table, normalize_header  # noqa: E402

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


def to_score(value: str):
    try:
        s = float(str(value).replace(",", "."))
        if 0 <= s <= 10:
            return s
    except ValueError:
        return None
    return None


def enps(scores: list[float]) -> float:
    if not scores:
        return None
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round((promoters - detractors) / len(scores) * 100, 1)


def main():
    parser = argparse.ArgumentParser(description="Аналитика опроса вовлечённости.")
    parser.add_argument("input", help="CSV или XLSX опроса")
    parser.add_argument("--out", default="survey_report.md", help="Markdown-отчёт")
    parser.add_argument("--chart", default="enps_chart.png", help="PNG-график распределения")
    parser.add_argument("--score-column", help="Колонка со шкалой 0-10")
    parser.add_argument("--enps-question", help="Точная формулировка вопроса о рекомендации работодателя")
    parser.add_argument("--enps-scale", choices=["0-10"], help="Подтверждённая шкала вопроса eNPS")
    parser.add_argument("--value-columns", nargs="+", help="Колонки вопросов для агрегированных средних")
    parser.add_argument("--min-group-size", type=int, default=5, help="Минимум ответов для публикации статистики (не менее 5)")
    add_manifest_args(parser)
    args = parser.parse_args()
    if args.min_group_size < 5:
        parser.error("Минимальная группа — 5; для меньших групп статистика скрывается.")

    src = Path(args.input)
    headers, rows = load_table(src)
    if not headers:
        print("Пустой файл.")
        return

    if args.score_column and args.score_column not in headers:
        parser.error(f"Колонка {args.score_column!r} не найдена")
    question = args.enps_question or ""
    question_ok = bool(re.search(r"рекоменд|recommend", question, re.I) and re.search(r"работодател|мест.{0,8}работ|employer|workplace|work", question, re.I))
    score_idx = headers.index(args.score_column) if args.score_column else None
    enps_enabled = score_idx is not None and args.enps_scale == "0-10" and question_ok
    scores = [s for r in rows if (s := to_score(r[score_idx])) is not None and float(s).is_integer()] if enps_enabled else []
    can_report_enps = enps_enabled and len(scores) >= args.min_group_size
    enps_value = enps(scores) if can_report_enps else None
    invalid_scores = len(rows) - len(scores) if enps_enabled else None
    if args.value_columns and any(c not in headers for c in args.value_columns):
        parser.error("Одна из --value-columns отсутствует в файле")
    block_avgs = defaultdict(list)
    for r in rows:
        for i, h in enumerate(headers):
            if i == score_idx or "nps" in h.casefold():
                continue
            if re.search(r"\bid\b|идентификатор|возраст|пол\b|gender|age\b|имя|фио|name|телефон|phone|email", normalize_header(h)):
                continue
            if args.value_columns and h not in args.value_columns:
                continue
            val = to_score(r[i] if i < len(r) else "")
            if val is not None:
                block_avgs[h].append(val)

    lines = [
        "# Аналитика опроса вовлечённости",
        "",
        f"- Источник: `{src.name}`",
        f"- Ответов: **{len(rows)}**",
        f"- eNPS: **{enps_value}** (n={len(scores)}, вопрос: {question}; шкала 0–10)" if can_report_enps else "- eNPS не рассчитан: нужен вопрос о рекомендации работодателя, подтверждённая шкала 0–10 и достаточное число ответов.",
        f"- Минимум для публикации среднего или eNPS: {args.min_group_size} ответов. Индивидуальные оценки и малые группы не публикуются.",
        "",
        "## Средние по блокам",
        "",
    ]
    for block, vals in sorted(block_avgs.items()):
        if len(vals) < args.min_group_size:
            lines.append(f"- **{block}**: статистика скрыта — малая группа.")
            continue
        avg = round(sum(vals) / len(vals), 2) if vals else 0
        lines.append(f"- **{block}**: {avg} (n={len(vals)})")
    lines.append("")

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    outputs = [artifact(out_path, "markdown", "report")]

    if plt and can_report_enps:
        chart_path = Path(args.chart)
        plt.figure(figsize=(6, 4))
        plt.hist(scores, bins=11, range=(0, 10), edgecolor="black")
        plt.title("Распределение оценок")
        plt.xlabel("Балл")
        plt.ylabel("Количество")
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        outputs.append(artifact(chart_path, "png", "chart"))
        print(f"График: {chart_path}")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_path)
    write_manifest(
        manifest_path,
        skill="engagement-survey",
        status="warning" if (not can_report_enps or invalid_scores) else "ok",
        inputs=[artifact(src, input_artifact_type(src), "data")],
        outputs=outputs,
        metrics={"responses": len(rows), "enps": enps_value, "invalid_enps_scores": invalid_scores, "min_group_size": args.min_group_size},
        suggested_next=["report-builder"],
    )
    print(f"Отчёт: {out_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
