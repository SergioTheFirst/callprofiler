# CallProfiler Dashboard v3 — Radical Overhaul Plan

## Goal
Ультрасовременная админка: управление ВСЕМИ параметрами системы через единый веб-интерфейс.

---

## Research Summary

| Источник | Ключевой инсайт | Применение |
|----------|----------------|-----------|
| Grafana | URL-synced filter dropdowns, panel repeat-by-variable, transformations | фильтры по user/date/status в URL |
| Datadog | Adaptive refresh (fast for recent, slow for old), change overlays on graphs | pipeline view с адаптивным refresh |
| Supabase | Table editor + SQL console + log viewer as tabs, perfect local-tool model | 4 основные вкладки |
| Glances | Self-hosted Python + Vue.js, API-first, MCP server for AI | архитектура: FastAPI + vanilla JS |
| Uptime Kuma | WebSocket + single-page, dark-first, reaction emoji on status | real-time через существующий SSE |

**Stack decision**: Оставить FastAPI + Jinja2 + vanilla JS (как сейчас). Добавить ECharts (через CDN, без npm). Никаких сборщиков.

## Design Direction

```
Aesthetic:    "Glass-Industrial Command Center"
Tone:         Premium, data-dense, spatial
Base:         #060B16 (deep navy, не pure black)
Accent:       #00D4C8 (cool teal, not purple)
Warning:      #F59E0B (amber)
Danger:       #EF4444 (red)
Font UI:      Geist (Vercel, через CDN)
Font Data:    JetBrains Mono (таблицы, числа, коды)
```

## Architecture: 5 Tabs

```
┌──────────────────────────────────────────────────────┐
│ CallProfiler  [serhio ▼]  2026-05-22  ● connected   │  header
├────┬─────────────────────────────────────────────────┤
│ 📊 │ Overview    → stat cards + pipeline + charts    │
│ 📋 │ Calls       → таблица с фильтрами + inline edit │
│ 🔍 │ Search      → FTS5 + filter chips + результаты  │
│ 🧠 │ Entities    → граф знаний + профили + портреты  │
│ ⚙️  │ Settings    → параметры pipeline, GPU, users    │
├────┴─────────────────────────────────────────────────┤
│  Cmd+K search  │  API healthy  │  DB: 12.3 MB        │  footer
└──────────────────────────────────────────────────────┘
```

---

## Phase 1: Backend — New API Endpoints

| # | Endpoint | Purpose |
|---|----------|---------|
| 1 | `GET /api/pipeline/status` | Статус всех звонков по стадиям (new→done) |
| 2 | `GET /api/pipeline/queue` | Очередь: pending + error с деталями |
| 3 | `GET /api/calls?status=&user=&days=&limit=&offset=` | Пагинированная история с фильтрами |
| 4 | `GET /api/calls/{id}` | Полные детали звонка (транскрипт + анализ) |
| 5 | `GET /api/calls/{id}/transcript` | Транскрипт с speaker-метками |
| 6 | `GET /api/search?q=&user=&contact=&days=` | FTS5 поиск с фильтрами |
| 7 | `GET /api/entities?type=&min_calls=&bs_min=&bs_max=` | Сущности графа с фильтрами |
| 8 | `GET /api/promises?status=open&user=&contact=` | Обещания с фильтрацией |
| 9 | `GET /api/system/info` | Версия, размер БД, uptime, GPU memory |
| 10 | `POST /api/actions/retry` | Перезапустить failed звонки |
| 11 | `POST /api/actions/reprocess/{call_id}` | Переобработать один звонок |
| 12 | `POST /api/actions/rescan` | Сканировать incoming_dir на новые файлы |

## Phase 2: Frontend — 5 Tabs Implementation

### Tab 1: Overview (Главный)
- **Stat cards** (4 ряд): сегодня звонков, в очереди, ошибок, средний риск
- **Pipeline stepper**: визуальная диаграмма new→normalizing→transcribing→diarizing→analyzing→done с цветовой подсветкой и счётчиками на каждом шаге
- **Realtime feed**: компактный список последних 10 событий (SSE), анимированное появление
- **Chart: звонки за 7 дней**: area chart с градиентной заливкой (ECharts)
- **Chart: распределение по call_type**: donut chart

### Tab 2: Calls (История)
- **Фильтры сверху**: date range, status dropdown, call_type dropdown, contact search
- **Таблица**: call_id, datetime, contact, duration, status, risk_score, call_type, summary (первые 80 символов)
- **Клик по строке → раскрывается панель**: полный транскрипт с ролями [me]/[s2], analysis (priority, risk, promises, flags), audio-плеер
- **Пагинация**: offset + limit, кнопки "Назад/Вперёд"
- **CSV export** кнопка

### Tab 3: Search (Поиск)
- **Поисковая строка** с автокомплитом контактов
- **Filter chips**: user, contact, date range, call_type — кликабельные теги под строкой поиска, синхронизированы с URL
- **Результаты**: FTS5-сниппеты с подсветкой совпадений, группировка по контакту
- **Клик → карточка звонка** (inline в панели справа)

### Tab 4: Entities (Граф знаний)
- **Таблица сущностей**: имя, тип, звонков, BS-index, риск, дата последнего
- **Фильтры**: entity_type dropdown, min_calls slider, BS-index range
- **Клик → профиль**: психология (Big Five OCEAN, темперамент, мотивация), портрет из biography, социальная сеть (связи)
- **Граф связей**: ECharts force-directed graph — визуализация отношений между сущностями

### Tab 5: Settings (Управление)
- **Pipeline parameters**: watch_interval, max_retries, file_settle_sec — inline edit с save
- **Users**: таблица пользователей (user_id, incoming_dir, sync_dir, chat_id) + кнопка add-user
- **GPU**: текущее состояние VRAM, список моделей, кнопка "unload all"
- **Database**: размер БД, количество записей, кнопка "vacuum"
- **Log viewer**: последние 200 строк pipeline.log, автообновление (tail -f через SSE), фильтр по уровню (INFO/WARN/ERROR)
- **Feature flags**: enable_diarization, enable_llm_analysis, enable_graph_update, enable_telegram — toggle переключатели

## Phase 3: Real-time & UX

- **Command palette**: `Cmd+K` → поиск по всем функциям (переход на вкладку, поиск контакта, открытие настроек)
- **Keyboard shortcuts**: `1-5` для вкладок, `/` для поиска, `Esc` закрыть модалку
- **URL state**: все фильтры в query params → shareable links, refresh-safe
- **Adaptive refresh**: Overview обновляется каждые 5s, Calls/Search только по запросу, Settings не обновляется
- **Toast notifications**: успех/ошибка действий (retry, reprocess, rescan)
- **Skeleton loaders**: при первой загрузке каждой вкладки

## Phase 4: Audio & Media

- **HTML5 Audio Player**: встроенный в карточку звонка, с визуализацией waveform (wavesurfer.js)
- **Timeline sync**: при клике на сегмент транскрипта → перемотка аудио к этому моменту
- **Download**: кнопка скачивания нормализованного WAV

## Phase 5: Polish & Performance

- **CSS-only animations**: без JS-анимаций (per baseline-ui)
- **Dark theme optimization**: проверка контрастности (WCAG AA)
- **Mobile responsive**: вкладки → аккордеон на <768px
- **Error boundaries**: graceful degradation — если API недоступен, показать состояние "переподключение..."
- **Lazy loading**: данные подгружаются только для активной вкладки

---

## Done When
- [x] 5 табов с полным функционалом
- [x] Все API endpoints возвращают корректные данные с `user_id` изоляцией
- [x] Pipeline stepper отражает реальное состояние очереди
- [x] Search работает через FTS5 с фильтрами
- [x] Settings позволяет менять параметры без рестарта
- [x] Command palette (Cmd+K) работает
- [x] URL сохраняет состояние фильтров
- [x] 311 тестов по-прежнему зелёные
- [x] Dashboard запускается: `python -m callprofiler dashboard --user ID`

## Конституционные ограничения (CONSTITUTION.md)
- Никаких облачных сервисов
- SQLite только (нет PostgreSQL/Redis)
- user_id изоляция во ВСЕХ запросах
- Read-only DB для dashboard (уже есть)
- Никаких новых зависимостей без замера
- ECharts через CDN (не npm, не pip)
