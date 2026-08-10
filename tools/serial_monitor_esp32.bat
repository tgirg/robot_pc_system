@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

set "PORT=%~1"
set "BAUD=115200"

echo ========================================
echo ESP32 シリアルモニタ
echo ========================================
echo.

where arduino-cli >nul 2>nul
if errorlevel 1 (
    echo NG：arduino-cli が見つかりません。
    echo Arduino CLIをインストールし、PATHに追加してください。
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

if "%PORT%"=="" (
    if exist ".venv\Scripts\python.exe" (
        for /f "usebackq delims=" %%P in (`.venv\Scripts\python.exe -c "import yaml; c=yaml.safe_load(open('pc/config.yaml', encoding='utf-8')) or {}; print(((c.get('controllers') or {}).get('drive') or {}).get('port') or (c.get('serial') or {}).get('port') or '')" 2^>nul`) do set "PORT=%%P"
    )
)

if "%PORT%"=="" (
    echo COMポートが指定されていません。
    arduino-cli board list
    echo.
    echo 使い方:
    echo   tools\serial_monitor_esp32.bat COM10
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

echo 使用COMポート: %PORT%
echo ボーレート: %BAUD%
echo 終了するときは Ctrl+C を押してください。
echo.

arduino-cli monitor -p %PORT% --config baudrate=%BAUD%

echo.
echo シリアルモニタを終了しました。
echo.
pause
popd
endlocal
