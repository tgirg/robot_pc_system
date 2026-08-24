@echo off
setlocal EnableExtensions

if not defined ROBOT_DASHBOARD_APPDIR set "ROBOT_DASHBOARD_APPDIR=%~dp0apps\robot_pc_system"
if not defined ROBOT_DASHBOARD_RUNNER set "ROBOT_DASHBOARD_RUNNER=run-robot-dashboard.cmd"
set "APPDIR=%ROBOT_DASHBOARD_APPDIR%"
if not defined ROBOT_DASHBOARD_VENV set "ROBOT_DASHBOARD_VENV=C:\robot_venvs\robot_pc_dashboard_4wis_new_py312"
set "VENV=%ROBOT_DASHBOARD_VENV%"
set "PYTHON=%VENV%\Scripts\python.exe"
set "ROBOT_DASHBOARD_PYTHON=%PYTHON%"

if not exist "%APPDIR%\requirements.txt" (
  echo robot_pc_system requirements were not found: %APPDIR%\requirements.txt
  exit /b 1
)

if exist "%PYTHON%" (
  "%PYTHON%" -c "import sys; print(sys.version)" >nul 2>nul
  if errorlevel 1 (
    echo Existing dashboard virtual environment is broken. Recreating it...
    rmdir /s /q "%VENV%"
  ) else (
    "%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)" >nul 2>nul
    if errorlevel 1 (
      echo Existing dashboard virtual environment is not Python 3.11 or 3.12. Recreating it...
      rmdir /s /q "%VENV%"
    )
  )
)

if not exist "%PYTHON%" (
  echo Creating dashboard virtual environment...
  if exist "C:\robot_venvs\robot_project_kicad\Scripts\python.exe" (
    "C:\robot_venvs\robot_project_kicad\Scripts\python.exe" -m venv "%VENV%"
  ) else (
    py -3.12 -m venv "%VENV%"
    if errorlevel 1 py -3.11 -m venv "%VENV%"
    if errorlevel 1 py -3 -m venv "%VENV%"
  )
  if errorlevel 1 (
    echo Could not create the virtual environment. Install Python 3.12/3.11 or fix the py launcher.
    exit /b 1
  )
)

"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON%" -m pip install -r "%APPDIR%\requirements.txt"
if errorlevel 1 exit /b %ERRORLEVEL%

echo Dashboard environment is ready.
echo Start it with %ROBOT_DASHBOARD_RUNNER%
