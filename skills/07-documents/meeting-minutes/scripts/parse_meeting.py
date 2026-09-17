#!/usr/bin/env python3
"""meeting-minutes: action items, решения и открытые вопросы из протокола встречи."""

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

ACTION_PREFIX = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:action|задача|todo|to-do|follow-up|follow up|"
    r"следующий шаг|action item|поручение|к выполнению|действие)\s*[:—-]\s*(.+)$",
    re.I,
)
CHECKBOX = re.compile(r"^\s*(?:[-*•]\s*)?\[(?:\s|x|X)\]\s*(.+)$")
DECISION_PREFIX = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:решени(?:е|я)|decision|итог|agreed|договорились|consensus|утверждено|постановили)\s*[:—-]\s*(.+)$",
    re.I,
)
QUESTION_PREFIX = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:вопрос|question|tbd|открытый вопрос|open question|требует уточнения|на уточнение)\s*[:—-]\s*(.+)$",
    re.I,
)
SKIP_LINE = re.compile(
    r"^\s*(?:протокол|дата|повестка|agenda|meeting|notes|time|время)\s*[:—-]",
    re.I,
)
ASSIGNEE_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\.\s]{1,40}?)\s*[:—]\s*(.+)$",
)
SKIP_ASSIGNEE_NAMES = {
    "участники", "повестка", "agenda", "notes", "протокол", "дата", "решение",
    "decision", "follow-up", "follow up", "action", "todo", "вопрос", "итог",
}
PARTICIPANTS = re.compile(
    r"^(?:участник|present|attendees|участники|на встрече|присутствовали|participants)\s*[:—-]\s*(.+)$",
    re.I,
)
OWNER = re.compile(
    r"(?:@|ответственн(?:ый|ая)?|owner|assignee|исполнитель)\s*[:—]?\s*"
    r"([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\.]*(?:\s+(?!(?:до|к|срок|deadline|by)\b)[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\.]*){0,2})",
    re.I,
)
DEADLINE = re.compile(
    r"\b(?:до|к|deadline|срок|due|by)\s*[:.]?\s*"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[\./]\d{1,2}(?:[\./]\d{2,4})?|\d{1,2}\s+(?:январ|феврал|март|апрел|"
    r"ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*(?:\s+\d{4})?|"
    r"(?:концу|конца)\s+(?:дня|недели|месяца)|(?:следующ\w*\s+)?(?:понедельник\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)|"
    r"завтра|сегодня|tomorrow|today|(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday)|end of (?:day|week|month))\b",
    re.I,
)
FUTURE_VERBS = (r"подготовит|пришл[её]т|проверит|отправит|сделает|обновит|согласует|"
                r"организует|предоставит|собер[её]т|разошл[её]т|протестирует|созвонится|"
                r"уточнит|доработает|исправит|запланирует|сверит|возьм[её]т|will")
TASK_START = re.compile(r"^(?:" + FUTURE_VERBS + r"|подготовлю|отправлю|сделаю|проверю|уточню|"
    r"организую|пришлю|соберу|подготовить|проверить|отправить|обновить|согласовать|"
    r"собрать|разослать|организовать|предоставить|уточнить|протестировать|исправить|"
    r"доработать|send|prepare|check|update|review|schedule|test|i will)\b", re.I)
PROPOSAL = re.compile(r"\b(?:предлагаю|предложил\w*|возможно|может быть|не будем|не решили|might|maybe|suggest|could)\b", re.I)


def parse_owner_deadline(text: str) -> tuple[str, str, str]:
    owner = ""
    deadline = ""
    owner_match = OWNER.search(text)
    if owner_match:
        owner = owner_match.group(1).strip(" .,")
        owner = re.split(r"\s+(?:до|к|срок|deadline|by)\b", owner, flags=re.I)[0].strip()
    deadline_match = DEADLINE.search(text)
    if deadline_match:
        deadline = deadline_match.group(1).strip()
    task = OWNER.sub("", text).strip(" .,-—")
    task = DEADLINE.sub("", task).strip(" .,-—")
    return owner, deadline, task or text.strip()


def segment_text(text):
    """Split prose at sentence boundaries, retaining dates such as 20.09.2026."""
    text = re.sub(r"(?<=[.!?;])\s+(?=[A-Za-zА-Яа-яЁё])", "\n", text)
    return [s.strip() for s in text.splitlines() if s.strip()]


def extract_items(lines: list[str]) -> tuple[list[dict], list[str], list[str], list[str]]:
    actions: list[dict] = []
    decisions: list[str] = []
    questions: list[str] = []
    participants: list[str] = []
    seen_actions: set[tuple] = set()

    def add_action(task: str, owner: str = "", deadline: str = "") -> None:
        lead_name = re.match(r"^([A-Za-zА-Яа-яЁё]{2,30})\s*:\s*(.+)$", task)
        if lead_name and lead_name.group(1).lower() not in SKIP_ASSIGNEE_NAMES:
            owner = owner or lead_name.group(1)
            task = lead_name.group(2)
        parsed_owner, parsed_deadline, parsed_task = parse_owner_deadline(task)
        owner = owner or parsed_owner
        deadline = deadline or parsed_deadline
        task = re.sub(r",?\s*owner\s*$", "", parsed_task, flags=re.I).strip(" ,")
        key = (task.casefold(), owner.casefold(), deadline.casefold())
        if task and key not in seen_actions:
            seen_actions.add(key)
            actions.append({"task": task, "owner": owner, "deadline": deadline})

    for line in segment_text("\n".join(lines)):
        stripped = line.strip()
        if not stripped:
            continue

        if not stripped or SKIP_LINE.match(stripped):
            continue

        part_match = PARTICIPANTS.match(stripped)
        if part_match:
            participants.extend(
                p.strip() for p in re.split(r"[,;]", part_match.group(1)) if p.strip()
            )
            continue

        decision_match = DECISION_PREFIX.match(stripped)
        if decision_match:
            decisions.append(decision_match.group(1).strip())
            continue
        prose_decision = re.match(r"^(?:решили|договорились|согласовали|приняли решение|утвердили|постановили|зафиксировали|we agreed|we decided|agreed to)\s+(.+)$", stripped, re.I)
        if prose_decision:
            decisions.append(prose_decision.group(1).strip())
            continue

        question_match = QUESTION_PREFIX.match(stripped)
        if question_match:
            questions.append(question_match.group(1).strip())
            continue

        if stripped.endswith("?") and len(stripped) > 8:
            questions.append(stripped.lstrip("-*• ").strip())
            continue

        for pattern in (ACTION_PREFIX, CHECKBOX):
            match = pattern.match(stripped)
            if match:
                add_action(match.group(1))
                break
        else:
            prose_action = re.match(r"^([А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+)?)\s+((?:" + FUTURE_VERBS + r")\b.+)$", stripped)
            if prose_action:
                add_action(prose_action.group(2), prose_action.group(1))
                continue
            assignee_match = ASSIGNEE_LINE.match(stripped)
            if assignee_match:
                name, rest = assignee_match.group(1).strip(), assignee_match.group(2).strip()
                if PROPOSAL.search(rest) or not TASK_START.search(rest):
                    continue
                if name.lower() not in SKIP_ASSIGNEE_NAMES:
                    owner, deadline, task = parse_owner_deadline(rest)
                    add_action(task, owner or name, deadline)
                    continue

    return actions, decisions, questions, participants


def build_markdown(
    src_name: str,
    actions: list[dict],
    decisions: list[str],
    questions: list[str],
    participants: list[str],
) -> str:
    lines = [
        "# Протокол встречи — структурированный разбор",
        "",
        f"- Источник: `{src_name}`",
        f"- Action items: **{len(actions)}**",
        f"- Решения: **{len(decisions)}**",
        f"- Открытые вопросы: **{len(questions)}**",
        "",
        "## Решения",
        "",
    ]
    if decisions:
        for item in decisions:
            lines.append(f"- {item}")
    else:
        lines.append("- Явные решения не найдены (эвристика).")

    lines += ["", "## Action items", "", "| # | Задача | Ответственный | Срок |", "| --- | --- | --- | --- |"]
    if actions:
        for index, row in enumerate(actions, 1):
            lines.append(
                f"| {index} | {row['task']} | {row['owner'] or '—'} | {row['deadline'] or '—'} |"
            )
    else:
        lines.append("| — | Задачи не найдены | — | — |")

    lines += ["", "## Открытые вопросы", ""]
    if questions:
        for item in questions:
            lines.append(f"- {item}")
    else:
        lines.append("- Открытых вопросов не найдено.")

    if participants:
        lines += ["", "## Участники", ""]
        for person in participants:
            lines.append(f"- {person}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Разбор протокола встречи (.txt).")
    parser.add_argument("input", help="Заметки или транскрипт встречи (.txt)")
    parser.add_argument("--out", default="meeting_minutes.md", help="Markdown-протокол")
    parser.add_argument("--out-csv", default="action_items.csv", help="CSV action items")
    add_manifest_args(parser)
    args = parser.parse_args()

    src = Path(args.input)
    text = src.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    actions, decisions, questions, participants = extract_items(lines)
    report = build_markdown(src.name, actions, decisions, questions, participants)

    out_path = Path(args.out)
    out_path.write_text(report, encoding="utf-8")

    csv_path = Path(args.out_csv)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["task", "owner", "deadline"])
        writer.writeheader()
        writer.writerows(actions)

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_path)
    write_manifest(
        manifest_path,
        skill="meeting-minutes",
        status="ok",
        inputs=[artifact(src, "text", "data")],
        outputs=[
            artifact(out_path, "markdown", "report"),
            artifact(csv_path, "csv", "data"),
        ],
        metrics={
            "actions": len(actions),
            "decisions": len(decisions),
            "questions": len(questions),
            "participants": len(participants),
        },
        suggested_next=["pii-redactor", "report-builder"],
    )
    print(f"Протокол: {out_path}")
    print(f"Action items CSV: {csv_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
