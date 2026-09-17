# Примеры: Spreadsheet Review

## Scope model — SaaS-модель фаундера

**Вход:** financial_model.xlsx (3-statement, 5 years).

**Находки (фрагмент):**

| # | Лист | Ячейка | Критичность | Проблема |
| --- | --- | --- | --- | --- |
| 1 | BS | D45 | Критично | Assets ≠ L+E на 1.2M Q3 |
| 2 | IS | B12 | Предупреждение | Hardcoded 1.05 growth в revenue row |

**Итого:** Серьёзные — 1 критично, 2 предупреждения.

---

## Pipeline после unit-economics-deep

**Вход:** `unit_economics_report` flagged NDR/gross retention mismatch → user uploads model.

**Выход:** Аудит подтверждает: revenue build не сходится с ARR bridge tab — Критично на IS!C20 link.

---

## Учебный checklist (demo scope model)

1. Критично — BS не сходится в одном периоде (trace WC sign).
2. Предупреждение — hardcoded growth в revenue build.
3. Инфо — inconsistent input cell coloring.

## Проверка конкретных ячеек

**Запрос:** В XLSX есть =SUM(B2:B4), число 100 в середине ряда формул и =Missing!A1.

**Ожидаемое поведение:** Фактически прочитать файл, указать адреса и основания находок. Число — подозрение на hardcode, не доказанная ошибка. Пустой кэш формулы не считать нулём; старый XLS требует конвертации.
