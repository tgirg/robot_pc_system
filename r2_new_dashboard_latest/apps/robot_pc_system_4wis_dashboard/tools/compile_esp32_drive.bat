@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

rem 実際のESP32ボードに合わせて変更してください。
rem よく使う候補:
rem   esp32:esp32:esp32
rem   esp32:esp32:esp32c3
rem   esp32:esp32:esp32c5
rem   esp32:esp32:esp32s3
set "FQBN=esp32:esp32:esp32"
set "ARDUINO_CLI="
set "ARDUINO_CLI_FALLBACK=C:\Program Files\Arduino CLI\arduino-cli.exe"

echo ========================================
echo ESP32 走行コントローラ コンパイル確認
echo ========================================
echo.
echo モータ出力は既定で無効です
echo IMUは既定でダミーモードです
echo.

call :find_arduino_cli
if not defined ARDUINO_CLI goto :cli_error

if not exist "esp32\drive_controller\drive_controller.ino" (
    echo NG：スケッチが見つかりません。
    echo esp32\drive_controller\drive_controller.ino を確認してください。
    goto :error_end
)

echo 使用Arduino CLI: %ARDUINO_CLI%
echo 使用FQBN: %FQBN%
echo.
echo コンパイルしています...
"%ARDUINO_CLI%" compile --fqbn %FQBN% esp32\drive_controller
if errorlevel 1 goto :compile_error

echo.
echo OK：ESP32走行コントローラのコンパイルに成功しました。
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
echo FQBNが実ボードと違う場合があります。
echo ESP32-C5の場合は esp32:esp32:esp32c5 などを確認してください。
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
