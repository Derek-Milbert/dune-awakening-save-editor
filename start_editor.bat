@echo off
rem Starts the Dune: Awakening Save Editor and opens it in your browser.
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto :nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :nopython

%PY% run.py %*
if errorlevel 1 (
  echo.
  echo The editor stopped with an error - see the message above.
)
pause
exit /b

:nopython
echo.
echo Python 3.10 or newer is required (nothing else needs installing).
echo Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" in the installer,
echo then double-click this file again.
echo.
pause
exit /b 1
