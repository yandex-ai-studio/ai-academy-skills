# Примеры — fin-model-builder

## Пример 1 — интерактивный режим

Пользователь загружает `sample_categorized.csv` и просит обработать данные.
Агент запускает скрипт в shell и показывает результат `pl_pivot.csv`.

```bash
python3 scripts/build_fin_model.py sample_categorized.csv --out-csv pl_pivot.csv --report pl_report.md
```

## Пример 2 — пайплайн-режим

Входной артефакт из `inputs` передаётся следующему скиллу через `manifest.json`.
Скилл пишет `manifest.json` с `outputs` и `suggested_next` для `report-builder`.

## Изменённая схема выгрузки

**Запрос:** XLSX с колонками «Дата платежа», «Итого», «Статья».

**Ожидаемое поведение:** Подготовить columns.json с соответствием date/amount/category, посчитать месяцы и проверить сумму. Это денежная сводка по платежам, не полноценная финмодель.
