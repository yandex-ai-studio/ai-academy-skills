# Примеры — pdf-toolkit

## Пример 1 — интерактивный режим

Пользователь загружает `sample.pdf` и просит обработать данные.
Агент запускает скрипт в shell и показывает результат `sample.txt`.

```bash
python3 scripts/pdf_toolkit.py --op extract --input sample.pdf --out sample.txt
```

## Пример 2 — пайплайн-режим

Входной артефакт из `inputs` передаётся следующему скиллу через `manifest.json`.
Скилл пишет `manifest.json` с `outputs` и `suggested_next` для `report-builder`.
