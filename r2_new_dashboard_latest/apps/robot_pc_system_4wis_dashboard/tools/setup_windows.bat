@echo off
chcp 932 >nul
setlocal
pushd "%~dp0.."

echo ========================================
echo R2 / NHK ロボット制御環境 セットアップ
echo ========================================
echo.

call :find_python
if errorlevel 1 goto :python_error

echo Pythonを確認しています...
%PYTHON_CMD% --version
if errorlevel 1 goto :python_error

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo 仮想環境を作成しています...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :venv_error
) else (
    echo.
    echo 既存の仮想環境を使用します。
)

echo.
echo 仮想環境を有効化しています...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :venv_error

echo.
echo pipを更新しています...
python -m pip install --upgrade pip
if errorlevel 1 goto :pip_error

echo.
echo 必要ライブラリをインストールしています...
python -m pip install -r requirements.txt
if errorlevel 1 goto :pip_error

echo.
echo セットアップ完了
echo 次は tools\run_dashboard.bat を実行してください。
goto :end

:find_python
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)
exit /b 1

:python_error
echo.
echo エラー：Pythonが見つかりません。
echo Python 3.11以降をインストールしてから、もう一度実行してください。
goto :end

:venv_error
echo.
echo エラー：仮想環境の作成または有効化に失敗しました。
goto :end

:pip_error
echo.
echo エラー：ライブラリのインストールに失敗しました。
echo インターネット接続と requirements.txt を確認してください。
goto :end

:end
echo.
pause
popd
endlocal
