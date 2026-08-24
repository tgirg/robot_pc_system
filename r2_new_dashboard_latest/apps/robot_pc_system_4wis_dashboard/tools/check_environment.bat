@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

echo ========================================
echo 環境チェック
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

call :check_cmd "Pythonバージョン" "%PYTHON_CMD% --version"
call :check_cmd "pipバージョン" "%PYTHON_CMD% -m pip --version"
call :check_import "PySide6" "PySide6"
call :check_import "OpenCV cv2" "cv2"
call :check_import "pyserial serial" "serial"
call :check_import "numpy" "numpy"
call :check_import "PyYAML yaml" "yaml"
call :check_file "pc\main_ui.py" "メインUI"
call :check_file "pc\config.yaml" "設定ファイル"
call :check_dir "logs" "ログフォルダ"
call :check_dir "tools" "ツールフォルダ"

echo.
echo チェック完了
echo NGがある場合は tools\setup_windows.bat を実行してください。
echo.
pause
popd
endlocal
exit /b 0

:check_cmd
echo [%~1]
%~2 >nul 2>nul
if errorlevel 1 (
    echo NG：%~1 を確認できません。
) else (
    %~2
    echo OK：%~1 を確認しました。
)
echo.
exit /b 0

:check_import
echo [%~1]
%PYTHON_CMD% -c "import %~2" >nul 2>nul
if errorlevel 1 (
    echo NG：%~1 を読み込めません。
) else (
    echo OK：%~1 を読み込めます。
)
echo.
exit /b 0

:check_file
if exist "%~1" (
    echo OK：%~2 があります。%~1
) else (
    echo NG：%~2 が見つかりません。%~1
)
exit /b 0

:check_dir
if exist "%~1\" (
    echo OK：%~2 があります。%~1
) else (
    echo NG：%~2 が見つかりません。%~1
)
exit /b 0
