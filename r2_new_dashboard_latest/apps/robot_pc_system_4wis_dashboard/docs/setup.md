# セットアップ

## 推奨手順（batファイル）

チームメンバーのPC、ユーザーPC、ロボット搭載ミニPCでは、次の手順を使います。

```cmd
tools\setup_windows.bat
tools\check_environment.bat
tools\run_dashboard.bat
```

PowerShellの実行ポリシー変更は不要です。ダブルクリックまたはコマンドプロンプトから実行できます。

## メンバー用手順

1. プロジェクト一式を受け取る
2. `tools\setup_windows.bat` を実行
3. `tools\check_environment.bat` で `OK` を確認
4. `tools\run_dashboard.bat` で起動

`.venv` は共有せず、各PCで作成します。

## ミニPC用手順

ミニPCでは次の配置を推奨します。

```text
C:\robot_pc_system
```

手順:

1. プロジェクトを `C:\robot_pc_system` に配置
2. `tools\setup_windows.bat` を実行
3. ESP32を接続
4. `tools\list_ports.bat` でCOMポートを確認
5. `pc\config.yaml` のCOMポート設定を更新
6. `tools\run_dashboard.bat` で起動

OneDrive配下は同期による遅延やファイルロックが起きることがあるため、実機運用では避けることを推奨します。

## 手動セットアップ

batファイルを使わない場合:

```cmd
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe pc\main_ui.py
```

検証:

```cmd
.venv\Scripts\python.exe -m compileall pc
```

## ESP32設定

ESP32のCOMポートは次で確認します。

```cmd
tools\list_ports.bat
```

確認したCOMポートを `pc\config.yaml` の次の場所に設定します。

- `serial.port`
- `communication.usb.port`
- `controllers.drive.port`

## Arduino CLIでESP32を書き込む場合

Arduino CLIは任意です。PCダッシュボードはArduino CLIなしでも動作します。

Arduino CLIを使う場合は、Arduino CLIをインストールしてPATHを通したあと、次を実行します。

```cmd
tools\setup_arduino_cli.bat
tools\check_arduino_cli.bat
tools\upload_esp32_drive.bat COM10
```

COM番号は実際のESP32に合わせて変更してください。
FQBNが合わない場合は `tools\upload_esp32_drive.bat` の `FQBN` を変更します。
