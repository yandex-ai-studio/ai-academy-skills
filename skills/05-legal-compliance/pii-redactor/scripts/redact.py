#!/usr/bin/env python3
"""pii-redactor: детект и маскирование персональных данных (ПДн).

Только стандартная библиотека Python 3. Никакой сети и сторонних пакетов.

Детектит и маскирует: email, телефоны РФ, номера банковских карт (проверка
Луна), ИНН (10/12, контрольная сумма), СНИЛС (контрольная сумма), паспорт РФ,
IP-адреса. Пишет обезличенную копию и audit-отчёт (Markdown + JSON).

Использование:
    python3 redact.py input.txt --out redacted.txt --report report.md
    python3 redact.py input.csv --mask-mode char   # маскировать символами, не тегом
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402
from tabular import input_artifact_type, is_xlsx, setup_vendor  # noqa: E402


# ---------------------------------------------------------------------------
# Валидаторы (снижают ложные срабатывания на голых цифрах)
# ---------------------------------------------------------------------------

def luhn_ok(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def inn_ok(digits: str) -> bool:
    def check(seq, coeffs):
        s = sum(int(a) * b for a, b in zip(seq, coeffs))
        return (s % 11) % 10

    if len(digits) == 10:
        c = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return check(digits[:9], c) == int(digits[9])
    if len(digits) == 12:
        c1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return check(digits[:10], c1) == int(digits[10]) and check(digits[:11], c2) == int(digits[11])
    return False


def snils_ok(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 11:
        return False
    number, control = digits[:9], int(digits[9:])
    s = sum(int(d) * (9 - i) for i, d in enumerate(number))
    if s < 100:
        expected = s
    elif s in (100, 101):
        expected = 0
    else:
        expected = s % 101
        if expected in (100, 101):
            expected = 0
    return expected == control


# ---------------------------------------------------------------------------
# Правила детекции: (тип, regex, валидатор|None, приоритет)
# Приоритет меньше = важнее при разрешении пересечений.
# ---------------------------------------------------------------------------

RULES = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), None, 1),
    ("CARD", re.compile(r"\b(?:\d[ \-]?){13,19}\b"), lambda m: luhn_ok(re.sub(r"\D", "", m)), 2),
    ("SNILS", re.compile(r"\b\d{3}[ \-]\d{3}[ \-]\d{3}[ \-]\d{2}\b"), snils_ok, 3),
    ("PHONE", re.compile(r"(?:\+7|8)[ \-]?\(?\d{3}\)?[ \-]?\d{3}[ \-]?\d{2}[ \-]?\d{2}\b"), None, 4),
    ("INN", re.compile(r"\b\d{12}\b|\b\d{10}\b"), lambda m: inn_ok(re.sub(r"\D", "", m)), 5),
    ("PASSPORT_RF", re.compile(r"\b\d{2}[ ]?\d{2}[ ]\d{6}\b"), None, 6),
    ("IP", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"), None, 7),
]


def find_spans(text: str):
    """Возвращает непересекающиеся находки: список (start, end, type, value)."""
    candidates = []
    for pii_type, pattern, validator, priority in RULES:
        for match in pattern.finditer(text):
            value = match.group(0)
            if validator and not validator(value):
                continue
            candidates.append((match.start(), match.end(), priority, pii_type, value))

    # Сортируем по позиции, затем по приоритету, затем по длине (длиннее раньше).
    candidates.sort(key=lambda c: (c[0], c[2], -(c[1] - c[0])))

    chosen = []
    occupied_end = -1
    for start, end, _priority, pii_type, value in candidates:
        if start >= occupied_end:
            chosen.append((start, end, pii_type, value))
            occupied_end = end
    return chosen


def mask_value(value: str, pii_type: str, mode: str) -> str:
    if mode == "tag":
        return f"[{pii_type}]"
    # mode == "char": оставляем последние 2 значимых символа, остальное меняем на *
    keep = 2
    def repl(s):
        if len(s) <= keep:
            return "*" * len(s)
        return "*" * (len(s) - keep) + s[-keep:]
    # маскируем только буквенно-цифровые, разделители сохраняем
    return re.sub(r"[A-Za-z0-9]+", lambda m: repl(m.group(0)), value) if "@" not in value else repl(value)


def redact(text: str, mode: str):
    spans = find_spans(text)
    counter = Counter()
    findings = []
    result = []
    cursor = 0
    for start, end, pii_type, value in spans:
        result.append(text[cursor:start])
        result.append(mask_value(value, pii_type, mode))
        cursor = end
        counter[pii_type] += 1
        line = text.count("\n", 0, start) + 1
        findings.append({"type": pii_type, "line": line, "masked_as": mask_value(value, pii_type, mode)})
    result.append(text[cursor:])
    return "".join(result), counter, findings


def build_report(counter: Counter, findings: list, source_name: str, mode: str) -> str:
    total = sum(counter.values())
    lines = [
        "# Предварительное маскирование персональных данных",
        "",
        f"- Источник: `{source_name}`",
        f"- Режим маскирования: `{mode}`",
        f"- Всего найдено ПДн: **{total}**",
        "- Перед передачей файла вручную проверьте пропуски и ложные срабатывания. Полное обезличивание не гарантируется.",
        "- Словарные/числовые правила не покрывают имена, адреса, изображения, комментарии, формулы и метаданные документов.",
        "",
        "## Сводка по типам",
        "",
        "| Тип | Количество |",
        "| --- | --- |",
    ]
    labels = {
        "EMAIL": "E-mail",
        "CARD": "Банковская карта",
        "SNILS": "СНИЛС",
        "PHONE": "Телефон",
        "INN": "ИНН",
        "PASSPORT_RF": "Паспорт РФ",
        "IP": "IP-адрес",
    }
    for pii_type, count in counter.most_common():
        lines.append(f"| {labels.get(pii_type, pii_type)} | {count} |")
    if not counter:
        lines.append("| — | 0 |")
    lines += ["", "## Находки по строкам", ""]
    if findings:
        for f in findings:
            lines.append(f"- строка {f['line']}: {labels.get(f['type'], f['type'])} -> `{f['masked_as']}`")
    else:
        lines.append("_Совпадений с правилами не найдено; персональные данные могут остаться._")
    lines.append("")
    return "\n".join(lines)


def redact_xlsx(src: Path, out_path: Path, mask_mode: str):
    setup_vendor()
    from openpyxl import load_workbook

    wb = load_workbook(src)
    counter: Counter = Counter()
    findings = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None or cell.data_type == "f":
                    continue
                text = str(cell.value)
                if not text.strip():
                    continue
                redacted, sub_counter, sub_findings = redact(text, mask_mode)
                if sub_counter:
                    cell.value = redacted
                counter.update(sub_counter)
                for finding in sub_findings:
                    finding["line"] = f"{ws.title}!{cell.coordinate}"
                findings.extend(sub_findings)
    wb.save(out_path)
    return counter, findings


def main():
    parser = argparse.ArgumentParser(description="Маскирование персональных данных (stdlib-only).")
    parser.add_argument("input", help="Входной файл (txt/csv/xlsx)")
    parser.add_argument("--out", help="Куда писать обезличенную копию (по умолчанию <input>.redacted)")
    parser.add_argument("--report", help="Куда писать Markdown-отчёт (по умолчанию <input>.audit.md)")
    parser.add_argument("--report-json", help="Куда писать JSON-отчёт (опционально)")
    parser.add_argument("--mask-mode", choices=["tag", "char"], default="tag",
                        help="tag: заменить на [TYPE]; char: замаскировать символами *")
    add_manifest_args(parser)
    args = parser.parse_args()

    src = Path(args.input)
    destinations = [args.out, args.report, args.report_json, args.manifest]
    if any(p and Path(p).resolve() == src.resolve() for p in destinations):
        parser.error("Исходный файл нельзя перезаписывать. Укажите отдельную копию и отдельные пути отчётов.")

    if is_xlsx(src):
        out_path = Path(args.out) if args.out else src.with_name(src.stem + ".redacted.xlsx")
        report_path = Path(args.report) if args.report else src.with_suffix(".audit.md")
        counter, findings = redact_xlsx(src, out_path, args.mask_mode)
    else:
        text = src.read_text(encoding="utf-8", errors="replace")
        redacted, counter, findings = redact(text, args.mask_mode)
        out_path = Path(args.out) if args.out else src.with_suffix(src.suffix + ".redacted")
        report_path = Path(args.report) if args.report else src.with_suffix(src.suffix + ".audit.md")
        out_path.write_text(redacted, encoding="utf-8")

    report_md = build_report(counter, findings, src.name, args.mask_mode)
    report_path.write_text(report_md, encoding="utf-8")

    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps({"summary": dict(counter), "findings": findings}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    total = sum(counter.values())
    print(f"Готово. Найдено и замаскировано ПДн: {total}")
    for pii_type, count in counter.most_common():
        print(f"  {pii_type}: {count}")
    print(f"Обезличенная копия: {out_path}")
    print(f"Audit-отчёт: {report_path}")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_path)
    outputs = [
        artifact(out_path, "xlsx" if is_xlsx(src) else "text", "redacted"),
        artifact(report_path, "markdown", "report"),
    ]
    if args.report_json:
        outputs.append(artifact(args.report_json, "json", "report"))
    write_manifest(
        manifest_path,
        skill="pii-redactor",
        status="ok",
        inputs=[artifact(src, input_artifact_type(src) if is_xlsx(src) else "text", "data")],
        outputs=outputs,
        metrics={"pii_total": total, **dict(counter)},
        suggested_next=["report-builder"],
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
