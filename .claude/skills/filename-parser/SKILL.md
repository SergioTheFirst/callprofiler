---
name: filename-parser
description: Парсинг имён аудиофайлов Android-диктофонов и определителей звонков в CallMetadata. Применять при изменении filename_parser.py, добавлении новых форматов, отладке "UNKNOWN" телефонов или нормализации номеров в E.164.
---

# Skill: filename-parser

## Назначение

CallProfiler получает аудиофайлы от разных Android-приложений записи
звонков. Каждое приложение именует файлы по-своему. Этот skill описывает
**5 поддерживаемых форматов**, правила нормализации телефонов и точки
расширения, когда появляется 6-й формат.

Связанный код:
- `src/callprofiler/ingest/filename_parser.py` — реализация
- `tests/test_filename_parser.py` — 40 тестов (8 normalize_phone + 32 parse_filename)
- `src/callprofiler/models.py` — `CallMetadata` dataclass

## Когда применять

- Добавление/изменение форматов имён файлов.
- Отладка случаев, когда `parse_filename()` возвращает `phone=None` или
  `direction='UNKNOWN'` для файла, который должен был распарситься.
- Изменение правил `normalize_phone()` (новая страна, новый сервисный код).
- Написание тестов для парсера.

## Поддерживаемые форматы

| № | Пример                                                    | Поля                        |
|---|-----------------------------------------------------------|-----------------------------|
| 1 | `007496451-07-97(0074964510797)_20240925154220`           | phone, datetime             |
| 2 | `8(495)197-87-11(84951978711)_20240502164535`             | phone, datetime             |
| 3 | `8496451-07-97(84964510797)_20240502170140`               | phone, datetime             |
| 4 | `Иванов(0079161234567)_20260328143022`                    | name, phone, datetime       |
|   | `Вызов@Ира(007925291-85-95)_20170828123145`               | name (без префикса), phone  |
|   | `name(900)_20231009112764`                                | name, сервисный короткий    |
| 5 | `Варлакаув Хрюн 2009_09_03 21_05_57`                      | name, datetime (без phone)  |

`direction` всегда `UNKNOWN` — текущие форматы не содержат `IN`/`OUT`.
При необходимости — добавлять через отдельный формат.

## Правила `normalize_phone()`

Вход → Выход:
- `007XXXXXXXXX` (11+ цифр) → `+7XXXXXXXXX` (международный 00 = +)
- `8` + ровно 11 цифр → `+7XXXXXXXXX` (русский 8)
- `00YYY...` (не 007) → `+YYY...` (другие международные)
- 3–4 цифры (`900`, `112`, `0511`) → как есть (сервисные)
- `79XXXXXXXXX` (12 цифр) → `+79XXXXXXXXX`
- всё остальное → `None`

Убираются скобки, дефисы, пробелы перед проверкой.

## Алгоритм расширения (как добавить 6-й формат)

1. **Собрать примеры.** Минимум 5 реальных имён файлов нового формата.
   Положить в `tests/fixtures/` если уместно.
2. **Написать тесты первыми** в `tests/test_filename_parser.py`:
   - happy path (3–5 кейсов)
   - edge case (пустое имя, сломанная дата, короткий номер)
   - проверка изоляции: новый формат не должен ломать старые.
3. **Добавить regex `_FMT6_RE`** с `re.VERBOSE` и комментарием.
4. **Написать `_parse_fmt6(stem) -> CallMetadata | None`.** Сигнатура
   строго как у других `_parse_fmtN`.
5. **Зарегистрировать в `parse_filename()`** — ВАЖНО: учесть порядок,
   формат 4 (`.+?(...)`) «жадный» и может съесть кейсы форматов 1–3.
   Добавляй новые форматы **перед** формат 4 или **после** формата 5
   в зависимости от специфичности regex.
6. **Прогнать все тесты:** `pytest tests/test_filename_parser.py -v`.
7. **Обновить docstring модуля** и таблицу в этом SKILL.md.
8. **Обновить CHANGELOG.md + CONTINUITY.md** (см. skill `journal-keeper`).

## Анти-паттерны

- **Изменение порядка форматов** без прогонки всех 40 тестов. Порядок
  важен из-за «жадных» regex в формате 4.
- **Парсинг телефонов в обход `normalize_phone()`.** Вся логика E.164 —
  в одном месте. Новая страна → новое правило в `normalize_phone()`,
  не в `_parse_fmtN()`.
- **`raise` при неизвестном формате.** `parse_filename()` никогда не
  бросает исключения — возвращает `CallMetadata(phone=None, direction='UNKNOWN')`.
  Валидация происходит выше в `Ingester`.
- **Хардкод `call_datetime=None`.** Если формат содержит дату — пытайся
  распарсить через `datetime.strptime()` с отдельным `try/except ValueError`.
- **Сохранение имени владельца (Сергей, Медведев) в `contact_name`.**
  Фильтрация владельца — забота `name_extractor.py`, не парсера.
- **Забывать про Windows-пути.** `parse_filename()` работает с полным
  путём тоже — тесты `test_parse_filename_from_windows_path` это проверяют.

## Ссылки на код

- Реализация: `src/callprofiler/ingest/filename_parser.py:271` (публичный `parse_filename`)
- Нормализация: `src/callprofiler/ingest/filename_parser.py:38` (`normalize_phone`)
- Regex форматов: `src/callprofiler/ingest/filename_parser.py:92-139`
- Dataclass: `src/callprofiler/models.py` (`CallMetadata`)
- Тесты: `tests/test_filename_parser.py`
- Использование в pipeline: `src/callprofiler/ingest/ingester.py:98` (`parse_filename(fpath.name)`)

## Пример использования

```python
from callprofiler.ingest.filename_parser import parse_filename, normalize_phone

meta = parse_filename("Иванов(+79161234567)_20260328143022.m4a")
# CallMetadata(phone='+79161234567', call_datetime=datetime(2026,3,28,14,30,22),
#              direction='UNKNOWN', contact_name='Иванов', raw_filename='Иванов(+79161234567)_20260328143022')

normalize_phone("8(916) 123-45-67")  # → '+79161234567'
normalize_phone("900")                # → '900' (короткий сервисный)
normalize_phone("gibberish")          # → None
```
