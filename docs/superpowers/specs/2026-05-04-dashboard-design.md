# CallProfiler Real-Time Dashboard Design

**Date:** 2026-05-04  
**Author:** Claude (Kiro)  
**Status:** Approved

---

## Executive Summary

A web-based real-time monitoring dashboard for CallProfiler pipeline. Displays live events (new audio → transcription → analysis → results) with historical browsing and detailed entity psychology profiles. Read-only observation panel with zero impact on existing pipeline code.

**Key Requirements:**
- Live event stream (SSE, 2-3 sec latency)
- Historical data browser with filters
- Full psychology profiles for entities (temperament, Big Five, motivation, biography portraits)
- High-tech premium dark theme
- Public dashboard (no authentication)
- 100% local, no cloud dependencies

---

## Architecture

### Technology Stack

**Backend:**
- FastAPI (async web framework)
- SQLite (read-only access to callprofiler.db)
- Jinja2 (HTML templates)
- Python 3.10+

**Frontend:**
- Vanilla JavaScript (no React/Vue)
- Tailwind CSS (utility-first styling)
- EventSource API (SSE client)

**Deployment:**
- Single process on port 8765
- CLI command: `python -m callprofiler dashboard --user serhio`

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Live Feed   │  │   History    │  │   Entity     │      │
│  │  Component   │  │   Browser    │  │   Profile    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         │ SSE              │ REST API         │ REST API     │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼──────────────┐
│         ▼                  ▼                  ▼              │
│  ┌────────────────────────────────────────────────────┐     │
│  │           FastAPI Application                      │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────┐ │     │
│  │  │ /events/     │  │ /api/        │  │ /api/   │ │     │
│  │  │  stream      │  │  history     │  │  entity │ │     │
│  │  └──────┬───────┘  └──────┬───────┘  └────┬────┘ │     │
│  └─────────┼──────────────────┼───────────────┼──────┘     │
│            │                  │               │            │
│  ┌─────────▼──────────────────▼───────────────▼──────┐     │
│  │         EventPoller (background task)             │     │
│  │  - Проверяет MAX(updated_at) каждые 2 сек        │     │
│  │  - Читает новые записи из DB                     │     │
│  │  - Отправляет через SSE queue                    │     │
│  └───────────────────────┬───────────────────────────┘     │
│                          │                                 │
│  ┌───────────────────────▼───────────────────────────┐     │
│  │      SQLite Database (read-only)                  │     │
│  │  calls, transcripts, analyses, events,            │     │
│  │  entities, entity_metrics, bio_portraits          │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│              Dashboard Process (port 8765)                  │
└─────────────────────────────────────────────────────────────┘
```

### Module Structure

```
src/callprofiler/dashboard/
├── __init__.py
├── server.py              # FastAPI app + EventPoller
├── models.py              # Pydantic models для API
├── db_reader.py           # Read-only SQLite queries
├── config.py              # Configuration constants
├── templates/
│   └── index.html         # Single-page app
└── static/
    ├── style.css          # Tailwind + custom theme
    └── app.js             # Frontend logic
```

---

## Data Flow

### 1. Live Events Flow (SSE)

```
[Enricher процесс]
    ↓ INSERT INTO calls/transcripts/analyses/events
[SQLite DB]
    ↓ updated_at изменяется
[EventPoller] (каждые 2 сек)
    ↓ SELECT * WHERE updated_at > last_check
[SSE Queue]
    ↓ event: new_event\ndata: {...}\n\n
[Browser EventSource]
    ↓ onmessage handler
[LiveFeed Component]
    ↓ prepend новое событие
[DOM Update]
```

**Event Types:**

```json
{
  "type": "call_created",
  "timestamp": "2026-05-04T08:15:23",
  "data": {
    "call_id": 1234,
    "contact": "Василий",
    "direction": "incoming",
    "status": "pending"
  }
}

{
  "type": "transcription_complete",
  "timestamp": "2026-05-04T08:17:45",
  "data": {
    "call_id": 1234,
    "duration_sec": 142,
    "speaker_segments": 23
  }
}

{
  "type": "analysis_complete",
  "timestamp": "2026-05-04T08:18:12",
  "data": {
    "call_id": 1234,
    "risk_score": 45,
    "call_type": "business",
    "priority": 70,
    "summary": "Обсуждение поставщиков..."
  }
}

{
  "type": "entity_updated",
  "timestamp": "2026-05-04T08:18:15",
  "data": {
    "entity_id": 42,
    "canonical_name": "Василий",
    "bs_index": 23.5,
    "avg_risk": 38.2
  }
}
```

### 2. History Query Flow

```
[User] клик на "История" + фильтры
    ↓ GET /api/history?date=2026-05&type=analysis&contact=Василий
[FastAPI endpoint]
    ↓ db_reader.get_history(filters)
[SQLite Query]
    ↓ JOIN calls + analyses + contacts
[JSON Response]
    ↓ [{call_id, date, contact, type, status, summary}, ...]
[HistoryBrowser Component]
    ↓ render таблица
[DOM Update]
```

### 3. Entity Profile Flow

```
[User] клик на имя персонажа в событии
    ↓ GET /api/entity/42
[FastAPI endpoint]
    ↓ db_reader.get_entity_profile(entity_id)
[SQLite Queries] (параллельно):
    ├─ SELECT * FROM entities WHERE id=42
    ├─ SELECT * FROM entity_metrics WHERE entity_id=42
    ├─ SELECT * FROM bio_portraits WHERE entity_id=42
    └─ Вычисление psychology profile (temperament, Big Five, motivation)
[JSON Response]
    ↓ {canonical_name, entity_type, metrics, temperament, big_five, motivation, portrait}
[EntityProfile Modal]
    ↓ render профиль
[DOM Update]
```

### 4. EventPoller Logic

```python
async def event_poller():
    last_check = {}  # {table: max_updated_at}
    
    while True:
        await asyncio.sleep(2)
        
        # Проверяем каждую таблицу
        for table in ['calls', 'transcripts', 'analyses', 'events']:
            current_max = db.execute(
                f"SELECT MAX(updated_at) FROM {table} WHERE user_id=?"
            ).fetchone()[0]
            
            if current_max > last_check.get(table, ''):
                # Читаем новые записи
                new_rows = db.execute(
                    f"SELECT * FROM {table} WHERE updated_at > ? AND user_id=?",
                    (last_check[table], user_id)
                ).fetchall()
                
                # Конвертируем в события
                for row in new_rows:
                    event = convert_to_event(table, row)
                    await sse_queue.put(event)
                
                last_check[table] = current_max
```

---

## API Endpoints

### GET /

**Description:** Serve main HTML page  
**Response:** HTML (Jinja2 template)

### GET /events/stream

**Description:** SSE stream for live events  
**Response:** `text/event-stream`  
**Format:**
```
event: new_event
data: {"type": "call_created", "timestamp": "...", "data": {...}}

event: new_event
data: {"type": "analysis_complete", "timestamp": "...", "data": {...}}
```

**Keepalive:** Empty comment every 30 seconds to prevent timeout

### GET /api/history

**Description:** Query historical events with filters  
**Query Parameters:**
- `date_from` (optional): ISO date (YYYY-MM-DD)
- `date_to` (optional): ISO date
- `type` (optional): call|transcription|analysis|entity
- `contact` (optional): contact name filter
- `limit` (optional): max results (default 50)
- `offset` (optional): pagination offset

**Response:**
```json
{
  "total": 1234,
  "results": [
    {
      "timestamp": "2026-05-04T08:18:12",
      "type": "analysis",
      "call_id": 1234,
      "contact": "Василий",
      "status": "complete",
      "summary": "Обсуждение поставщиков...",
      "risk_score": 45,
      "priority": 70
    }
  ]
}
```

### GET /api/entity/{entity_id}

**Description:** Get full psychology profile for entity  
**Path Parameters:**
- `entity_id`: integer

**Response:**
```json
{
  "entity_id": 42,
  "canonical_name": "Василий",
  "entity_type": "PERSON",
  "aliases": ["Вася", "Василий Петрович"],
  "metrics": {
    "bs_index": 23.5,
    "avg_risk": 38.2,
    "trust_score": 0.76,
    "volatility": 0.32,
    "conflict_count": 2,
    "open_promises": 1,
    "total_calls": 47
  },
  "temperament": {
    "type": "choleric",
    "energy": "high",
    "reactivity": "high",
    "calls_per_week": 3.2
  },
  "big_five": {
    "openness": 0.8,
    "conscientiousness": 0.6,
    "extraversion": 0.8,
    "agreeableness": 0.4,
    "neuroticism": 0.5
  },
  "motivation": {
    "primary": "achievement",
    "drivers": [
      {"driver": "achievement", "score": 0.8},
      {"driver": "power", "score": 0.6}
    ]
  },
  "portrait": {
    "prose": "Василий (холерический темперамент, высокая энергия)...",
    "traits": ["деловой", "прямолинейный", "требовательный"],
    "relationship": "коллега по проекту, инициатор"
  }
}
```

### GET /api/stats

**Description:** Quick stats for dashboard header  
**Response:**
```json
{
  "calls_today": 12,
  "processing": 2,
  "high_risk_today": 1,
  "active_entities": 47
}
```

---

## UI/UX Design

### Color Scheme (Dark Theme)

```css
:root {
  --bg-primary: #0a0e1a;      /* Тёмно-синий фон */
  --bg-secondary: #151b2e;    /* Карточки */
  --bg-tertiary: #1e2740;     /* Hover states */
  
  --text-primary: #e4e8f0;    /* Основной текст */
  --text-secondary: #8b95ab;  /* Вторичный текст */
  --text-muted: #5a6478;      /* Timestamps */
  
  --accent-blue: #3b82f6;     /* Ссылки, кнопки */
  --accent-green: #10b981;    /* Success */
  --accent-yellow: #f59e0b;   /* Warning */
  --accent-red: #ef4444;      /* Error, high risk */
  
  --border: #2d3748;          /* Разделители */
  --shadow: rgba(0, 0, 0, 0.5);
}
```

### Typography

```css
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--bg-primary);
}

h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
h2 { font-size: 18px; font-weight: 600; }
h3 { font-size: 16px; font-weight: 600; }

.mono { font-family: 'JetBrains Mono', 'Fira Code', monospace; }
```

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  CallProfiler Dashboard          [●] Connected   [⚙] Settings│
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────┐  ┌───────────────────────────┐ │
│  │   Live Feed             │  │   Quick Stats             │ │
│  │  ┌──────────────────┐   │  │  📞 Calls today: 12       │ │
│  │  │ 08:18:12         │   │  │  ⚡ Processing: 2         │ │
│  │  │ Analysis complete│   │  │  ⚠️  High risk: 1         │ │
│  │  │ Василий          │   │  │  👥 Active entities: 47   │ │
│  │  │ Risk: 45 🟡      │   │  └───────────────────────────┘ │
│  │  └──────────────────┘   │                                │
│  │  ┌──────────────────┐   │  ┌───────────────────────────┐ │
│  │  │ 08:17:45         │   │  │   Filters                 │ │
│  │  │ Transcription OK │   │  │  Date: [2026-05-04    ▼] │ │
│  │  │ 142 sec, 23 seg  │   │  │  Type: [All           ▼] │ │
│  │  └──────────────────┘   │  │  Contact: [All        ▼] │ │
│  │  ...                    │  │  [Apply Filters]          │ │
│  └─────────────────────────┘  └───────────────────────────┘ │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │   History                                    [Export CSV] ││
│  │  ┌────────┬──────────┬─────────┬────────┬──────────────┐││
│  │  │ Time   │ Contact  │ Type    │ Status │ Summary      │││
│  │  ├────────┼──────────┼─────────┼────────┼──────────────┤││
│  │  │ 08:18  │ Василий  │ Analysis│ ✓      │ Обсуждение...│││
│  │  │ 08:15  │ Василий  │ Call    │ ✓      │ Incoming 142s│││
│  │  │ 07:42  │ Катя     │ Analysis│ ✓      │ Проект X...  │││
│  │  └────────┴──────────┴─────────┴────────┴──────────────┘││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Entity Profile Modal

```
┌─────────────────────────────────────────────────────────────┐
│  Василий                                              [✕]    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Type: PERSON  │  Mentions: 47  │  Last contact: 2 hours ago│
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Behavioral Metrics                                      ││
│  │  BS-index: 23.5 🟢  │  Avg Risk: 38.2 🟡                ││
│  │  Trust score: 0.76  │  Volatility: 0.32                 ││
│  │  Conflicts: 2       │  Open promises: 1                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Psychology Profile                                      ││
│  │                                                         ││
│  │  Temperament: Choleric                                  ││
│  │    Energy: High  │  Reactivity: High  │  Calls/week: 3  ││
│  │                                                         ││
│  │  Big Five (OCEAN):                                      ││
│  │    Openness:          ████████░░ 0.8                    ││
│  │    Conscientiousness: ██████░░░░ 0.6                    ││
│  │    Extraversion:      ████████░░ 0.8                    ││
│  │    Agreeableness:     ████░░░░░░ 0.4                    ││
│  │    Neuroticism:       █████░░░░░ 0.5                    ││
│  │                                                         ││
│  │  Motivation (McClelland):                               ││
│  │    Primary: Achievement                                 ││
│  │    Drivers: Achievement (0.8), Power (0.6)              ││
│  └─────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Biography Portrait                                      ││
│  │                                                         ││
│  │  Traits: деловой, прямолинейный, требовательный,       ││
│  │          холерик, высокая мотивация достижения         ││
│  │                                                         ││
│  │  Relationship: коллега по проекту, инициатор           ││
│  │                                                         ││
│  │  Prose: Василий (холерический темперамент, высокая     ││
│  │  энергия) появился в трёх звонках в марте. Его стиль — ││
│  │  прямые вопросы без обиняков (экстраверсия 0.8,        ││
│  │  открытость 0.7). Доминирующая мотивация — достижение  ││
│  │  результата...                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                               │
│                                    [Close]                    │
└─────────────────────────────────────────────────────────────┘
```

### Animations

```css
/* Плавное появление новых событий */
.event-card {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Пульсация индикатора подключения */
.status-indicator.connected {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* Hover эффекты */
.event-card:hover {
  background: var(--bg-tertiary);
  transform: translateX(4px);
  transition: all 0.2s ease;
}
```

---

## Error Handling

### Backend Errors

**1. Database Connection Failures**
```python
try:
    conn = sqlite3.connect(db_path, check_same_thread=False)
except sqlite3.Error as e:
    logger.error("DB connection failed: %s", e)
    return HTMLResponse("Database unavailable", status_code=503)
```

**2. SSE Connection Drops**
```python
@app.get("/events/stream")
async def event_stream(request: Request):
    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await sse_queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("SSE error: %s", e)
            yield f"event: error\ndata: {str(e)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**3. Query Timeouts**
```python
conn.execute("PRAGMA busy_timeout = 5000")  # 5 sec

try:
    rows = conn.execute(query, params).fetchall()
except sqlite3.OperationalError:
    return {"error": "Query timeout", "partial": True}
```

### Frontend Errors

**1. SSE Reconnection**
```javascript
const eventSource = new EventSource('/events/stream');

eventSource.onerror = (e) => {
  console.error('SSE error:', e);
  statusBar.show('Переподключение...', 'warning');
};

eventSource.onopen = () => {
  statusBar.show('Подключено', 'success');
};
```

**2. API Request Failures**
```javascript
async function fetchHistory(filters) {
  try {
    const response = await fetch('/api/history?' + new URLSearchParams(filters));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error('History fetch failed:', error);
    showNotification('Не удалось загрузить историю', 'error');
    return [];
  }
}
```

**3. Malformed Event Data**
```javascript
eventSource.onmessage = (e) => {
  try {
    const event = JSON.parse(e.data);
    if (!event.type || !event.data) {
      throw new Error('Invalid event structure');
    }
    liveFeed.addEvent(event);
  } catch (error) {
    console.error('Failed to parse event:', error, e.data);
  }
};
```

### Graceful Degradation

**Если SSE не работает:**
- Показать предупреждение "Live updates недоступны"
- Переключиться на polling (fetch /api/recent каждые 5 сек)
- Кнопка "Обновить" для ручного refresh

**Если DB недоступна:**
- Показать статичную страницу с инструкцией
- Не запускать EventPoller
- Retry connection каждые 30 сек

---

## Testing Strategy

### Unit Tests (pytest)

**1. EventPoller Logic**
```python
def test_event_poller_detects_new_calls(tmp_db):
    conn = sqlite3.connect(tmp_db)
    # ... insert test data
    
    poller = EventPoller(tmp_db, user_id='test')
    events = await poller.check_updates()
    
    assert len(events) == 1
    assert events[0]['type'] == 'call_created'
```

**2. DB Reader Queries**
```python
def test_get_history_filters_by_date(tmp_db):
    reader = DBReader(tmp_db)
    results = reader.get_history(
        user_id='test',
        date_from='2026-05-01',
        date_to='2026-05-31'
    )
    assert all(r['date'].startswith('2026-05') for r in results)
```

**3. Entity Profile Assembly**
```python
def test_get_entity_profile_includes_psychology(tmp_db):
    reader = DBReader(tmp_db)
    profile = reader.get_entity_profile(entity_id=42, user_id='test')
    
    assert 'temperament' in profile
    assert 'big_five' in profile
    assert 'motivation' in profile
```

### Integration Tests

**1. SSE Stream**
```python
@pytest.mark.asyncio
async def test_sse_stream_sends_events(test_client):
    async with test_client.stream('GET', '/events/stream') as response:
        insert_test_call()
        
        async for line in response.aiter_lines():
            if line.startswith('data:'):
                event = json.loads(line[5:])
                assert event['type'] == 'call_created'
                break
```

**2. History API**
```python
def test_history_api_returns_filtered_results(test_client):
    response = test_client.get('/api/history?type=analysis&limit=10')
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 10
```

### Manual Testing Checklist

- [ ] Запустить dashboard: `python -m callprofiler dashboard --user serhio`
- [ ] Открыть http://localhost:8765 в браузере
- [ ] Проверить SSE подключение (индикатор "Подключено")
- [ ] Запустить enricher в другом терминале
- [ ] Скопировать аудиофайл в incoming_dir
- [ ] Проверить появление событий в LiveFeed
- [ ] Кликнуть на имя персонажа → проверить модальное окно
- [ ] Открыть "История" → проверить фильтры
- [ ] Закрыть браузер → переоткрыть → проверить автоподключение

---

## Configuration

```python
# src/callprofiler/dashboard/config.py

DASHBOARD_CONFIG = {
    "poll_interval_sec": 2,
    "sse_keepalive_sec": 30,
    "history_page_size": 50,
    "max_live_events": 100,
    "db_timeout_sec": 5,
    "log_level": "INFO",
}
```

---

## Deployment

### CLI Command

```bash
python -m callprofiler dashboard --user serhio --port 8765
```

### Startup Sequence

1. Проверить существование DB (`callprofiler.db`)
2. Проверить наличие user_id в таблице `users`
3. Запустить FastAPI app на указанном порту
4. Запустить EventPoller в фоне
5. Открыть браузер на `http://localhost:8765`
6. Логировать все события в `dashboard.log`

---

## Security Considerations

**Public Dashboard (No Auth):**
- Dashboard is read-only (no write operations)
- Intended for local network only (localhost:8765)
- No sensitive data exposure (no passwords, tokens)
- User data isolation via user_id filter in all queries

**Future Auth (if needed):**
- Add simple password protection via environment variable
- HTTP Basic Auth middleware in FastAPI
- Session cookies for persistent login

---

## Performance Considerations

**Database:**
- Read-only access (no locks)
- Indexed queries (updated_at, user_id)
- Query timeout: 5 seconds
- Connection pooling not needed (single user)

**SSE:**
- Max 100 events in live feed (auto-trim old)
- Keepalive every 30 sec (prevent timeout)
- Automatic reconnection on disconnect

**Frontend:**
- Vanilla JS (no framework overhead)
- Lazy loading for history (pagination)
- Modal lazy-load entity profiles (on-demand)

---

## Future Enhancements

**Phase 1 (Current):**
- Live event stream
- History browser
- Entity profiles

**Phase 2 (Future):**
- Export to CSV/JSON
- Custom filters (save/load)
- Dark/light theme toggle

**Phase 3 (Future):**
- WebSocket upgrade (< 100ms latency)
- Real-time charts (calls per hour, risk distribution)
- Multi-user support with authentication

---

## Success Metrics

1. **Latency:** Events appear in browser within 3 seconds of DB write
2. **Stability:** Dashboard runs 24/7 without crashes
3. **Performance:** History queries < 500ms for 1000 records
4. **Usability:** Entity profile loads < 200ms
5. **Zero Impact:** Enricher performance unchanged (no slowdown)

---

## Constraints

- 100% local (no cloud dependencies)
- Read-only DB access (no schema changes)
- No breaking changes to existing code
- Windows compatible (paths, file handling)
- Single user per dashboard instance
