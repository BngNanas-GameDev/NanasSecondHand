@echo off
REM Impose single file via RL preset + ImpositionTool
REM Usage: drag PDF onto this .bat, or: impose.bat "C:\path\file.pdf"
title Nanas Impose Single
cd /d "%~dp0"

if "%~1"=="" (
  echo Drag PDF ke file ini atau jalankan: impose.bat "file.pdf"
  pause
  exit /b
)

set INPUT=%~1
for %%F in ("%INPUT%") do set NAME=%%~nxF

python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'scripts'); from imposition_bridge import impose_file; import preset_learner_rl as rl; from pathlib import Path; import json; cfg=json.load(open('config.json')); src=Path(r'%INPUT%'); outdir=Path(cfg.get('output_folder','impose')); outdir.mkdir(parents=True, exist_ok=True); dst=outdir / src.name; preset,_,_=rl.suggest_parallel_rl(src.name); preset['label']=src.name; ok=impose_file(src, dst, preset); print('SUKSES' if ok else 'GAGAL'); exit(0 if ok else 1)"
if %errorlevel%==0 (
  echo.
  echo [SUKSES] %NAME%
  for /f %%U in ('python -c "import json; print(json.load(open('config.json')).get('uda_folder','uda'))"') do set UDA=%%U
  if not exist "%UDA%" mkdir "%UDA%"
  move /Y "%INPUT%" "%UDA%\%NAME%" >nul
  echo [PINDAH] %NAME% -^> uda
) else (
  echo [GAGAL] cek error di atas (lihat ERROR_CODES.md)
)
pause
