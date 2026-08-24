@echo off
chcp 932 >nul
setlocal EnableExtensions

pushd "%~dp0.." >nul 2>nul
if errorlevel 1 (
    echo エラー：プロジェクトフォルダへ移動できません。
    echo 場所: %~dp0..
    echo.
    pause
    endlocal
    exit /b 1
)

echo ========================================
echo ロボットPCダッシュボードを起動しています
echo ========================================
echo プロジェクト: %CD%
echo 起動ファイル: pc\main_ui.py
echo.

if not exist ".venv\Scripts\python.exe" (
    echo エラー：仮想環境 .venv が見つかりません。
    echo 先に tools\setup_windows.bat を実行してください。
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

if not exist "pc\main_ui.py" (
    echo エラー：pc\main_ui.py が見つかりません。プロジェクト配置を確認してください。
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

echo 使用Python:
".venv\Scripts\python.exe" --version
echo Pythonパス: %CD%\.venv\Scripts\python.exe
echo.

".venv\Scripts\python.exe" pc\main_ui.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo 起動に失敗しました。上のエラーメッセージを確認してください。
    echo 終了コード: %EXIT_CODE%
    echo.
    pause
)

popd
endlocal
exit /b %EXIT_CODE%
