@echo off
REM Nanas Second Hand - Auto Reload Watcher
REM Auto restart saat kode berubah
title Nanas Second Hand - Auto Reload
cd /d "%~dp0"
echo ========================================
echo  Nanas Second Hand - AI Imposition
echo  Auto Reload: restart saat kode berubah
echo ========================================
echo.
python auto_reload.py
pause
