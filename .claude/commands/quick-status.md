---
description: Быстрый обзор состояния проекта без чтения больших файлов
---

Выведи компактный статус (минимум токенов):

1. `git status --short` — незакоммиченные изменения
2. `git log -5 --oneline` — последние 5 коммитов
3. `git branch --show-current` — текущая ветка
4. `pytest tests/ --collect-only -q 2>&1 | tail -3` — количество тестов
5. grep первой строки секции "Текущее состояние" в CONTINUITY.md

Формат вывода:
```
📍 Branch: <name>
📝 Uncommitted: <N files или "clean">
🔄 Last 5 commits:
   <hash> <message>
   ...
🧪 Tests: <N collected>
📌 State: <first line from CONTINUITY.md>
```

Не читай большие файлы целиком. Это диагностика, а не брифинг.
