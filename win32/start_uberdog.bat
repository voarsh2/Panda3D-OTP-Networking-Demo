@echo off
setlocal
call "%~dp0demo_env.bat"
if errorlevel 1 exit /b 1

title Panda3D Networking Demo - UberDOG
pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" -m demo.ud_server
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
