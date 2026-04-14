@echo off
cd C:\pro\callprofiler-obsidian
git pull origin main
for /f "tokens=1-3 delims=." %%%%a in ('powershell -command "Get-Date -Format dd.MM.yyyy"') do set D=%%%%c-%%%%b-%%%%a
set FILE=C:\pro\callprofiler-obsidian\sessions\%%D%%.md
if not exist "%%FILE%%" (
  echo # Session %%D%% > "%%FILE%%"
  echo. >> "%%FILE%%"
  echo ## Цель >> "%%FILE%%"
  echo. >> "%%FILE%%"
  echo ## Сделано >> "%%FILE%%"
  echo. >> "%%FILE%%"
  echo ## Проблемы >> "%%FILE%%"
  echo. >> "%%FILE%%"
  echo ## Следующий шаг >> "%%FILE%%"
  echo [Создан: %%FILE%%]
)
cd C:\pro\callprofiler
git pull origin main
echo.
echo === CONTINUITY.md последние 30 строк ===
powershell -command "Get-Content CONTINUITY.md ^| Select-Object -Last 30"
pause
