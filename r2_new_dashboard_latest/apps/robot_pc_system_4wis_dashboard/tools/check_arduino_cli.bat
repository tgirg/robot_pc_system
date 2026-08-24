@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

set "ARDUINO_CLI="
set "ARDUINO_CLI_FALLBACK=C:\Program Files\Arduino CLI\arduino-cli.exe"

echo ========================================
echo Arduino CLI 環境チェック
echo ========================================
echo.

call :find_arduino_cli
if not defined ARDUINO_CLI (
    echo NG：arduino-cli が見つかりません。
    echo PATHに追加するか、次の場所にインストールしてください。
    echo %ARDUINO_CLI_FALLBACK%
    echo ダッシュボード本体はArduino CLIなしでも動作します。
    goto :error_end
)

echo OK：arduino-cli が見つかりました。
echo 使用Arduino CLI: %ARDUINO_CLI%
"%ARDUINO_CLI%" version
echo.

echo インストール済みcore:
"%ARDUINO_CLI%" core list
echo.

"%ARDUINO_CLI%" core list | findstr /i "esp32:esp32" >nul
if errorlevel 1 (
    echo NG：ESP32 core が見つかりません。
    echo tools\setup_arduino_cli.bat を実行してください。
) else (
    echo OK：ESP32 core がインストールされています。
)
echo.

echo 接続ボード一覧:
"%ARDUINO_CLI%" board list
echo.
echo ESP32未接続でもコンパイル確認は可能です
echo.

if exist "esp32\drive_controller\drive_controller.ino" (
    echo OK：esp32\drive_controller\drive_controller.ino があります。
) else (
    echo NG：esp32\drive_controller\drive_controller.ino が見つかりません。
)

echo.
echo Arduino CLI 環境チェック完了
goto :end

:find_arduino_cli
where arduino-cli >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%A in ('where arduino-cli 2^>nul') do (
        set "ARDUINO_CLI=%%A"
        goto :eof
    )
)
if exist "%ARDUINO_CLI_FALLBACK%" (
    set "ARDUINO_CLI=%ARDUINO_CLI_FALLBACK%"
)
goto :eof

:error_end
echo.
pause
popd
endlocal
exit /b 1

:end
echo.
pause
popd
endlocal
