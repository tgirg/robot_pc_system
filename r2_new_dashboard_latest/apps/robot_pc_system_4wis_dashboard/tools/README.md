# tools フォルダ

Windowsでチームメンバーやロボット搭載ミニPCが同じ手順で準備・起動できるようにするための補助ツールです。

## ダッシュボード用ツール

- `setup_windows.bat`: 初回セットアップ用。`.venv` を作成し、必要ライブラリをインストールします。
- `run_dashboard.bat`: ダッシュボード起動用。通常はこれを実行します。
- `check_environment.bat`: Python、主要ライブラリ、必要ファイルの存在を確認します。
- `clean_cache.bat`: `__pycache__` や `*.pyc` を削除します。`.venv` と設定ファイルは削除しません。
- `list_ports.bat`: ESP32のCOMポート確認用です。

## Arduino CLI / ESP32用ツール

- `setup_arduino_cli.bat`: Arduino CLIが利用できる場合にESP32 coreをセットアップします。
- `check_arduino_cli.bat`: Arduino CLI、ESP32 core、接続ボード、スケッチの存在を確認します。
- `upload_esp32_drive.bat`: `esp32\drive_controller` をコンパイルしてESP32へ書き込みます。
- `serial_monitor_esp32.bat`: ESP32のシリアルモニタを開きます。
- `arduino_cli_guide.md`: Arduino CLIの導入とトラブル対応メモです。

Arduino CLIは任意です。インストールされていなくても、PCダッシュボードは動作します。

## 基本手順

1. `tools\setup_windows.bat` を実行
2. `tools\check_environment.bat` で確認
3. `tools\run_dashboard.bat` で起動

ESP32を書き込む場合:

1. Arduino CLIをインストールしてPATHを通す
2. `tools\setup_arduino_cli.bat` を実行
3. `tools\check_arduino_cli.bat` で確認
4. `tools\upload_esp32_drive.bat COM10` を実行

PowerShellの実行ポリシー変更は不要です。ダブルクリックまたはコマンドプロンプトから実行できます。

## ESP32未接続でのコンパイル確認

- `compile_esp32_drive.bat`: ESP32を接続せずに `esp32\drive_controller` をコンパイルします。COMポートは不要です。
- `upload_esp32_drive.bat`: ESP32接続後にコンパイルして書き込みます。
- `check_arduino_cli.bat`: Arduino CLI、ESP32 core、接続ボード一覧を確認します。

Arduino CLIはPATH上の `arduino-cli` を優先し、見つからない場合は `C:\Program Files\Arduino CLI\arduino-cli.exe` を確認します。

## デスクトップ起動用ツール

- `run_dashboard.bat`: プロジェクト位置を自動検出し、`.venv\Scripts\python.exe` で `pc\main_ui.py` を起動します。起動失敗時はウィンドウを閉じずにエラーを表示します。
- `run_dashboard_silent.vbs`: ショートカット用の静音ランチャーです。大きなコンソールを出さずに `run_dashboard.bat` を起動します。
- `create_desktop_shortcut.ps1`: デスクトップに `ロボットPCダッシュボード.lnk` を作成します。
- `create_desktop_shortcut.bat`: PowerShell実行ポリシーを変更せず、`create_desktop_shortcut.ps1` を実行します。
- `check_startup.bat`: `.venv`、起動ファイル、主要ライブラリを確認します。ダッシュボードは起動しません。
- `make_icon.py`: 任意ツールです。Pillowがある場合、`assets\app_icon.png` から `assets\app_icon.ico` を作ります。

ショートカット作成:

```cmd
tools\create_desktop_shortcut.bat
```

起動トラブル確認:

```cmd
tools\check_startup.bat
tools\run_dashboard.bat
```
