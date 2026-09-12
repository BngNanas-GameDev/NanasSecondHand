@echo off
REM Sync aturan guru NSH -> NSH Lite
cd /d "%~dp0"
copy /Y "llm_zen.py" "..\NSH Lite\llm_zen.py" >nul
copy /Y "bahan_dict.py" "..\NSH Lite\bahan_dict.py" >nul
echo [SYNC] llm_zen.py + bahan_dict.py -^> NSH Lite
pause
