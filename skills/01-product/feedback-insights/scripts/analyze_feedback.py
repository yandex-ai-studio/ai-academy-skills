#!/usr/bin/env python3
"""feedback-insights: темы, частотность и тональность из CSV отзывов."""

import argparse
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
from tabular import input_artifact_type, load_table, resolve_column  # noqa: E402

POSITIVE = re.compile(r"\b(?:отличн\w*|удобн\w*|быстр\w*|нравится|понравил\w*|рекомендую|"
    r"супер|класс|спасибо|прекрасн\w*|хорош\w*|доволен|довольн\w*|великолепн\w*|"
    r"восхитительн\w*|качественн\w*|порадовал\w*|отзывчив\w*|"
    r"great|excellent|good|love[ds]?|loved|amazing|helpful|reliable|satisfied|easy to use)\b", re.I)
NEGATIVE = re.compile(r"\b(?:плох\w*|ужас\w*|медленн\w*|не\s+(?:работает|запускается|открывается)|"
    r"разочарован\w*|разочаровыва\w*|верну|жалоб\w*|баг(?:и|ов|ом)?|ошиб(?:ка|ки|ок|ку|ками)|"
    r"неудобн\w*|сломал\w*|сбо(?:й|и|ев)|зависает|зависания|тормозит|тормоза|"
    r"проблем(?:а|ы|у|ой|ами)?|груб(?:ый|ая|ое|о|ость)|навязчив\w*|"
    r"bad|terrible|broken|awful|disappointed|disappointing|slow|crashes|crashed|buggy|"
    r"unhelpful|unreliable|doesn['’]t work|does not work)\b", re.I)

STOP = {"и", "в", "на", "с", "по", "для", "что", "как", "это", "не", "но", "из", "у", "к", "а", "то", "же", "или", "при", "от", "до", "за", "о", "об", "бы", "ли", "мы", "вы", "они", "он", "она", "его", "её", "их", "the", "a", "is", "to", "of"}


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{3,}", text.lower())
    return [w for w in words if w not in STOP]


def sentiment(text: str) -> str:
    low = text.casefold().replace("ё", "е")
    pos = neg = 0
    for pattern, positive in ((POSITIVE, True), (NEGATIVE, False)):
        for match in pattern.finditer(low):
            prefix = re.split(r"[.!?;,\n]|\b(?:но|зато|but|however)\b", low[:match.start()])[-1]
            prefix = re.sub(r"\b(?:не только|not only)\s+", "", prefix)
            denied = bool(re.search(r"(?:\bне|\bnot|\bнет|\bбез|\bno|\bwithout)\s+(?:\w+\s+){0,2}$", prefix))
            if positive:
                neg += denied
                pos += not denied
            elif not denied:
                neg += 1
    if pos and neg:
        return "mixed"
    if pos:
        return "positive"
    if neg:
        return "negative"
    return "unknown"


def find_text_column(headers: list[str], rows: list[list[str]]) -> int:
    best_idx, best_score = 0, -1
    for i, h in enumerate(headers):
        score = sum(len(r[i]) for r in rows if i < len(r))
        if "text" in h.lower() or "отзыв" in h.lower() or "comment" in h.lower():
            score += 1000
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx


def main():
    parser = argparse.ArgumentParser(description="Анализ отзывов из CSV/XLSX.")
    parser.add_argument("input", help="CSV или XLSX с текстами отзывов")
    parser.add_argument("--out", default="insights.md", help="Markdown-отчёт")
    parser.add_argument("--text-column", help="Имя колонки с текстом")
    add_manifest_args(parser)
    args = parser.parse_args()

    src = Path(args.input)
    headers, rows = load_table(src)
    if not headers:
        print("Пустой файл.")
        return
    column = resolve_column(headers, ["text", "отзыв", "текст отзыва", "comment", "review", "текст"], args.text_column)
    col_idx = headers.index(column) if column else find_text_column(headers, rows)

    indexed_texts = [(n, r[col_idx]) for n, r in enumerate(rows, 2) if r[col_idx].strip()]
    texts = [t for _, t in indexed_texts]
    sentiments = Counter(sentiment(t) for t in texts)
    tokens = Counter()
    for t in texts:
        tokens.update(tokenize(t))

    lines = [
        "# Голос клиента — insights",
        "",
        f"- Источник: `{src.name}`",
        f"- Отзывов: **{len(texts)}**",
        "",
        "## Тональность",
        "",
        "| Тон | Количество |",
        "| --- | --- |",
    ]
    for tone, count in sentiments.most_common():
        lines.append(f"| {tone} | {count} |")
    lines += ["", "Тональность — предварительная словарная оценка каждой строки: mixed — смешанные сигналы, unknown — данных словаря недостаточно. Unknown не означает нейтральный отзыв.",
              "", "## Частота слов (все вхождения, включая повторы внутри отзыва)", "",
              "Точные токены без лемматизации; частотные слова сами по себе не являются тематическими кластерами."]
    for word, count in tokens.most_common(15):
        lines.append(f"- **{word}** — {count}")
    lines += ["", "## Построчная проверка", "", "| Строка данных | Предварительная тональность | Текст |", "| --- | --- | --- |"]
    for n, t in indexed_texts:
        excerpt = t.replace("|", "\\|").replace("\n", " / ")
        lines.append(f"| {n} | {sentiment(t)} | {excerpt} |")
    lines.append("")
    out_path = Path(args.out)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_path)
    write_manifest(
        manifest_path,
        skill="feedback-insights",
        status="ok",
        inputs=[artifact(src, input_artifact_type(src), "data")],
        outputs=[artifact(out_path, "markdown", "report")],
        metrics={"reviews": len(texts), "empty_reviews": len(rows)-len(texts), "word_counts": dict(tokens), **dict(sentiments)},
        suggested_next=["report-builder"],
    )
    print(f"Отчёт: {out_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
