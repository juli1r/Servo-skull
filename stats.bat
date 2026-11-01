@echo off
setlocal
cd /d "%~dp0"
rem Reconstruit les stats a partir de tes parties locales, puis ouvre la page.
if exist .venv\Scripts\python.exe (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% tools\build_stats.py --local parties
if errorlevel 1 pause & exit /b 1
start "" "site\index.html"
