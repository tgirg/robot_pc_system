@echo off
setlocal

if "%~1"=="" (
  echo Usage:
  echo tools\team_publish_feature.bat "commit message"
  echo.
  echo Example:
  echo tools\team_publish_feature.bat "Add field object editor"
  exit /b 1
)

set MESSAGE=%~1

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo ERROR: Run this inside a Git repository.
  exit /b 1
)

for /f "tokens=*" %%b in ('git branch --show-current') do set CURRENT_BRANCH=%%b
if "%CURRENT_BRANCH%"=="main" (
  echo ERROR: Do not publish directly from main.
  echo Run tools\team_start_feature.bat feature/work-name first.
  exit /b 1
)

echo [team publish] Current changes:
echo.
git status --short
echo.
echo This will commit and push all current changes.
echo Branch: %CURRENT_BRANCH%
echo Message: %MESSAGE%
echo.
set /p ANSWER=Continue? y/N: 
if /i not "%ANSWER%"=="y" (
  echo Canceled.
  exit /b 1
)

git add -A
if errorlevel 1 exit /b 1

git commit -m "%MESSAGE%"
if errorlevel 1 exit /b 1

git push -u origin "%CURRENT_BRANCH%"
if errorlevel 1 exit /b 1

echo.
echo Done: pushed to GitHub.
echo Create a Pull Request on GitHub.
