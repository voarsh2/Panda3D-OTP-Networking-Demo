@echo off
setlocal
call "%~dp0demo_env.bat"
if errorlevel 1 exit /b 1

set "MODE=%~1"
set "NAME=%~2"
if not defined NAME set "NAME=Guest"
if not defined MODE set "MODE=fixed"
title Panda3D Networking Demo - Client (%MODE%)
pushd "%PROJECT_ROOT%"

if /i "%MODE%"=="fixed" "%PYTHON_EXE%" -m demo.client --name "%NAME%"
if /i "%MODE%"=="grid-local" "%PYTHON_EXE%" -m demo.cartesian_grid_client --name "%NAME%" --show-grid
if /i "%MODE%"=="grid-ai" "%PYTHON_EXE%" -m demo.cartesian_grid_client --name "%NAME%" --show-grid --server-grid-interest
if /i "%MODE%"=="ui-grid-local" "%PYTHON_EXE%" tests\cartesian_grid_live.py --ui --name "%NAME%"
if /i "%MODE%"=="ui-grid-ai" "%PYTHON_EXE%" tests\cartesian_grid_live.py --ui --server-grid-interest --name "%NAME%"
if /i not "%MODE%"=="fixed" if /i not "%MODE%"=="grid-local" if /i not "%MODE%"=="grid-ai" if /i not "%MODE%"=="ui-grid-local" if /i not "%MODE%"=="ui-grid-ai" (
    echo ERROR: Unknown client mode "%MODE%".
    popd
    exit /b 2
)

set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
