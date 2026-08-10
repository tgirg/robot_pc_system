# デスクトップ起動

## 目的

ロボットPCダッシュボードを、PowerShellやコマンド入力なしでWindowsデスクトップから起動できるようにします。

現在はPyInstallerでexe化せず、ショートカット方式で起動します。この方式はプロジェクト構成を変えずに使えるため、開発中のダッシュボードには安全です。

## ショートカット作成

次のファイルをダブルクリックします。

```cmd
tools\create_desktop_shortcut.bat
```

作成されるショートカット:

```text
デスクトップ\ロボットPCダッシュボード.lnk
```

ショートカットは、通常 `tools\run_dashboard_silent.vbs` を起動します。静音起動がうまくいかない場合は、`tools\run_dashboard.bat` を直接実行してください。

## 起動方法

デスクトップの `ロボットPCダッシュボード` をダブルクリックします。

起動できない場合は、原因を見えるようにするため、次を直接実行します。

```cmd
tools\run_dashboard.bat
```

## 起動前チェック

起動に必要なファイルとライブラリを確認できます。

```cmd
tools\check_startup.bat
```

確認内容:

- `.venv` があるか
- `.venv\Scripts\python.exe` があるか
- `pc\main_ui.py` があるか
- PySide6 / cv2 / serial / numpy / yaml を読み込めるか

NGがある場合は、先に次を実行してください。

```cmd
tools\setup_windows.bat
```

## .venv が無い場合

ショートカットや `run_dashboard.bat` は `.venv` を使って起動します。

`.venv` が無い場合は、次を実行してください。

```cmd
tools\setup_windows.bat
```

## OneDrive配下で不安定な場合

OneDriveの同期中に仮想環境やログファイルが不安定になることがあります。ミニPCや実機テスト用PCでは、次の場所に置くことを推奨します。

```text
C:\robot_pc_system
```

移動後は、その場所で改めて `tools\setup_windows.bat` と `tools\create_desktop_shortcut.bat` を実行してください。

## アイコンを変更したい場合

`assets\app_icon.ico` を置くと、ショートカットとダッシュボードのアイコンに使われます。

PNGから作る場合は、任意で次を使えます。

```cmd
.venv\Scripts\python.exe tools\make_icon.py
```

`tools\make_icon.py` は `assets\app_icon.png` から `assets\app_icon.ico` を作ります。Pillow が必要ですが、メインの依存関係には追加していません。

## 起動ログ

ダッシュボード起動時に、次のファイルへ起動情報を追記します。

```text
logs\startup.log
```

記録内容:

- 起動時刻
- 起動状態
- プロジェクトパス
- Python実行ファイル
- 現在モード

ログ書き込みに失敗しても、ダッシュボード起動は止めません。

## 将来のexe化

PyInstallerなどによるexe化は将来対応できます。ただし、現在は開発中でPythonコードや設定を頻繁に変更するため、ショートカット方式の方が安全です。
# デスクトップ起動後のESP32書き込み

デスクトップショートカットから起動した場合でも、`診断` タブの `ESP32書き込み` セクションからArduino CLIを実行できます。

書き込みは自動では行われません。必ずユーザーが `ESP32へ書き込み` を押し、確認ダイアログで承認した場合だけ実行されます。
