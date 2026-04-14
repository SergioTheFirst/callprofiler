@echo off
REM save-session.bat — Сохранение завершённой сессии
REM
REM Процесс (как в AGENTS.md 3.3):
REM 1. Проверить статус измнений
REM 2. Запустить тесты
REM 3. Проверить CHANGELOG.md и CONTINUITY.md обновлены
REM 4. Сделать commit
REM 5. Push

echo.
echo ============================================
echo  CallProfiler — сохранение сессии
echo ============================================
echo.

REM [1] Показать статус
echo [1/5] Статус изменений:
git status --short
echo.

REM [2] Запустить тесты (если есть)
echo [2/5] Запуск тестов...
if exist "tests\" (
    python -m pytest tests/ -q
    if %ERRORLEVEL% neq 0 (
        echo.
        echo ❌ ТЕСТЫ НЕ ПРОШЛИ! Сессия NOT сохранена.
        echo Исправьте ошибки и запустите save-session.bat снова.
        pause
        exit /b 1
    )
    echo ✓ Тесты passed
) else (
    echo ⚠ tests/ не найден — пропуск
)
echo.

REM [3] Проверить что CHANGELOG и CONTINUITY обновлены
echo [3/5] Проверка обновления журналов...
git diff --name-only | findstr "CHANGELOG.md CONTINUITY.md" > nul
if %ERRORLEVEL% equ 0 (
    echo ✓ CHANGELOG.md и/или CONTINUITY.md изменены
) else (
    echo ⚠ WARNING: CHANGELOG.md и CONTINUITY.md НЕ изменены
    echo Убедитесь, что обновили журналы!
    pause
)
echo.

REM [4] Stage и commit
echo [4/5] Подготовка к commit...
git add -A
echo.

REM Показать что будет committed
echo Файлы для commit:
git diff --cached --name-only
echo.

echo Внесите сообщение для commit (или нажмите Ctrl+C для отмены):
set /p COMMIT_MSG=">> "

if "%COMMIT_MSG%"=="" (
    echo Отмена commit.
    git reset
    pause
    exit /b 1
)

git commit -m "%COMMIT_MSG%"
echo.

REM [5] Push
echo [5/5] Push в origin...
git push -u origin HEAD
echo.

echo ============================================
echo ✓ Сессия СОХРАНЕНА И ЗАПУШЕНА!
echo ============================================
echo.
pause
