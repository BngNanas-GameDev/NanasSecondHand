@echo off
REM WMA - Watcher Module Auto (jembatan ke Watcher Dashboard)
chcp 65001 >nul
title WMA - Watcher Module Auto
cd /d "%~dp0"
color 0A
echo ============================================================
echo   WMA - Watcher Module Auto
echo   Tanya folder dulu -^> tunggu file -^> operator saat batch siap
echo ============================================================
echo.
if "%~1"=="--check" (
  python wma.py --check %2
  echo.
  pause
  exit /b
)
if "%~1"=="--report" (
  python wma.py --report %2 --machine %3
  echo.
  pause
  exit /b
)
python wma.py
echo.
pause
