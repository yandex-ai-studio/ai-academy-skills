# Примеры — report-builder

## Пример 1 — интерактивный режим

Пользователь загружает `step1.manifest.json` и просит обработать данные.
Агент запускает скрипт в shell и показывает результат `executive_report.md`.

```bash
python3 scripts/build_report.py --manifests step1.manifest.json step2.manifest.json --out executive_report.md
```

## Пример 2 — пайплайн-режим

Входной артефакт из `inputs` передаётся следующему скиллу через `manifest.json`.
Скилл пишет `manifest.json` с `outputs` и `suggested_next` для `report-builder`.

## Вариант схемы и warning

**Запрос:** JSON {"name":"Загрузка","state":"warning","kpis":[{"name":"rows","value":7}],"artifacts":["loaded.csv"]}.

**Ожидаемое поведение:** Показать rows=7, артефакт loaded.csv и warning; не объявлять этот шаг ошибкой.
