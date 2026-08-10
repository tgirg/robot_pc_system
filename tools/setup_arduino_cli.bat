@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

echo ========================================
echo Arduino CLI / ESP32 セットアップ
echo ========================================
echo.

where arduino-cli >nul 2>nul
if errorlevel 1 (
    echo NG：arduino-cli が見つかりません。
    echo Arduino CLIをインストールし、PATHに追加してください。
    echo 参考: tools\arduino_cli_guide.md
    echo.
    echo ダッシュボード本体はArduino CLIなしでも動作します。
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

echo arduino-cliを確認しています...
arduino-cli version
if errorlevel 1 goto :error

echo.
echo Arduino CLI設定を確認しています...
arduino-cli config dump >nul 2>nul
if errorlevel 1 (
    echo 設定ファイルを作成しています...
    arduino-cli config init
    if errorlevel 1 goto :error
) else (
    echo 設定ファイルは利用できます。
)

echo.
echo ESP32ボードマネージャURLを追加しています...
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json

echo.
echo ボード情報を更新しています...
arduino-cli core update-index
if errorlevel 1 goto :error

echo.
echo ESP32 coreをインストールしています...
arduino-cli core install esp32:esp32
if errorlevel 1 goto :error

echo.
echo Arduino CLI / ESP32 セットアップ完了
goto :end

:error
echo.
echo エラー：Arduino CLI / ESP32 セットアップに失敗しました。
echo ネットワーク接続、PATH、Arduino CLIのインストール状態を確認してください。

:end
echo.
pause
popd
endlocal
