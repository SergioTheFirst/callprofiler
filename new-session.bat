@echo off
REM new-session.bat — Инициализация новой рабочей сессии
REM
REM Что делает:
REM 1. Проверяет статус git
REM 2. Выводит последнее состояние (CONTINUITY.md + CHANGELOG.md)
REM 3. Показывает следующий шаг
REM 4. Готовит к работе (ls files, pytest status)

echo.
echo ============================================
echo  CallProfiler — новая рабочая сессия
echo ============================================
echo.

REM Проверить git статус
echo [1/4] Проверка git статуса...
git status
echo.

REM Показать текущее состояние
echo [2/4] CONTINUITY.md (последнее состояние):
echo ────────────────────────────────────────
for /f "tokens=*" %%A in ('findstr /N "^" CONTINUITY.md ^| findstr /B "9:" ^| findstr /v "^9:$"') do (
    setlocal enabledelayedexpansion
    set line=%%A
    echo !line:~2!
)
echo.

REM Показать последние изменения в CHANGELOG
echo [3/4] CHANGELOG.md (последние 10 строк):
echo ────────────────────────────────────────
powershell -Command "Get-Content CHANGELOG.md -Tail 10"
echo.

REM Показать текущую ветку
echo [4/4] Текущая ветка:
git branch --show-current
echo.

REM Готовность к работе
echo ============================================
echo Статус: ГОТОВ К РАБОТЕ
echo.
echo Используйте после работы:
echo   save-session.bat   — сохранить изменения
echo   emergency-save.bat — срочное сохранение
echo ============================================
echo.
