@echo off
REM One-click local run (Windows). Double-click, or:
REM   run_local.bat                 process every date found in samples\
REM   run_local.bat 20260410 20260414   only these dates
REM   run_local.bat --install       pip install -r requirements.txt first
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="
for %%P in (python py) do (
  if not defined PY (
    where %%P >nul 2>&1 && set "PY=%%P"
  )
)
if not defined PY (
  echo ERROR: python not found on PATH
  pause
  exit /b 1
)

set "DATES="
for %%A in (%*) do (
  if "%%A"=="--install" (
    "%PY%" -m pip install -r requirements.txt
  ) else (
    set "DATES=!DATES! %%A"
  )
)

if "!DATES!"=="" (
  for %%F in (samples\*.json samples\*.png samples\*.jpg samples\*.jpeg) do (
    set "n=%%~nF"
    set "DATES=!DATES! !n!"
  )
)

if "!DATES!"=="" (
  echo ERROR: no dates found. Put 20260410.json or .png in samples\
  pause
  exit /b 1
)

echo Processing dates:!DATES!
for %%D in (!DATES!) do (
  echo --- %%D ---
  "%PY%" -m pipeline.run "samples\%%D.png"
)

echo --- combined report ---
"%PY%" -m pipeline.combined !DATES!

echo.
echo Done. See the output\ folder.
pause
