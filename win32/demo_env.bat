@echo off
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"

set "PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%"
call :find_python
if not defined PYTHON_EXE goto :setup_environment
goto :have_environment

:setup_environment
echo Panda3D dependencies are missing.
choice /c YN /m "Create .venv and install project requirements"
if errorlevel 2 exit /b 1
call "%~dp0setup_demo.bat" /yes
if errorlevel 1 exit /b 1
call :find_python
if not defined PYTHON_EXE (
    echo ERROR: Setup completed without finding a usable Python environment.
    exit /b 1
)

:have_environment

set "PYTHONW_EXE=%PYTHON_EXE:python.exe=pythonw.exe%"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"
exit /b 0

:find_python
set "PYTHON_EXE="
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    "%PROJECT_ROOT%\.venv\Scripts\python.exe" -c "import panda3d; import demo.networking.client_repository; import demo.networking.internal_repository" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
)
if not defined PYTHON_EXE if exist "C:\Python313\python.exe" (
    "C:\Python313\python.exe" -c "import panda3d; import demo.networking.client_repository; import demo.networking.internal_repository" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=C:\Python313\python.exe"
)
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE (
        "%%P" -c "import panda3d; import demo.networking.client_repository; import demo.networking.internal_repository" >nul 2>&1
        if not errorlevel 1 set "PYTHON_EXE=%%P"
    )
)
exit /b 0
