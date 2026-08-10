@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0.." >nul

echo デスクトップショートカットを作成しています...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo 完了しました。デスクトップの「ロボットPCダッシュボード」を確認してください。
) else (
    echo ショートカット作成に失敗しました。上のメッセージを確認してください。
)
echo.
pause
popd >nul
endlocal
exit /b %EXIT_CODE%
