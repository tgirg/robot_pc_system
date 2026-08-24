@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

echo ========================================
echo キャッシュ削除
echo ========================================
echo.
echo __pycache__ と *.pyc を削除します。
echo .venv、config.yaml、ソースコードは削除しません。
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    ) else (
        set "PYTHON_CMD=python"
    )
)

%PYTHON_CMD% -c "from pathlib import Path; import shutil; root=Path.cwd(); [print(f'削除: {p}') or shutil.rmtree(p, ignore_errors=True) for p in root.rglob('__pycache__') if '.venv' not in p.parts]; [print(f'削除: {p}') or p.unlink(missing_ok=True) for p in root.rglob('*.pyc') if '.venv' not in p.parts]"

echo.
set /p DELETE_LOGS=古いログ（logs\*.csv と logs\*.log）も削除しますか？ [y/N]: 
if /i "%DELETE_LOGS%"=="y" (
    if exist "logs\*.csv" del /q "logs\*.csv"
    if exist "logs\*.log" del /q "logs\*.log"
    echo ログを削除しました。
) else (
    echo ログは削除しません。
)

echo.
echo クリーン完了
echo.
pause
popd
endlocal