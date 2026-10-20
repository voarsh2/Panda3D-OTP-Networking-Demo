@echo off
setlocal
call "%~dp0demo_env.bat"
if errorlevel 1 exit /b 1

set "BUNDLED_ASTRON=%PROJECT_ROOT%\demo\astron\astrond.exe"
set "ASTRON_EXE=%BUNDLED_ASTRON%"
set "USING_BUNDLED_ASTRON=1"
set "ASTRON_CONFIG=%~1"
if not defined ASTRON_CONFIG set "ASTRON_CONFIG=astron.yml"
set "ASTRON_CONFIG=%PROJECT_ROOT%\demo\astron\config\%ASTRON_CONFIG%"

if not exist "%ASTRON_EXE%" (
    set "ASTRON_EXE="
    set "USING_BUNDLED_ASTRON="
    for /f "delims=" %%P in ('where astrond.exe 2^>nul') do if not defined ASTRON_EXE set "ASTRON_EXE=%%P"
)

if not exist "%ASTRON_EXE%" (
    echo ERROR: Astron binary not found: %ASTRON_EXE%
    echo Build Astron and add astrond.exe to PATH, or place it under demo\astron.
    pause
    exit /b 1
)
if not exist "%ASTRON_CONFIG%" (
    echo ERROR: Astron config not found: %ASTRON_CONFIG%
    pause
    exit /b 1
)
if defined USING_BUNDLED_ASTRON (
    call :check_legacy_runtime
    if errorlevel 1 exit /b 1
)

title Panda3D Networking Demo - Astron
pushd "%PROJECT_ROOT%"
"%ASTRON_EXE%" "%ASTRON_CONFIG%"
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:check_legacy_runtime
if exist "%PROJECT_ROOT%\demo\astron\msvcr120.dll" exit /b 0
if exist "%SystemRoot%\System32\msvcr120.dll" exit /b 0
where msvcr120.dll >nul 2>&1
if not errorlevel 1 exit /b 0
echo ERROR: Bundled Astron requires the Microsoft Visual C++ 2013 x64 runtime (MSVCR120.dll).
echo Install it from: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
exit /b 1
