@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

rem 実際の環境に合わせて編集してください。引数でCOMポートを渡した場合はそちらを優先します。
set "PORT=COM10"
set "FQBN=esp32:esp32:esp32"
set "ARDUINO_CLI="
set "ARDUINO_CLI_FALLBACK=C:\Program Files\Arduino CLI\arduino-cli.exe"

rem よく使うFQBN候補:
rem   esp32:esp32:esp32
rem   esp32:esp32:esp32c3
rem   esp32:esp32:esp32c5
rem   esp32:esp32:esp32s3

if not "%~1"=="" set "PORT=%~1"

echo ========================================
echo ESP32 走行コントローラ 書き込み
echo ========================================
echo.
echo 書き込み前にArduino IDEのシリアルモニタを閉じてください
echo モータ出力は既定で無効です
echo.

call :find_arduino_cli
if not defined ARDUINO_CLI goto :cli_error

if not exist "esp32\drive_controller\drive_controller.ino" (
    echo NG：スケッチが見つかりません。
    echo esp32\drive_controller\drive_controller.ino を確認してください。
    goto :error_end
)

echo 使用Arduino CLI: %ARDUINO_CLI%
echo 使用COMポート: %PORT%
echo 使用FQBN: %FQBN%
echo.

echo コンパイルしています...
"%ARDUINO_CLI%" compile --fqbn %FQBN% esp32\drive_controller
if errorlevel 1 goto :compile_error

echo.
echo ESP32へ書き込んでいます...
"%ARDUINO_CLI%" upload -p %PORT% --fqbn %FQBN% esp32\drive_controller
if errorlevel 1 goto :upload_error

echo.
echo 書き込み完了
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

:cli_error
echo NG：arduino-cli が見つかりません。
echo PATHに追加するか、次の場所にインストールしてください。
echo %ARDUINO_CLI_FALLBACK%
goto :error_end

:compile_error
echo.
echo エラー：コンパイルに失敗しました。
echo FQBN、ESP32 core、スケッチを確認してください。
echo ESP32-C5の場合は esp32:esp32:esp32c5 などを確認してください。
goto :error_end

:upload_error
echo.
echo エラー：書き込みに失敗しました。
echo COMポート、USBケーブル、BOOTボタン、Arduino IDEのシリアルモニタを確認してください。
goto :error_end

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
