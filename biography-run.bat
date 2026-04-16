@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

:: ================================================================
::  biography-run.bat  —  8-pass biography pipeline (CallProfiler)
::  편집할 설정: ONLY the USER CONFIG block below.
::  Resume-safe: повторный запуск пропускает уже выполненные passes.
:: ================================================================

:: ── USER CONFIG (редактировать здесь) ───────────────────────────
set USER_ID=serhio
set CONFIG=C:\pro\callprofiler\configs\base.yaml
set PYTHONPATH=C:\pro\callprofiler\src
set PYTHON=python

:: llama-server адрес (для preflight TCP-проверки)
set LLM_HOST=127.0.0.1
set LLM_PORT=8080

:: Количество повторных попыток LLM-запроса при сбое
set MAX_RETRIES=5

:: Запустить только часть проходов? (пусто = все 8)
:: Пример: set PASSES=p1,p2,p3
set PASSES=

:: Выходная книга
set OUT_DIR=D:\calls\data\biography
set BOOK_FILE=%OUT_DIR%\book_%USER_ID%.md

:: Лог этого запуска (отдельно от основного pipeline.log)
set LOG_DIR=D:\calls\data\logs
set BIO_LOG=%LOG_DIR%\biography_%USER_ID%.log
:: ── END CONFIG ──────────────────────────────────────────────────

:: UTF-8 для всех Python-процессов: исправляет UnicodeEncodeError на CP1251-консоли
:: и устраняет "эяэяэяэяэяэя" при передаче кириллицы через пайп в PowerShell.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

:: Фиксируем время старта
set T0=%TIME%
set D0=%DATE%

echo.
echo ================================================================
echo   CallProfiler  —  Biography Pipeline
echo   User  : %USER_ID%
echo   Start : %D0% %T0%
echo ================================================================
echo.

:: Создаём директории вывода и логов
if not exist "%OUT_DIR%"  mkdir "%OUT_DIR%"
if not exist "%LOG_DIR%"  mkdir "%LOG_DIR%"

:: Инициализируем лог-файл (чтобы Get-Content -Wait не падал сразу)
echo. >> "%BIO_LOG%"
echo ===== biography-run START %D0% %T0% ===== >> "%BIO_LOG%"

:: ── PREFLIGHT 1: Python ─────────────────────────────────────────
echo [preflight 1/3] Python...
set PYTHONPATH=%PYTHONPATH%
%PYTHON% --version > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   FAIL  Python не найден. Добавь python.exe в PATH.
    goto :ABORT
)
for /f "tokens=*" %%V in ('%PYTHON% --version 2^>^&1') do echo   OK    %%V

:: ── PREFLIGHT 2: llama-server ───────────────────────────────────
echo [preflight 2/3] llama-server %LLM_HOST%:%LLM_PORT%...
powershell -NoProfile -Command ^
    "if (Test-NetConnection -ComputerName %LLM_HOST% -Port %LLM_PORT% -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 } else { exit 1 }" ^
    > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   FAIL  llama-server не отвечает на %LLM_HOST%:%LLM_PORT%
    echo.
    echo   Запусти в отдельном окне:
    echo     llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" ^
    echo       -ngl 99 -c 16384 --host 127.0.0.1 --port 8080
    echo.
    goto :ABORT
)
echo   OK    llama-server отвечает

:: ── PREFLIGHT 3: база данных ────────────────────────────────────
echo [preflight 3/3] База данных...
%PYTHON% -c ^
    "import yaml,sys; d=yaml.safe_load(open(r'%CONFIG%')); print(d.get('data_dir',''))" ^
    > "%TEMP%\cp_dd.tmp" 2> nul
if %ERRORLEVEL% neq 0 (
    echo   FAIL  Не удалось прочитать конфиг: %CONFIG%
    goto :ABORT
)
set /p DATA_DIR= < "%TEMP%\cp_dd.tmp"
del "%TEMP%\cp_dd.tmp" 2> nul

set DB_PATH=%DATA_DIR%\db\callprofiler.db
if not exist "%DB_PATH%" (
    echo   FAIL  База данных не найдена: %DB_PATH%
    echo         Сначала выполни: python -m callprofiler bulk-load ...
    goto :ABORT
)
echo   OK    DB: %DB_PATH%

echo.
echo   Preflight пройден. Открываем окно мониторинга...
echo.

:: Открыть окно мониторинга лога в реальном времени
start "Biography Log  [tail -f]" powershell -NoProfile -NoExit -Command ^
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content -Path '%BIO_LOG%' -Wait -Tail 30 -Encoding UTF8"

timeout /t 1 /nobreak > nul

:: ── STEP 1: biography-run ───────────────────────────────────────
echo ================================================================
echo   STEP 1/3  biography-run  (8 passes, resume-safe)
if not "%PASSES%"=="" echo              passes: %PASSES%
echo   Лог  : %BIO_LOG%
echo   Ctrl+C прерывает текущий pass (следующий запуск продолжит).
echo ================================================================
echo.

:: Собираем аргументы Python
:: ВАЖНО: -v должен идти ДО имени подкоманды (глобальный флаг парсера)
set BIO_ARGS=--config "%CONFIG%" -v biography-run --user %USER_ID% --max-retries %MAX_RETRIES%
if not "%PASSES%"=="" set BIO_ARGS=%BIO_ARGS% --passes %PASSES%

:: Запуск с дублированием stdout+stderr в лог через PowerShell Tee-Object.
:: [Console]::InputEncoding = UTF-8 — читаем пайп от Python как UTF-8.
:: ERRORLEVEL здесь ненадёжен (его захватывает PowerShell), поэтому
:: успех проверяем через biography-status ниже.
%PYTHON% -m callprofiler %BIO_ARGS% 2>&1 | powershell -NoProfile -Command ^
    "[Console]::InputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $input | Tee-Object -FilePath '%BIO_LOG%' -Append"

echo.

:: ── STEP 2: biography-status ────────────────────────────────────
echo ================================================================
echo   STEP 2/3  biography-status  (состояние checkpoint-ов)
echo ================================================================
echo.

%PYTHON% -m callprofiler --config "%CONFIG%" biography-status --user %USER_ID%

echo.

:: ── STEP 3: biography-export ────────────────────────────────────
echo ================================================================
echo   STEP 3/3  biography-export  ^>  %BOOK_FILE%
echo ================================================================
echo.

%PYTHON% -m callprofiler --config "%CONFIG%" biography-export --user %USER_ID% --out "%BOOK_FILE%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo   WARN  Книга ещё не собрана — pass p7_book или p8_editorial
    echo         не завершён. Дождись их окончания и запусти снова.
    goto :DONE
)

:: Размер итогового файла
for %%F in ("%BOOK_FILE%") do set BOOK_BYTES=%%~zF
echo.
echo   OK    Книга: %BOOK_FILE%
echo         Размер: %BOOK_BYTES% байт

:: Примерный подсчёт слов через PowerShell
powershell -NoProfile -Command ^
    "$wc = (Get-Content '%BOOK_FILE%' | Measure-Object -Word).Words; Write-Host ('         Слов  : ' + $wc + ' (~' + [int]($wc/250) + ' стр.)')"

echo.
choice /M "Открыть книгу в Notepad" /C YN /N /T 15 /D N
if %ERRORLEVEL% equ 1 start notepad "%BOOK_FILE%"

:DONE
set T1=%TIME%
echo.
echo ================================================================
echo   Biography Pipeline  —  DONE
echo   Start : %D0% %T0%
echo   End   : %D0% %T1%
echo   Книга : %BOOK_FILE%
echo   Лог   : %BIO_LOG%
echo ================================================================
echo.
echo Нажми любую клавишу для закрытия...
pause > nul
exit /b 0

:ABORT
echo.
echo ================================================================
echo   ABORT  —  preflight не пройден. Устрани ошибки выше.
echo ================================================================
echo.
pause
exit /b 1
