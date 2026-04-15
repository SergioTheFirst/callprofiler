---
description: Безопасное сохранение сессии — tests → journal → commit → push
---

Выполни сохранение сессии СТРОГО по порядку:

1. **Tests** — запусти `pytest tests/ -q` (только summary). Если FAILED — СТОП, покажи ошибку, не коммить.

2. **Journal check** — убедись что в последней сессии обновлены:
   - CONTINUITY.md (секция "Текущее состояние" свежая)
   - CHANGELOG.md (секция [Unreleased] содержит изменения)
   Если нет — обнови их ПЕРЕД коммитом.

3. **Git status** — `git status --short` (только краткий вид). Покажи пользователю что будет закоммичено.

4. **Commit** — создай коммит с понятным message в формате:
   ```
   <action>: <short description>

   <bullets с деталями>

   Tests: 90 passed
   ```

5. **Push** — `git push -u origin main`. Если push fails — retry с exponential backoff (2s, 4s, 8s, 16s).

6. **Report** — в конце: "[commit_hash] pushed. Memory updated."

Не проси подтверждения на каждом шаге — выполняй последовательно.
Если тесты упали — ОСТАНОВИСЬ и покажи пользователю ошибку.
