@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

echo ========================================
echo COMポート一覧
echo ========================================
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

%PYTHON_CMD% -c "import serial.tools.list_ports" >nul 2>nul
if errorlevel 1 (
    echo pyserial が見つかりません。
    echo 先に tools\setup_windows.bat を実行してください。
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

%PYTHON_CMD% -c "from serial.tools import list_ports; ports=list(list_ports.comports()); print('検出されたCOMポート:'); [print(f'{p.device}  {p.description}') for p in ports] if ports else print('COMポートは見つかりませんでした。')"

echo.
echo ESP32を接続した状態で再実行すると、COMポートを確認できます。
echo.
pause
popd
endlocal
