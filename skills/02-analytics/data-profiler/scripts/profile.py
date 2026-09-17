#!/usr/bin/env python3
"""data-profiler: профайлинг датасета и проверка качества данных (EDA).

Только стандартная библиотека Python 3. Никакой сети и сторонних пакетов
(pandas НЕ требуется).

Читает CSV, определяет типы колонок, считает статистику, ищет проблемы качества
(пропуски, константные колонки, высокая кардинальность, выбросы, дубли строк) и
формирует отчёт в Markdown (+опционально HTML).

Использование:
    python3 profile.py data.csv --out report.md
    python3 profile.py data.csv --out report.md --html report.html
"""

import argparse
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402
from tabular import input_artifact_type, load_table  # noqa: E402

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "—"}
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S")
TRUE_TOKENS = {"true", "yes", "да", "1", "y"}
FALSE_TOKENS = {"false", "no", "нет", "0", "n"}


def is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_TOKENS


def try_int(value: str):
    try:
        return int(value)
    except ValueError:
        return None


def try_float(value: str):
    try:
        return float(value.replace(",", ".")) if value.count(",") == 1 and "." not in value else float(value)
    except ValueError:
        return None


def try_date(value: str):
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value.strip()):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def infer_type(values):
    """Определяем тип колонки по непустым значениям."""
    non_missing = [v for v in values if not is_missing(v)]
    if not non_missing:
        return "empty"

    if all(v.strip().lower() in TRUE_TOKENS | FALSE_TOKENS for v in non_missing):
        return "boolean"
    if all(try_int(v) is not None for v in non_missing):
        return "integer"
    if all(try_float(v) is not None for v in non_missing):
        return "float"
    if all(try_date(v) is not None for v in non_missing):
        return "timestamp" if any(re.search(r"[T ]\d{2}:\d{2}", v) for v in non_missing) else "date"
    return "categorical"


def numeric_values(values):
    result = []
    for v in values:
        if is_missing(v):
            continue
        f = try_float(v)
        if f is not None:
            result.append(f)
    return result


def outliers_iqr(nums):
    if len(nums) < 4:
        return 0, None, None
    q1, _, q3 = statistics.quantiles(nums, n=4)
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    count = sum(1 for x in nums if x < low or x > high)
    return count, low, high


def profile_column(name, values):
    total = len(values)
    missing = sum(1 for v in values if is_missing(v))
    present = [v for v in values if not is_missing(v)]
    unique = len(set(present))
    col_type = infer_type(values)

    info = {
        "name": name,
        "type": col_type,
        "count": total,
        "missing": missing,
        "missing_pct": round(missing / total * 100, 1) if total else 0.0,
        "unique": unique,
    }

    if col_type in ("integer", "float"):
        nums = numeric_values(values)
        if nums:
            info.update({
                "min": min(nums),
                "max": max(nums),
                "mean": round(statistics.fmean(nums), 4),
                "median": statistics.median(nums),
                "std": round(statistics.pstdev(nums), 4) if len(nums) > 1 else 0.0,
            })
            out_count, low, high = outliers_iqr(nums)
            info["outliers"] = out_count
            info["outlier_bounds"] = (round(low, 4), round(high, 4)) if low is not None else None
    else:
        freq = {}
        for v in present:
            freq[v] = freq.get(v, 0) + 1
        top = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:5]
        info["top_values"] = top

    return info


def collect_warnings(columns, dup_rows, n_rows):
    warnings = []
    for c in columns:
        if c["missing_pct"] >= 50:
            warnings.append(f"Колонка `{c['name']}`: пропусков {c['missing_pct']}% (высокий уровень).")
        if c["type"] != "empty" and c["unique"] <= 1 and c["count"] - c["missing"] > 0:
            warnings.append(f"Колонка `{c['name']}`: константная (все значения одинаковы).")
        if c["type"] == "categorical" and c["count"] and c["unique"] == c["count"] - c["missing"] and c["unique"] > 1:
            warnings.append(f"Колонка `{c['name']}`: все значения уникальны (похоже на идентификатор).")
        if c.get("outliers"):
            warnings.append(f"Колонка `{c['name']}`: выбросов по IQR — {c['outliers']}.")
        if c["type"] == "empty":
            warnings.append(f"Колонка `{c['name']}`: полностью пустая.")
    if dup_rows:
        warnings.append(f"Дубли строк: {dup_rows} ({round(dup_rows / n_rows * 100, 1)}%).")
    return warnings


def build_markdown(source, headers, rows, columns, dup_rows, warnings):
    n_rows = len(rows)
    total_cells = n_rows * len(headers) if headers else 0
    missing_cells = sum(c["missing"] for c in columns)
    missing_pct = round(missing_cells / total_cells * 100, 1) if total_cells else 0.0

    lines = [
        "# Профайлинг датасета",
        "",
        f"- Источник: `{source}`",
        f"- Строк: **{n_rows}**",
        f"- Колонок: **{len(headers)}**",
        f"- Дубли строк: **{dup_rows}**",
        f"- Пропущенных ячеек: **{missing_cells}** ({missing_pct}%)",
        "",
        "## Колонки",
        "",
        "| Колонка | Тип | Пропуски | Уникальных | Статистика |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in columns:
        if c["type"] in ("integer", "float") and "mean" in c:
            stat = f"min={c['min']}, max={c['max']}, mean={c['mean']}, median={c['median']}, std={c['std']}, выбросы={c.get('outliers', 0)}"
        elif c.get("top_values"):
            stat = "топ: " + ", ".join(f"{val}={cnt}" for val, cnt in c["top_values"])
        else:
            stat = "—"
        lines.append(
            f"| {c['name']} | {c['type']} | {c['missing']} ({c['missing_pct']}%) | {c['unique']} | {stat} |"
        )

    lines += ["", "## Проблемы качества данных", ""]
    if warnings:
        lines += [f"- {w}" for w in warnings]
    else:
        lines.append("_Существенных проблем не обнаружено._")
    lines.append("")
    return "\n".join(lines)


def build_html(markdown_text):
    body = (
        markdown_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>Профайлинг датасета</title>"
        "<style>body{font-family:system-ui,Arial,sans-serif;max-width:960px;margin:40px auto;padding:0 16px;}"
        "pre{white-space:pre-wrap;line-height:1.5;}</style></head>"
        f"<body><pre>{body}</pre></body></html>"
    )


def main():
    parser = argparse.ArgumentParser(description="Профайлинг CSV/XLSX-датасета.")
    parser.add_argument("input", help="Входной CSV или XLSX")
    parser.add_argument("--out", help="Куда писать Markdown-отчёт (по умолчанию <input>.profile.md)")
    parser.add_argument("--html", help="Дополнительно сохранить HTML-версию по этому пути")
    parser.add_argument("--delimiter", default=None, help="Разделитель CSV (по умолчанию автоопределение)")
    add_manifest_args(parser)
    args = parser.parse_args()

    src = Path(args.input)
    headers, rows = load_table(src, delimiter=args.delimiter)
    if not headers:
        print("Пустой файл.")
        return

    # Транспонируем в колонки (выравниваем длину строк по числу заголовков).
    cols_values = [[] for _ in headers]
    for row in rows:
        for i in range(len(headers)):
            cols_values[i].append(row[i] if i < len(row) else "")

    columns = [profile_column(headers[i], cols_values[i]) for i in range(len(headers))]

    seen = set()
    dup_rows = 0
    for row in rows:
        key = tuple(row)
        if key in seen:
            dup_rows += 1
        else:
            seen.add(key)

    warnings = collect_warnings(columns, dup_rows, len(rows) or 1)
    markdown_text = build_markdown(src.name, headers, rows, columns, dup_rows, warnings)

    out_path = Path(args.out) if args.out else src.with_suffix(src.suffix + ".profile.md")
    out_path.write_text(markdown_text, encoding="utf-8")

    if args.html:
        Path(args.html).write_text(build_html(markdown_text), encoding="utf-8")

    print(f"Готово. Строк: {len(rows)}, колонок: {len(headers)}, дубли: {dup_rows}.")
    print(f"Проблем качества отмечено: {len(warnings)}.")
    print(f"Отчёт: {out_path}")
    if args.html:
        print(f"HTML: {args.html}")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_path)
    outputs = [artifact(out_path, "markdown", "report")]
    if args.html:
        outputs.append(artifact(args.html, "html", "report"))
    write_manifest(
        manifest_path,
        skill="data-profiler",
        status="ok",
        inputs=[artifact(src, input_artifact_type(src), "data")],
        outputs=outputs,
        metrics={"rows": len(rows), "columns": len(headers), "duplicates": dup_rows, "issues": len(warnings), "column_types": {c["name"]: c["type"] for c in columns}},
        suggested_next=["pii-redactor", "report-builder"],
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
