@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Lance d'abord lancer.bat une fois pour installer Servo-Skull.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\raccourcis.ps1" -Root "%~dp0."
echo.
echo Raccourcis "Servo-Skull" crees sur le Bureau et dans le menu Demarrer.
echo Pour l'epingler : lance-le, puis clic droit sur son icone dans la barre des taches ^> Epingler.
pause
