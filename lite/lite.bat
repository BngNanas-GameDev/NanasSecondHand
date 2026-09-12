@echo off
REM NSH Lite - guru saja, tanpa Q-table
chcp 65001 >nul
title NSH Lite - Guru Imposition
cd /d "%~dp0"
color 0A
echo ============================================================
echo   NSH Lite - Guru Imposition (tanpa Q-table)
echo   Tanpa argumen = watcher  ^|  Dengan argumen = sekali jalan
echo ============================================================
echo.
if "%~1"=="" (
  echo  [Watcher] pantau folder input setiap 2 detik
  echo  [Cooldown] 5 detik anti-spam  ^|  3x gagal -^> .txt ERROR
  echo.
  python lite.py
  echo.
  echo --- watcher berhenti ---
  pause
  exit /b
)
echo  [Sekali jalan] %*
echo.
python lite.py %*
echo.
pause
