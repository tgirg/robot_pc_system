@echo off
setlocal EnableExtensions

set "APPDIR=%~dp0apps\robot_pc_system_4wis_dashboard"
set "PROJECT_ROOT=%~dp0"
call :resolve_python
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

if not exist "%APPDIR%\pc\shared_dashboard_main.py" (
  echo Fake shared dashboard entrypoint was not found: %APPDIR%
  exit /b 1
)

if not exist "%PYTHON%" (
  call :prepare_env
  if errorlevel 1 exit /b 1
)

"%PYTHON%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  call :prepare_env
  if errorlevel 1 exit /b 1
)

set "PYTHONPATH=%PROJECT_ROOT%;%APPDIR%\pc;%PYTHONPATH%"
pushd "%PROJECT_ROOT%" >nul 2>nul
if errorlevel 1 (
  echo Failed to enter project root: %PROJECT_ROOT%
  exit /b 1
)

"%PYTHON%" "%APPDIR%\pc\shared_dashboard_main.py" %*
set "EXITCODE=%ERRORLEVEL%"

popd
exit /b %EXITCODE%

:resolve_python
if defined ROBOT_DASHBOARD_PYTHON (
  set "PYTHON=%ROBOT_DASHBOARD_PYTHON%"
  exit /b 0
)
if exist "C:\robot_venvs\robot_pc_dashboard_4wis_new_py312\Scripts\python.exe" (
  set "ROBOT_DASHBOARD_PYTHON=C:\robot_venvs\robot_pc_dashboard_4wis_new_py312\Scripts\python.exe"
) else if exist "C:\robot_venvs\robot_pc_dashboard\Scripts\python.exe" (
  set "ROBOT_DASHBOARD_PYTHON=C:\robot_venvs\robot_pc_dashboard\Scripts\python.exe"
) else (
  set "ROBOT_DASHBOARD_PYTHON=C:\robot_venvs\robot_pc_dashboard_4wis_new_py312\Scripts\python.exe"
)
set "PYTHON=%ROBOT_DASHBOARD_PYTHON%"
exit /b 0

:prepare_env
if "%ROBOT_DASHBOARD_AUTO_SETUP%"=="0" (
  echo Dashboard Python environment is not ready.
  echo Run setup-robot-dashboard-4wis.cmd first.
  echo Expected working Python: %PYTHON%
  exit /b 1
)
echo Preparing 4WIS dashboard Python environment...
call "%~dp0setup-robot-dashboard-4wis.cmd"
set "PYTHON=%ROBOT_DASHBOARD_PYTHON%"
exit /b %ERRORLEVEL%
