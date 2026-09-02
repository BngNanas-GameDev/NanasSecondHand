@echo off
REM Impose single file via AI + ImpositionTool
REM Usage: drag PDF onto this .bat, or: impose.bat "C:\path\file.pdf"
title Nanas Impose Single
cd /d "%~dp0"

if "%~1"=="" (
  echo Drag PDF ke file ini atau jalankan: impose.bat "file.pdf"
  echo Contoh: impose.bat "input\contoh.pdf"
  pause
  exit /b
)

set INPUT=%~1
for %%F in ("%INPUT%") do set NAME=%%~nxF
set OUTPUT=impose\%NAME%

echo Input : %INPUT%
echo Output: %OUTPUT%
echo Tool  : C:\ImpositionTool\ImpositionTool.exe
echo.

python -c "import sys; sys.path.insert(0,'scripts'); from imposition_bridge import impose_file; from pathlib import Path; import json, shutil; cfg=json.load(open('config.json')); src=Path(r'%INPUT%'); dst=Path(r'%OUTPUT%'); ok=impose_file(src, dst, cfg); print('SUKSES' if ok else 'GAGAL'); exit(0 if ok else 1)"
if %errorlevel%==0 (
  echo.
  echo [SUKSES] %NAME% -> impose\%NAME%
  REM pindah file input ke folder uda
  if not exist "input\uda" mkdir "input\uda"
  move /Y "%INPUT%" "input\uda\%NAME%" >nul
  echo [PINDAH] %NAME% -> input\uda\%NAME%
  explorer /select,"impose\%NAME%"
) else (
  echo [GAGAL] cek logs\
)
pause
