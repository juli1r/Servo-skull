@echo off
setlocal
cd /d "%~dp0"
echo === Servo-Skull : publication de la page live ===
where firebase >nul 2>nul
if not %errorlevel%==0 (
  echo Firebase CLI introuvable. Installe-la une fois : npm install -g firebase-tools
  echo Puis connecte-toi : firebase login
  pause
  exit /b 1
)
rem site/ est servi tel quel par Firebase Hosting : recap_template.html (source app/) y est copié à
rem chaque publication pour que site/live.js puisse le charger (même rendu que le récap final).
copy /y app\recap_template.html site\recap_template.html >nul || goto :err
firebase deploy --only hosting || goto :err
echo.
echo OK : page live publiée.
pause
exit /b 0
:err
echo.
echo Échec de la publication. Copie le message ci-dessus à Claude.
pause
exit /b 1
