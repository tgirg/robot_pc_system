# 開発環境とミニPC配置

## 推奨環境

- OS: Windows 11
- Python: 3.11 以降を推奨
- 実行方法: 各PCで `tools\setup_windows.bat` を実行し、プロジェクト直下に `.venv` を作成する

## .venvを共有しない理由

`.venv` にはPCごとのPython実行ファイル、ライブラリ、パス情報が入ります。別のPCへコピーすると、パス不一致やDLL不一致で起動できないことがあります。

そのため、GitやUSBメモリで共有するのはソースコードと設定ファイルだけにし、`.venv` は各PCで作り直します。

## 各PCでsetup_windows.batを実行する理由

`tools\setup_windows.bat` は次を自動で行います。

- Python確認
- `.venv` 作成
- pip更新
- `requirements.txt` のインストール

これにより、ユーザーPC、チームメンバーPC、ロボット搭載ミニPCで同じ手順にできます。

## ミニPCでの推奨配置

ロボット搭載ミニPCでは、次の場所に置くことを推奨します。

```text
C:\robot_pc_system
```

OneDrive配下は同期中にファイルロックや遅延が起きることがあり、試合中や実機テスト中には不安定になる可能性があります。ミニPCではOneDrive外の固定フォルダを使うのが安全です。

## 共有するもの / 共有しないもの

共有するもの:

- `pc/`
- `esp32/`
- `docs/`
- `tools/`
- `requirements.txt`
- `README.md`
- `ENVIRONMENT.md`
- `pc/config.yaml` のテンプレートまたはチームで合意した設定

共有しないもの:

- `.venv/`
- `__pycache__/`
- `*.pyc`
- 個人の `.env`
- 大量のログCSV
- PC固有のIDE設定

## トラブル対応

### pythonコマンドがWindows Storeを開く

Windowsの「アプリ実行エイリアス」で `python.exe` がStore版を指していることがあります。`tools\setup_windows.bat` は `py -3` を優先します。うまくいかない場合はPython公式版をインストールし、再度セットアップしてください。

### PySide6が見つからない

次を実行してください。

```cmd
tools\setup_windows.bat
```

その後、次で確認します。

```cmd
tools\check_environment.bat
```

### ESP32のCOMポートがわからない

ESP32をUSB接続した状態で次を実行します。

```cmd
tools\list_ports.bat
```

表示されたCOMポートを `pc\config.yaml` の `serial.port`、`communication.usb.port`、`controllers.drive.port` に設定します。

### カメラが映らない

Mockモードではカメラ未接続でも起動できます。実カメラを使う場合は `pc\config.yaml` の `camera.index` と `camera.mock` を確認してください。
