@echo off
setlocal
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"

if /i not "%~1"=="/yes" (
    echo This prepares a project-local Python environment and installs Panda3D.
    choice /c YN /m "Continue"
    if errorlevel 2 exit /b 1
)

set "BOOTSTRAP_PYTHON="
if exist "C:\Python313\python.exe" set "BOOTSTRAP_PYTHON=C:\Python313\python.exe"
if not defined BOOTSTRAP_PYTHON (
    for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined BOOTSTRAP_PYTHON set "BOOTSTRAP_PYTHON=%%P"
)
if not defined BOOTSTRAP_PYTHON (
    echo ERROR: Python was not found. Install Python 3, then run this launcher again.
    exit /b 1
)

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    "%BOOTSTRAP_PYTHON%" -m venv --upgrade "%PROJECT_ROOT%\.venv"
) else (
    "%BOOTSTRAP_PYTHON%" -m venv "%PROJECT_ROOT%\.venv"
)
if errorlevel 1 exit /b 1

"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m pip install -r "%PROJECT_ROOT%\requirements.txt"
if errorlevel 1 exit /b 1

echo Setup complete. Start the desired mode again.
exit /b 0
