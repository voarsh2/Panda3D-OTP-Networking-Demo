@echo off
setlocal
set "MODE=%~1"
if not defined MODE set "MODE=fixed"
set "UI_CHECK=0"

if /i "%MODE%"=="fixed" (
    set "ASTRON_CONFIG=astron.yml"
    set "AI_MODE=fixed"
    set "CLIENT_MODE=fixed"
    set "CLIENT_NAME=Alice"
    goto launch
)
if /i "%MODE%"=="grid-local" (
    set "ASTRON_CONFIG=astron-cartesian-grid.yml"
    set "AI_MODE=grid-local"
    set "CLIENT_MODE=grid-local"
    set "CLIENT_NAME=Alice"
    goto launch
)
if /i "%MODE%"=="grid-ai" (
    set "ASTRON_CONFIG=astron-cartesian-grid.yml"
    set "AI_MODE=grid-ai"
    set "CLIENT_MODE=grid-ai"
    set "CLIENT_NAME=Alice"
    goto launch
)
if /i "%MODE%"=="ui-grid-local" (
    set "UI_CHECK=1"
    set "ASTRON_CONFIG=astron-cartesian-grid.yml"
    set "AI_MODE=grid-local"
    set "CLIENT_MODE=ui-grid-local"
    set "CLIENT_NAME=GridLocalCheck"
    goto launch
)
if /i "%MODE%"=="ui-grid-ai" (
    set "UI_CHECK=1"
    set "ASTRON_CONFIG=astron-cartesian-grid.yml"
    set "AI_MODE=grid-ai"
    set "CLIENT_MODE=ui-grid-ai"
    set "CLIENT_NAME=GridAICheck"
    goto launch
)

echo ERROR: Unknown demo mode "%MODE%".
exit /b 2

:launch
call "%~dp0demo_env.bat"
if errorlevel 1 (
    echo Demo setup was not completed.
    pause
    exit /b 1
)

echo Checking for an existing demo stack...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 7199 -InformationLevel Quiet) -or (Test-NetConnection -ComputerName 127.0.0.1 -Port 6667 -InformationLevel Quiet)) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo ERROR: A service is already listening on demo port 7199 or 6667.
    echo Stop the current stack before starting another mode.
    pause
    exit /b 1
)

set "PANDA_DEMO_AI_READY_FILE=%TEMP%\Panda3D-OTP-%RANDOM%-%RANDOM%-ai.ready"
set "PANDA_DEMO_UD_READY_FILE=%TEMP%\Panda3D-OTP-%RANDOM%-%RANDOM%-ud.ready"

start "Panda3D Astron - %MODE%" "%ComSpec%" /k call "%~dp0start_astron.bat" "%ASTRON_CONFIG%"
echo Waiting for Astron Message Director and Client Agent...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$deadline = (Get-Date).AddSeconds(15); do { if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 7199 -InformationLevel Quiet) -and (Test-NetConnection -ComputerName 127.0.0.1 -Port 6667 -InformationLevel Quiet)) { exit 0 }; Start-Sleep -Milliseconds 250 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo ERROR: Astron did not open ports 7199 and 6667 within 15 seconds.
    echo Check the Astron window for configuration or runtime errors.
    pause
    exit /b 1
)

start "Panda3D UberDOG - %MODE%" "%ComSpec%" /k call "%~dp0start_uberdog.bat"
echo Waiting for UberDOG's login manager before starting AI...
call :wait_for_ready "%PANDA_DEMO_UD_READY_FILE%"
if errorlevel 1 (
    echo ERROR: UberDOG did not report ready within 30 seconds.
    echo AI and clients were not started. Check the UberDOG window.
    del /q "%PANDA_DEMO_AI_READY_FILE%" "%PANDA_DEMO_UD_READY_FILE%" >nul 2>&1
    pause
    exit /b 1
)

start "Panda3D AI - %MODE%" "%ComSpec%" /k call "%~dp0start_ai.bat" "%AI_MODE%"
echo Waiting for the AI District...
call :wait_for_ready "%PANDA_DEMO_AI_READY_FILE%"
if errorlevel 1 (
    echo ERROR: AI did not publish its District within 30 seconds.
    echo Clients were not started. Check the AI window.
    del /q "%PANDA_DEMO_AI_READY_FILE%" "%PANDA_DEMO_UD_READY_FILE%" >nul 2>&1
    pause
    exit /b 1
)
del /q "%PANDA_DEMO_AI_READY_FILE%" "%PANDA_DEMO_UD_READY_FILE%" >nul 2>&1
set "PANDA_DEMO_AI_READY_FILE="
set "PANDA_DEMO_UD_READY_FILE="

if "%UI_CHECK%"=="1" (
    start "Panda3D UI Check - %MODE%" "%ComSpec%" /k call "%~dp0start_client.bat" "%CLIENT_MODE%" "%CLIENT_NAME%"
) else (
    start "Panda3D Alice - %MODE%" "%ComSpec%" /k call "%~dp0start_client.bat" "%CLIENT_MODE%" "Alice"
    start "Panda3D Bob - %MODE%" "%ComSpec%" /k call "%~dp0start_client.bat" "%CLIENT_MODE%" "Bob"
)
exit /b 0

:wait_for_ready
set "PANDA_DEMO_WAIT_FILE=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$path = $env:PANDA_DEMO_WAIT_FILE; $directory = Split-Path -Path $path; $filter = Split-Path -Path $path -Leaf; $watcher = [System.IO.FileSystemWatcher]::new($directory, $filter); $watcher.EnableRaisingEvents = $true; try { $deadline = (Get-Date).AddSeconds(30); while (!(Test-Path -LiteralPath $path)) { $remaining = [int][Math]::Max(1, ($deadline - (Get-Date)).TotalMilliseconds); $change = $watcher.WaitForChanged([IO.WatcherChangeTypes]::Created, $remaining); if ($change.TimedOut -and !(Test-Path -LiteralPath $path)) { exit 1 } }; exit 0 } finally { $watcher.Dispose() }"
set "WAIT_RESULT=%ERRORLEVEL%"
set "PANDA_DEMO_WAIT_FILE="
exit /b %WAIT_RESULT%
