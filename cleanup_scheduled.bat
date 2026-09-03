@echo off
REM The Cleanup Team - scheduled run (12:00 & 16:00)
cd /d "%~dp0"
set PY=C:\Users\ID2\AppData\Local\Programs\Python\Python312\python.exe
echo [%date% %time%] Cleanup start >> cleanup.log
"%PY%" cleanup.py --fix >> cleanup.log 2>&1
echo [%date% %time%] Cleanup done (exit=%errorlevel%) >> cleanup.log
