---
name: pdf-toolkit
description: "Офлайн-операции с PDF — extract текста, merge нескольких файлов, split по страницам. Bundled pypdf в assets/vendor, без сети. Вызывай, когда пользователь просит извлечь текст из PDF, объединить или разделить PDF."
metadata:
  source: Academy of Yandex AI Studio
  shelf: Документы и продуктивность
  type: shell
  role: Документ-инженер
  tools: [shell]
  version: "0.2.0"
inputs: [pdf_file]
outputs: [extracted_text]
---

# PDF Toolkit — extract / merge / split PDF

Офлайн-операции с PDF на bundled pypdf (в `assets/vendor/`): извлечение текста,
объединение нескольких PDF и разделение по страницам. Без сети и pip install.

## Когда использовать

- Пользователь просит «извлечь текст из PDF / объединить PDF / разделить PDF по страницам».
- Нужно подготовить `.txt` для `contract-review`, `pii-redactor` или `resume-screener`.
- Работа с PDF в изолированном shell без интернета.

## Что на входе / на выходе

- Вход: один или несколько PDF-файлов (`--input`).
- Выход (зависит от `--op`):
  - `extract` — `.txt` с текстом страниц (разделитель `--- page break ---`);
  - `merge` — один объединённый PDF;
  - `split` — отдельные PDF по страницам в `--out-dir`;
  - `manifest.json` для следующих шагов.

## Как выполнять (инструкция для агента)

1. Убедись, что в окружении есть `assets/vendor/pypdf` (bundled с скиллом).
2. Запусти нужную операцию:
   ```bash
   # Извлечь текст
   python3 scripts/pdf_toolkit.py --op extract --input document.pdf --out document.txt

   # Объединить PDF
   python3 scripts/pdf_toolkit.py --op merge --input part1.pdf part2.pdf --out merged.pdf

   # Разделить по страницам
   python3 scripts/pdf_toolkit.py --op split --input document.pdf --out-dir split_pages
   ```
3. Покажи пользователю пути к выходным файлам.

## Композиция

- **После:** загрузка PDF пользователем.
- **Дальше:** `contract-review` (extract → review), `pii-redactor` (extract → redact), `resume-screener` (extract → screen), `bank-statement-parser` (extract → parse, если выписка в PDF).
- Пишет `manifest.json` с `suggested_next: ["contract-review", "pii-redactor"]`.

## Ограничения окружения

- Python 3.12; pypdf bundled в `assets/vendor/` — сохраняй структуру каталогов при загрузке.
- Extract — plain text, таблицы и сложная вёрстка могут теряться.
- Без сети; pip install не используется.


## Источники данных

Используй переданный текст, загруженные файлы и доступный веб-поиск. Не подразумевай доступ к CRM, почте, 1С или другим корпоративным системам. Если данных нет, обозначь пробел; не подменяй их вымышленными сведениями.
