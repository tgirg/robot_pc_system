@echo off
chcp 65001 >nul
setlocal EnableExtensions

pushd "%~dp0.." >nul 2>nul
if errorlevel 1 (
    echo NG プロジェクトフォルダへ移動できません。
    echo 場所: %~dp0..
    pause
    endlocal
    exit /b 1
)

echo ========================================
echo ダッシュボード起動前チェック
echo ========================================
echo プロジェクト: %CD%
echo.

set "NG=0"

if exist ".venv" (
    echo OK .venv があります
) else (
    echo NG .venv がありません
    set "NG=1"
)

if exist ".venv\Scripts\python.exe" (
    echo OK .venv\Scripts\python.exe があります
) else (
    echo NG .venv\Scripts\python.exe がありません
    set "NG=1"
)

if exist "pc\main_ui.py" (
    echo OK pc\main_ui.py があります
) else (
    echo NG pc\main_ui.py がありません
    set "NG=1"
)

echo.
echo Python / ライブラリ確認:
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version
    ".venv\Scripts\python.exe" -c "import importlib.util, sys; mods=['PySide6','cv2','serial','numpy','yaml']; missing=[]; [print(('OK ' if importlib.util.find_spec(m) else 'NG ') + m) or (missing.append(m) if importlib.util.find_spec(m) is None else None) for m in mods]; sys.exit(1 if missing else 0)"
    if errorlevel 1 set "NG=1"
) else (
    echo NG Python確認を実行できません
)

echo.
if "%NG%"=="0" (
    echo 起動前チェックはOKです。
) else (
    echo 起動前チェックでNGがあります。tools\setup_windows.bat を実行してください。
)
echo.
pause
popd >nul
endlocal
exit /b %NG%
