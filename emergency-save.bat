@echo off
REM emergency-save.bat — Срочное сохранение перед потенциальной потерей контекста
REM
REM Используйте когда:
REM - Быстро заканчивается токен контекста
REM - Планируется перезагрузка машины
REM - Нужно срочно сохраниться но нет времени на полный цикл save-session.bat
REM
REM ВНИМАНИЕ: этот скрипт НЕ проверяет тесты!
REM Полная проверка должна быть в следующей сессии.

echo.
echo ============================================
echo  EMERGENCY SAVE — СРОЧНОЕ СОХРАНЕНИЕ
echo ============================================
echo.

REM Показать что произойдёт
echo Будут сохранены ВСЕ изменения:
git status --short
echo.

echo ВНИМАНИЕ: тесты НЕ проверяются!
echo Проверьте в следующей сессии: pytest tests/
echo.

set /p CONFIRM="Продолжить срочное сохранение? (y/n) >> "
if /i "%CONFIRM%" neq "y" (
    echo Отмена.
    pause
    exit /b 0
)

REM Сразу добавляем всё
git add -A

REM Делаем коммит с timestamp
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set date=%%c-%%a-%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set time=%%a-%%b)

set COMMIT_MSG=EMERGENCY SAVE: %date% %time% (untested - check in next session)

echo.
echo Commit: %COMMIT_MSG%
git commit -m "%COMMIT_MSG%"

REM Push если возможно
echo.
echo Попытка push...
git push -u origin HEAD 2>nul
if %ERRORLEVEL% equ 0 (
    echo ✓ Push успешен
) else (
    echo ⚠ Push не удался (сохранено локально)
    echo   Попробуйте push позже: git push -u origin HEAD
)

echo.
echo ============================================
echo ✓ АВАРИЙНОЕ СОХРАНЕНИЕ ЗАВЕРШЕНО
echo ============================================
echo.
pause
