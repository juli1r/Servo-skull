@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe goto :run
echo === Premiere installation (une seule fois) ===
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if not %errorlevel%==0 (
  echo Python 3.10 ou plus est requis : https://www.python.org/downloads/
  echo Pendant l'installation, coche "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% -m venv .venv || goto :err
.venv\Scripts\python.exe -m pip install --upgrade pip >nul
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err
:run
start "" .venv\Scripts\pythonw.exe app\main.py
exit /b 0
:err
echo Echec de l'installation. Copie le message ci-dessus a Claude.
pause
exit /b 1
