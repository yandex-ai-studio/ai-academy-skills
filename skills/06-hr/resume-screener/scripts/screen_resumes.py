#!/usr/bin/env python3
"""resume-screener: сопоставление требований и свидетельств в резюме."""

import argparse
import csv
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402


STOP = {"опыт", "работы", "работа", "работать", "работал", "работала", "знание", "знания", "требуется", "требования", "навыки", "умение", "владение", "лет", "года", "год", "with", "and", "the", "experience", "required", "будет", "плюсом", "на", "по", "от", "до", "из", "of", "in", "to", "knowledge", "skills", "using"}
SENSITIVE = re.compile(r"возраст|дата рождения|пол\s*[:—-]|мужчин|женщин|национальност|религи|семейн|инвалидност|pregnan|gender|age\s*[:—-]", re.I)
NEGATION = re.compile(r"\bне\s+(?:знаком\w*|знаю|работал\w*|использовал\w*|владею|имею|доводилось|приходилось)|\bнет\s+(?:опыта|знаний)|\bбез\s+опыта|\bопыт\w*.{0,20}отсутствует|\bno\s+(?:practical\s+)?experience|\bnot\s+(?:familiar|used|worked)|\bnever\s+(?:used|worked)|\bhave(?:n't| not)\s+(?:used|worked)", re.I)
LEARNING = re.compile(r"хочу\s+(?:освоить|изучить)|планирую\s+(?:освоить|изучить)|только\s+теори|изучаю|прохожу\s+курс|\b(?:learning|plan to learn|want to learn|theoretical only)\b", re.I)
# Aliases are spelling equivalents, not inferred related skills (SQL != NoSQL,
# Python != pandas). Replacement is used only for matching; quotes stay untouched.
ALIASES = {
    "python": r"python|питон(?:а|ом|е)?|пайтон(?:а|ом|е)?",
    "javascript": r"javascript|java\s*script|js|джаваскрипт",
    "typescript": r"typescript|type\s*script|ts|тайпскрипт",
    "postgresql": r"postgresql|postgres|постгрес(?:а|ом)?",
    "excel": r"excel|эксель|экселе|экселем",
    "powerbi": r"power\s*bi|пауэр\s*би",
    "1c": r"[1]с|1c",
    "c++": r"c\+\+|си\s*плюс\s*плюс",
    "c#": r"c#|c\s*sharp|си\s*шарп",
    "dotnet": r"\.net|dotnet|dot\s*net",
    "kubernetes": r"kubernetes|k8s|кубернетес",
    "golang": r"golang|go",
}


def keywords(text):
    text = text.casefold().replace("ё", "е")
    for canonical, pattern in ALIASES.items():
        text = re.sub(r"(?<![\w+#])(?:" + pattern + r")(?![\w+#])", lambda _: canonical, text)
    words = (w.strip(".") for w in re.findall(r"[a-zа-я0-9][a-zа-я0-9+#.]*", text))
    return {w for w in words if w not in STOP and len(w) > 1}


def clauses(text):
    # A comma before a new predicate separates experience statements, but a list
    # of technologies after one denial remains together: "без опыта SQL, Python".
    parts = re.split(r"[\n;]+|(?<=[.!?])\s+|,?\s+(?:но|зато|but|however)\s+|,\s*(?=[^,;.!?]{0,55}\b(?:использовал\w*|работал\w*|знаю|владею|изучаю|used|worked)\b)", text, flags=re.I)
    return [x.strip() for x in parts if x.strip() and not SENSITIVE.search(x)]


def requirements(text):
    lines = [line.strip(" -*•\t") for line in text.splitlines() if line.strip() and not SENSITIVE.search(line)]
    return [part.strip() for line in lines for part in re.split(r"[,;]", line) if keywords(part) and not part.strip().endswith(":" )]


def inspect_requirement(requirement, text):
    terms = keywords(requirement)
    evidence = [c for c in clauses(text) if terms & keywords(c)]
    if not evidence:
        return "нет данных", "", "Есть ли опыт по требованию «" + requirement + "»? Приведите пример."
    denied = [c for c in evidence if NEGATION.search(c)]
    learning = [c for c in evidence if c not in denied and LEARNING.search(c)]
    positive = [c for c in evidence if c not in denied and c not in learning]
    if denied and positive:
        status = "противоречивые сведения — уточнить"
    elif denied:
        status = "явное отрицание опыта"
    elif learning and not positive:
        status = "планы или обучение — опыт не подтвержден"
    else:
        status = "упоминание — проверить содержание и уровень"
    return status, " / ".join(evidence), "Какой у вас практический опыт по требованию «" + requirement + "»? Уточните контекст и результат."


def main():
    parser = argparse.ArgumentParser(description="Сопоставление резюме с вакансией без рейтинга кандидатов.")
    parser.add_argument("--job", required=True)
    parser.add_argument("--resumes", nargs="+", required=True)
    parser.add_argument("--requirements", help="JSON-массив профессиональных требований, если описание вакансии неоднозначно")
    parser.add_argument("--out-csv", default="resume_evidence.csv")
    parser.add_argument("--report", default="resume_evidence.md")
    add_manifest_args(parser)
    args = parser.parse_args()
    import json
    job = Path(args.job).read_text(encoding="utf-8-sig")
    reqs = json.loads(Path(args.requirements).read_text()) if args.requirements else requirements(job)
    if not isinstance(reqs, list) or not all(isinstance(x, str) for x in reqs):
        parser.error("--requirements должен содержать массив строк")
    reqs = [r for r in reqs if not SENSITIVE.search(r)]
    if not reqs:
        parser.error("Не найдены профессиональные требования. Укажите --requirements.")
    results = []
    for resume in args.resumes:
        text = Path(resume).read_text(encoding="utf-8-sig")
        for requirement in reqs:
            status, evidence, question = inspect_requirement(requirement, text)
            results.append(dict(resume=Path(resume).name, requirement=requirement, status=status, evidence=evidence, interview_question=question))
    out = Path(args.out_csv)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["resume", "requirement", "status", "evidence", "interview_question"])
        writer.writeheader(); writer.writerows(results)
    lines = ["# Сопоставление резюме с требованиями", "", "Порядок кандидатов сохранён как во входе. Баллы, рейтинг, автоматический отбор и отказы не формируются.",
        "Совпадение слов не подтверждает навык. Фрагменты ниже — материал для содержательной проверки человеком; отсутствие данных не означает отсутствие опыта.",
        "Возраст, пол и другие нерелевантные признаки исключены из анализа.", "", "| Резюме | Требование | Статус | Фрагмент | Вопрос для интервью |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in r.values()) + " |")
    report = Path(args.report); report.write_text("\n".join(lines)+"\n", encoding="utf-8")
    manifest = Path(args.manifest) if args.manifest else default_manifest_path(out)
    write_manifest(manifest, skill="resume-screener", inputs=[artifact(args.job,"text","data")]+[artifact(p,"text","data") for p in args.resumes],
        outputs=[artifact(out,"csv","report"),artifact(report,"markdown","report")], metrics={"candidates":len(args.resumes),"requirements":len(reqs)}, suggested_next=["report-builder"])
    print(f"CSV: {out}\nОтчёт: {report}\nManifest: {manifest}")

if __name__ == "__main__":
    main()
