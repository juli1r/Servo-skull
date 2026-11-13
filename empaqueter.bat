@echo off
setlocal
cd /d "%~dp0"
echo === Servo-Skull : paquet a partager (dossier + zip) ===
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
for /f %%v in ('python -c "import sys; sys.path.insert(0,'app'); from core import VERSION; print(VERSION)"') do set "VER=%%v"
rem Dossier (onedir) plutot qu'un seul exe : beaucoup moins de faux positifs antivirus et demarrage plus rapide.
pyinstaller --noconfirm --onedir --windowed --name Servo-Skull --paths app ^
  --add-data "app\recap_template.html;." --add-data "app\assets;assets" --add-data "app\data;data" --icon "app\assets\servo-skull.ico" ^
  app\main.py || goto :err
copy /y LISEZMOI.md dist\Servo-Skull\LISEZMOI.md >nul
copy /y README.md dist\Servo-Skull\LISEZ-MOI-D-ABORD.md >nul
if not exist release mkdir release
set "ZIP=release\Servo-Skull-%VER%-windows.zip"
if exist "%ZIP%" del "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Servo-Skull' -DestinationPath '%ZIP%'" || goto :err
echo.
echo OK : %ZIP%
echo A envoyer a tes amis (ou a deposer dans les Releases GitHub ou GitLab).
pause
exit /b 0
:err
echo.
echo Echec de la construction. Copie le message ci-dessus a Claude.
pause
exit /b 1
