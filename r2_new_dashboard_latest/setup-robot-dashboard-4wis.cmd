@echo off
setlocal EnableExtensions

set "ROBOT_DASHBOARD_APPDIR=%~dp0apps\robot_pc_system_4wis_dashboard"
set "ROBOT_DASHBOARD_RUNNER=run-robot-dashboard-4wis.cmd"

call "%~dp0setup-robot-dashboard.cmd"
exit /b %ERRORLEVEL%
