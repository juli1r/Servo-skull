@echo off
setlocal
cd /d "%~dp0"
echo === Servo-Skull : construction de l'exe ===
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
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :err
pyinstaller --noconfirm --onefile --windowed --name Servo-Skull --paths app ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --add-data "app\recap_template.html;." --add-data "app\assets;assets" --add-data "app\data;data" --icon "app\assets\servo-skull.ico" ^
  app\main.py || goto :err
copy /y dist\Servo-Skull.exe . >nul
echo.
echo OK : Servo-Skull.exe est pret dans ce dossier. Double-clique dessus pour lancer.
pause
exit /b 0
:err
echo.
echo Echec de la construction. Copie le message ci-dessus a Claude.
pause
exit /b 1
