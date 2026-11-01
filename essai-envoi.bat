@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Lance d abord lancer.bat une fois.
  pause
  exit /b 1
)
.venv\Scripts\python.exe tools\essai_envoi.py
pause
