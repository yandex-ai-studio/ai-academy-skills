#!/usr/bin/env python3
"""contract-review: предварительная проверка договора с цитатами."""

import argparse
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402

CHECKS = [
    ("Срок действия", re.compile(r"срок|действует до|вступает в силу|expiration|\bterm\b|effective date|valid until", re.I)),
    ("Ответственность", re.compile(r"ответственност|liability|штраф|penalt|возмещ|убытк|неустойк|\bпени\b|ущерб|компенсац|indemnif|damages", re.I)),
    ("Расторжение", re.compile(r"растор[гж]|terminat|denounc|отказ.{0,30}(?:договор|исполнени)|прекращен|досрочн.{0,25}выход|cancell?ation", re.I)),
    ("Конфиденциальность", re.compile(r"конфиденциальн|confidential|\bnda\b|неразглашен|коммерческ.{0,15}тайн|non.?disclosure", re.I)),
    ("Персональные данные", re.compile(r"персональн|personal data|152[ -]?фз|\bgdpr\b|data protection|субъект.{0,15}данных", re.I)),
    ("Автопролонгация", re.compile(r"автоматическ.{0,60}(?:пролонг|продл)|auto.?renew|продлевается|считается продленным|renew.{0,30}automatically", re.I)),
    ("Форс-мажор", re.compile(r"форс[ -]?мажор|force majeure|непреодолим.{0,15}сил|acts? of god", re.I)),
    ("Подсудность", re.compile(r"подсудност|jurisdiction|арбитраж|подведомственност|спор.{0,50}(?:суд|разреш)|dispute resolution|arbitration", re.I)),
]

PARTIES = re.compile(r"(?:сторон[аы]|party|заказчик|исполнитель|customer|contractor)", re.I)


RISK_SIGNALS = [
    ("Исключение или ограничение ответственности", re.compile(r"не\s+нес[её]т\s+ответственност|не\s+(?:подлежат|подлежит)\s+возмещ|(?:убытки|ущерб).{0,50}не\s+(?:возмещ|компенсир)|освобожда.{0,40}ответственност|ответственност.{0,35}(?<!не )огранич|не\s+отвечает\s+за|(?:компенсаци|возмещени).{0,40}не предусмотрен|not\s+liable|no\s+liability|liability\s+(?:is\s+)?(?:limited|capped)|damages.{0,25}(?:excluded|not recoverable)", re.I)),
    ("Возможное ограничение выхода из договора", re.compile(r"не\s+(?:вправе|может).{0,50}(?:расторг|отказ)|расторжен.{0,30}(?:не\s+допуска|запрещ)|отказ.{0,30}не\s+допуска", re.I)),
    ("Одностороннее изменение условий", re.compile(r"(?:вправе|может|имеет право).{0,60}(?:измен|повыс|пересмотр).{0,35}(?:цен|тариф|услов)|односторонн.{0,50}(?:измен|повыс)|(?:цен|тариф|услов).{0,50}без\s+(?:согласия|уведомления)|(?:may|can).{0,30}(?:change|increase).{0,25}(?:price|fee|terms)", re.I)),
]

PROTECTIVE_CHANGE = re.compile(r"не\s+(?:вправе|может)|не\s+имеет\s+права|(?:измен|повыш|пересмотр).{0,40}(?:не допуска|запрещ)|(?:только|исключительно).{0,25}(?:соглас|соглаш)|\b(?:may not|cannot|must not)\b|only with.{0,20}consent", re.I)


def passages(text):
    return [p.strip() for p in re.split(r"\n+|(?<=[.!?;])\s+(?=[А-ЯЁA-Z])", text) if p.strip()]


def review(text):
    fragments = passages(text)
    sections = []
    for name, pattern in CHECKS:
        quotes = [p for p in fragments if pattern.search(p)]
        sections.append((name, quotes))
    risks = []
    for p in fragments:
        # Split opposing clauses for matching while preserving the original quote.
        parts = re.split(r"\s+(?:но|однако|but|however)\s+|;", p, flags=re.I)
        for label, pattern in RISK_SIGNALS:
            if any(pattern.search(part) and not (label == "Одностороннее изменение условий"
                    and PROTECTIVE_CHANGE.search(part)) for part in parts):
                risks.append((label, p))
    return sections, risks


def main():
    parser = argparse.ArgumentParser(description="Предварительная проверка договора; не юридическое заключение.")
    parser.add_argument("input")
    parser.add_argument("--out", default="contract_memo.md")
    add_manifest_args(parser)
    args = parser.parse_args()
    src = Path(args.input); text = src.read_text(encoding="utf-8-sig")
    sections, risks = review(text)
    lines = ["# Предварительная проверка договора", "", f"Источник: `{src.name}`.",
        "Это список пунктов для ручной проверки и вопросов юристу, а не юридическое заключение. Наличие ключевого слова не означает приемлемость условия; отсутствие совпадения не доказывает отсутствие пункта.",
        "", "## Условия и подтверждающие фрагменты", ""]
    for name, quotes in sections:
        lines += [f"### {name}"]
        lines += ["> " + q.replace("\n", " ") for q in quotes] if quotes else ["Не найдено по словарю — требуется содержательная проверка текста."]
        lines += ["Проверить смысл, отрицания, исключения и перекрёстные ссылки.", ""]
    lines += ["## Потенциальные риски и вопросы юристу", ""]
    for label, quote in risks:
        lines += [f"- **{label}**. Основание: «{quote}». Уточнить у юриста допустимость и последствия именно этого условия для стороны пользователя."]
    if not risks:
        lines.append("Правила не выделили явных сигналов; это не подтверждает отсутствие рисков.")
    lines += ["", "## Следующий шаг", "Содержательно перечитать цитаты и весь договор: перефразированные условия могут не совпасть со словарём. Не делать выводов о применимом праве, законности или неуказанных обязательствах без основания."]
    out = Path(args.out); out.write_text("\n".join(lines)+"\n", encoding="utf-8")
    manifest = Path(args.manifest) if args.manifest else default_manifest_path(out)
    write_manifest(manifest, skill="contract-review", status="warning" if risks else "ok", inputs=[artifact(src,"text","data")], outputs=[artifact(out,"markdown","report")],
        metrics={"unmatched_topics":sum(not q for _,q in sections),"potential_risks":len(risks),"words":len(text.split())}, suggested_next=["pii-redactor","report-builder"])
    print(f"Memo: {out}\nManifest: {manifest}")

if __name__ == "__main__":
    main()
