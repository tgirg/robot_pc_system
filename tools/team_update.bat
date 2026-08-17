@echo off
setlocal

echo [team update] Fetch and fast-forward main from GitHub.
echo.

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo ERROR: Run this inside a Git repository.
  exit /b 1
)

for /f "tokens=*" %%i in ('git status --porcelain') do (
  echo ERROR: Working tree has uncommitted changes.
  echo Commit or save your changes before updating.
  echo.
  git status --short
  exit /b 1
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo ERROR: origin remote is not configured.
  exit /b 1
)

echo Fetching origin...
git fetch origin
if errorlevel 1 exit /b 1

echo Switching to main...
git checkout main
if errorlevel 1 exit /b 1

echo Pulling origin/main...
git pull --ff-only origin main
if errorlevel 1 (
  echo.
  echo ERROR: Could not fast-forward main. Resolve Git history or conflicts first.
  exit /b 1
)

echo.
echo Done: main is up to date.
git log -1 --oneline
