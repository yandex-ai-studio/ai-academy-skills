#!/usr/bin/env python3
"""bank-statement-parser: категоризация банковской выписки CSV."""

import argparse
import csv
import json
import re
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
from finance import add_columns_arg, parse_amount, read_transactions

def normalized(text):
    return re.sub(r"\s+", " ", text.casefold().replace("ё", "е")).strip()


# Specific purpose precedes payment channel. SBP/card-to-card alone says nothing
# about the economic purpose of a payment; keep it for review, never call it revenue.
COMMON = [
    ("Комиссии", r"комисси|\b(?:fee|fees|bank charge)\b|обслуживание счета", "expense"),
    ("Между своими счетами", r"между (?:своими|собственными) счетами|на (?:свой|собственный) счет|перевод собственных средств|\bown accounts?\b", "any"),
    ("Возвраты", r"возврат.{0,35}(?:средств|платеж|оплат|покуп|товар)|\brefund\w*\b|\bchargeback\b", "any"),
    ("Кредиты и займы", r"\bкредит\w*|\bзайм\w*|\bзаем\w*|\b(?:loan|mortgage|credit repayment)\b|ипотек", "any"),
    ("Налоги", r"\bналог\w*|\b(?:tax|taxes|фнс|ндфл|усн|енс)\b|страховые взносы", "any"),
]
TRANSFER = ("Переводы — назначение не уточнено", r"\bперевод\w*|\b(?:transfer|p2p|c2c|сбп)\b|систем[аы] быстрых платежей|с карты на карту|card.to.card", "any")
PROFILES = {
    "business": COMMON + [
        ("Выручка", r"выручк|продаж|эквайринг|оплат.{0,25}клиент|поступлен.{0,25}покупател|\b(?:revenue|sales|acquiring)\b", "income"),
        ("Аренда", r"\bаренд\w*|\brent\b|\blease payment\b", "any"),
        ("Зарплата", r"зарплат|заработн\w* плат|\b(?:salary|payroll)\b", "expense"),
        ("Поставщики и подрядчики", r"поставщик|подрядчик|оплата по (?:счету|договору)|\b(?:supplier|vendor|contractor|invoice)\b", "expense"),
        ("ПО и сервисы", r"подписк|лицензи|хостинг|облачн\w* сервис|\b(?:subscription|saas|hosting|software)\b", "expense"),
        ("Связь и интернет", r"интернет|мобильн\w* связь|телефони|\b(?:internet|telecom)\b", "expense"),
        ("Командировки", r"командиров|делов\w* поездк|\bbusiness trip\b", "expense"),
        TRANSFER,
    ],
    "personal": COMMON + [
        ("Зарплата и доход от работы", r"зарплат|заработн\w* плат|\b(?:salary|payroll)\b", "income"),
        ("Пенсии и пособия", r"пенси|пособи|\b(?:pension|benefit payment)\b", "income"),
        ("Жильё и ЖКХ", r"\bаренд\w*|\brent\b|\b(?:жкх|жку|utility|utilities)\b|квартплат|коммунальн", "expense"),
        ("Подписки", r"подписк|\b(?:subscription|netflix|spotify)\b", "expense"),
        ("Продукты и кафе", r"ресторан|кафе|кофейн|супермаркет|продуктов\w* магазин|доставка еды|\b(?:coffee|restaurant|grocery|groceries)\b", "expense"),
        ("Транспорт", r"\bтакси\b|\bметро\b|\bазс\b|бензин|парковк|\b(?:taxi|fuel|parking)\b", "expense"),
        ("Здоровье", r"аптек|клиник|стоматолог|\b(?:pharmacy|clinic|dentist)\b", "expense"),
        ("Связь и интернет", r"интернет|мобильн\w* связь|\b(?:internet|telecom)\b", "expense"),
        TRANSFER,
    ],
}


def load_rules(path):
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("--rules: ожидается JSON-массив правил")
    for rule in data:
        if (not isinstance(rule, dict) or not isinstance(rule.get("category"), str)
                or not rule["category"].strip()
                or not isinstance(rule.get("contains_any"), list) or not rule["contains_any"]
                or not all(isinstance(x, str) and x.strip() for x in rule["contains_any"])
                or rule.get("direction", "any") not in ("any", "income", "expense")):
            raise ValueError("--rules: правило требует category, непустой contains_any и direction any/income/expense")
    return data


def direction_matches(direction, amount):
    return (direction == "any" or amount is None
            or direction == "income" and amount > 0
            or direction == "expense" and amount < 0)


def classify(description, amount=None, profile="business", rules=()):
    text = normalized(description)
    for rule in rules:
        if (direction_matches(rule.get("direction", "any"), amount)
                and any(normalized(word) in text for word in rule["contains_any"])):
            return rule["category"].strip(), "user_rule"
    for name, pattern, direction in PROFILES[profile]:
        if direction_matches(direction, amount) and re.search(pattern, text):
            return name, "dictionary:" + profile
    return "Прочее", "unmatched"


def categorize(description: str, amount=None, profile="business", rules=()) -> str:
    return classify(description, amount, profile, rules)[0]


def main():
    parser = argparse.ArgumentParser(description="Разбор банковской выписки CSV/XLSX.")
    parser.add_argument("input", help="CSV или XLSX выписки")
    parser.add_argument("--out-csv", default="categorized.csv", help="CSV с категориями")
    parser.add_argument("--report", default="reconciliation.md", help="Markdown-сверка")
    parser.add_argument("--profile", choices=PROFILES, default="business", help="Назначение категорий; по умолчанию business")
    parser.add_argument("--rules", help="JSON с пользовательскими категориями и строками для поиска")
    add_manifest_args(parser)
    add_columns_arg(parser)
    args = parser.parse_args()

    src = Path(args.input)
    try:
        rules = load_rules(args.rules)
        transactions, mapping = read_transactions(src, args.columns)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    fieldnames = list(transactions[0]["source"])
    if "category" not in fieldnames:
        fieldnames.append("category")
    if "amount_normalized" not in fieldnames:
        fieldnames.append("amount_normalized")
    if "category_source" not in fieldnames:
        fieldnames.append("category_source")
    out_rows = []
    totals = defaultdict(Decimal)
    uncategorized = 0
    review_rows = []
    for tx in transactions:
        row = dict(tx["source"])
        amount = tx["amount"]
        cat, source = ((tx["category"], "input") if tx["category"] else
                       classify(tx["description"], amount, args.profile, rules))
        uncategorized += cat == "Прочее"
        if source == "unmatched" or (cat == TRANSFER[0] and source.startswith("dictionary:")):
            review_rows.append((len(out_rows) + 2, tx["description"], amount))
        row["category"] = cat
        row["category_source"] = source
        row["amount_normalized"] = str(amount)
        out_rows.append(row)
        totals[cat] += amount

    out_csv = Path(args.out_csv)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    lines = ["# Сверка банковской выписки", "", f"- Источник: `{src.name}`", f"- Операций: **{len(out_rows)}**",
             f"- Профиль: **{args.profile}**", f"- Пользовательских правил: {len(rules)}", "", "## По категориям", ""]
    for cat, total in sorted(totals.items(), key=lambda x: -abs(x[1])):
        lines.append(f"- **{cat}**: {total:,.2f}")
    lines += ["", f"Итого: {sum(totals.values()):,.2f}", f"Не распознано категорий: {uncategorized}.",
              "Приоритет: входная категория → первое пользовательское правило → словарь профиля. Источник записан в category_source.",
              f"Требуют уточнения назначения: {len(review_rows)} из {len(out_rows)} ({len(review_rows)/len(out_rows):.1%}).",
              "СБП/P2P обозначают канал перевода, а не выручку или конкретную статью расходов. Категории — предварительная аналитика, не бухгалтерские проводки.",
              "Сверка относится к суммам выгрузки; без остатков и независимого источника полнота выписки не подтверждена.",
              f"Соответствие колонок: {mapping}"]
    if review_rows:
        lines += ["", "## Операции для уточнения", ""]
        lines += [f"- Строка {n}: {description.replace(chr(10), ' ')}; сумма {amount}" for n, description, amount in review_rows]
    lines.append("")
    report_path = Path(args.report)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_csv)
    write_manifest(
        manifest_path,
        skill="bank-statement-parser",
        status="warning" if review_rows else "ok",
        inputs=[artifact(src, input_artifact_type(src), "data")],
        outputs=[
            artifact(out_csv, "csv", "data"),
            artifact(report_path, "markdown", "report"),
        ],
        metrics={"transactions": len(out_rows), "categories": len(totals), "uncategorized": uncategorized,
                 "needs_review": len(review_rows), "profile": args.profile, "custom_rules": len(rules), "total": str(sum(totals.values()))},
        suggested_next=["fin-model-builder", "report-builder"],
    )
    print(f"CSV: {out_csv}")
    print(f"Отчёт: {report_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
