@echo off
setlocal

if "%~1"=="" (
  echo Usage:
  echo tools\team_start_feature.bat feature/work-name
  echo.
  echo Example:
  echo tools\team_start_feature.bat feature/field-ui-fix
  exit /b 1
)

set BRANCH=%~1

echo [team start] Create a feature branch from latest main.
echo Branch: %BRANCH%
echo.

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo ERROR: Run this inside a Git repository.
  exit /b 1
)

for /f "tokens=*" %%i in ('git status --porcelain') do (
  echo ERROR: Working tree has uncommitted changes.
  echo Commit or save your changes before starting a new branch.
  echo.
  git status --short
  exit /b 1
)

git fetch origin
if errorlevel 1 exit /b 1

git checkout main
if errorlevel 1 exit /b 1

git pull --ff-only origin main
if errorlevel 1 (
  echo.
  echo ERROR: Could not update main.
  exit /b 1
)

git checkout -b "%BRANCH%"
if errorlevel 1 (
  echo.
  echo ERROR: Could not create branch. If it already exists, run:
  echo git checkout %BRANCH%
  exit /b 1
)

echo.
echo Done: feature branch is ready.
git branch --show-current
