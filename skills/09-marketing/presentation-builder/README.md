# Презентации PowerPoint

Создаёт редактируемый PPTX по брифу, тексту или данным. 14 макетов, три светлые темы (`paper`, `sage`, `stone`), собственные цвета и шрифты, изображения из файлов или по прямой ссылке.

- [Инструкция навыка](SKILL.md)
- [Формат спецификации](references/spec.md)
- [Примеры запросов](examples.md)
- [Готовый архив для AI Studio](../../../for_agents/presentation-builder.zip)

## Локальный пример

Из папки навыка:

```sh
python3 scripts/doctor.py
python3 scripts/builder.py assets/example.json --output-dir /tmp/presentation-example
python3 scripts/validate_deck.py /tmp/presentation-example/support-pilot.pptx --strict
```

Зависимости: `python-pptx` и `Pillow` из `requirements.txt`. Для необязательного рендера превью нужны LibreOffice и Poppler.

## Проверка

10 локальных тестов охватывают все макеты и темы, сохранность чисел, редактируемость диаграмм, переполнение текста и обработку изображений. Проверки запускаются из корня репозитория:

```sh
python3 -m unittest discover -s tests -p 'test_presentation*.py' -v
```

Три запуска через Skills API и Responses API на DeepSeek V4 Flash завершились успешно (`temperature: 1`, `reasoning.effort: medium`). Созданные PPTX скачаны из контейнеров и просмотрены после локального рендера. В тестовых контейнерах средства рендера отсутствовали.

## Сборка архива

Из корня репозитория:

```sh
python3 tools/build_zip.py presentation-builder
```

Состав задаётся в `bundle.json`: `SKILL.md` находится в корне ZIP, рядом с `scripts`, `assets`, `references` и `requirements.txt`. Сохранённый в `for_agents` архив содержит проверенные в AI Studio файлы.
