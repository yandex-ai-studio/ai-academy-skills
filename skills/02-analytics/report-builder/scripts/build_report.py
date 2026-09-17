#!/usr/bin/env python3
"""report-builder: сводный executive-отчёт из manifest.json нескольких скиллов."""

import argparse
import glob
import json
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, read_manifest, write_manifest  # noqa: E402


def normalize_manifest(raw):
    if not isinstance(raw, dict):
        raise ValueError("Каждый шаг отчёта должен быть JSON-объектом.")
    result = dict(raw)
    result["skill"] = raw.get("skill") or raw.get("name") or raw.get("step") or "Без названия"
    status = str(raw.get("status", raw.get("state", "unknown"))).casefold()
    result["status"] = {"success": "ok", "completed": "ok", "warn": "warning", "failed": "error", "failure": "error"}.get(status, status)
    if result["status"] not in ("ok", "warning", "error"):
        result["status"] = "unknown"
    metrics = raw.get("metrics", raw.get("kpis", {}))
    if isinstance(metrics, list):
        metrics = {str(m.get("name", m.get("metric", n))): m.get("value") if "value" in m else m for n, m in enumerate(metrics) if isinstance(m, dict)}
    result["metrics"] = metrics if isinstance(metrics, dict) else {"исходные метрики": metrics}
    outputs = raw.get("outputs", raw.get("artifacts", [])) or []
    if not isinstance(outputs, list):
        outputs = [outputs]
    result["outputs"] = [{"path": o, "role": "artifact"} if isinstance(o, str) else o for o in outputs if isinstance(o, (str, dict))]
    suggested = raw.get("suggested_next") or []
    result["suggested_next"] = [suggested] if isinstance(suggested, str) else suggested
    return result


def aggregate_status(manifests):
    statuses = {m["status"] for m in manifests}
    return next((s for s in ("error", "warning", "unknown") if s in statuses), "ok")


def load_manifests(paths: list[str]) -> list[dict]:
    result = []
    seen = set()
    for pattern in paths:
        for match in sorted(glob.glob(pattern, recursive=True)):
            if str(Path(match).resolve()) in seen:
                continue
            seen.add(str(Path(match).resolve()))
            if match.endswith(".json"):
                raw = read_manifest(match)
                steps = raw if isinstance(raw, list) else raw.get("steps", [raw]) if isinstance(raw, dict) else [raw]
                result.extend(normalize_manifest(m) for m in steps)
    return result


def build_executive(manifests: list[dict], title: str) -> str:
    manifests = [normalize_manifest(m) for m in manifests]
    lines = [
        f"# {title}",
        "",
        f"Шагов в pipeline: **{len(manifests)}**",
        "",
    ]
    for index, manifest in enumerate(manifests, 1):
        skill = manifest.get("skill", "?")
        status = manifest.get("status", "?")
        lines += [f"## Шаг {index}: {skill}", "", f"- Статус: **{status}**"]
        metrics = manifest.get("metrics") or {}
        if metrics:
            lines.append("- Метрики:")
            for key, value in metrics.items():
                lines.append(f"  - {key}: {value}")
        outputs = manifest.get("outputs") or []
        if outputs:
            lines.append("- Артефакты:")
            for out in outputs:
                lines.append(f"  - `{out.get('path')}` ({out.get('role', out.get('type'))})")
        suggested = manifest.get("suggested_next") or []
        if suggested:
            lines.append(f"- Рекомендуемые следующие скиллы: {', '.join(suggested)}")
        lines.append("")

    lines += ["## Рекомендации", ""]
    counts = {s: sum(m["status"] == s for m in manifests) for s in ("ok", "warning", "error", "unknown")}
    lines.append("- Статусы: " + ", ".join(f"{s}: {n}" for s, n in counts.items()))
    if counts["error"]:
        lines.append("- Ошибки (error): проверьте неуспешные шаги и их сообщения.")
    if counts["warning"]:
        lines.append("- Предупреждения (warning): результат получен с ограничениями; это не означает сбой выполнения.")
    if counts["unknown"]:
        lines.append("- Неизвестные статусы: данных недостаточно для вывода об успехе или ошибке.")
    if counts["ok"] == len(manifests):
        lines.append("- Все шаги завершились успешно.")
    lines.append("- Детальные отчёты — в артефактах каждого шага (Markdown/CSV).")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Сводный отчёт из manifest.json.")
    parser.add_argument("--manifests", nargs="+", help="Пути или glob к manifest.json")
    parser.add_argument("--glob", dest="glob_pattern", help="Glob для manifest, напр. '**/manifest.json'")
    parser.add_argument("--out", default="executive_report.md", help="Куда писать сводный отчёт")
    parser.add_argument("--title", default="Executive Report", help="Заголовок отчёта")
    add_manifest_args(parser)
    args = parser.parse_args()

    patterns = list(args.manifests or [])
    if args.glob_pattern:
        patterns.append(args.glob_pattern)
    if not patterns:
        parser.error("Укажите --manifests или --glob")

    manifests = load_manifests(patterns)
    if not manifests:
        print("Manifest не найдены.")
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_executive(manifests, args.title)
    out_path.write_text(report, encoding="utf-8")

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(out_path)
    write_manifest(
        manifest_path,
        skill="report-builder",
        status=aggregate_status(manifests),
        inputs=[artifact(p, "json", "data") for p in patterns],
        outputs=[artifact(out_path, "markdown", "report")],
        metrics={"steps": len(manifests), "skills": [m.get("skill") for m in manifests]},
        suggested_next=[],
    )

    print(f"Сводный отчёт: {out_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
