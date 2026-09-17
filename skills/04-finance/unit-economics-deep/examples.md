# Примеры: Unit Economics Deep

## Пример 1 — SaaS после fin-model-builder

**Вход:** categorized.csv + ARR by customer CSV (12 months).

**Фрагмент выхода:**

| Метрика | Значение | Бенчмарк |
| --- | --- | --- |
| NDR | 112% | Норма (>110%) |
| Gross retention | 88% | Риск (<90%) |
| LTV:CAC | 3.2x | Норма |

**Red flag:** Expansion +24% маскирует logo churn 12% — запросить logo-level cohort export.

---

## Пример 2 — pipeline автономный

**Вход (`financial_data`):** Markdown table: ARR 42M, growth 35%, gross margin 72%, S&M 28% revenue.

**Выход:** Оценка качества выручки итого 3.5/5; CAC payback ~16 мес [assumption]; рекомендуемые вопросы для investor call.
