@echo off
setlocal
call "%~dp0demo_env.bat"
if errorlevel 1 exit /b 1

set "MODE=%~1"
if not defined MODE set "MODE=fixed"
title Panda3D Networking Demo - AI (%MODE%)
pushd "%PROJECT_ROOT%"

if /i "%MODE%"=="fixed" "%PYTHON_EXE%" -m demo.ai_server
if /i "%MODE%"=="grid-local" "%PYTHON_EXE%" -m demo.ai_server --cartesian-grid
if /i "%MODE%"=="grid-ai" "%PYTHON_EXE%" -m demo.ai_server --cartesian-grid --ai-grid-interest
if /i not "%MODE%"=="fixed" if /i not "%MODE%"=="grid-local" if /i not "%MODE%"=="grid-ai" (
    echo ERROR: Unknown AI mode "%MODE%".
    popd
    exit /b 2
)

set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
