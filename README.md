# R2 / NHK ロボット制御ダッシュボード

R2 / 将来のNHK Robocon向けに、ミニPCを中心にしたロボット開発環境を作るためのプロジェクトです。
PC側でUI、センサ統合、自己位置表示、ログ、シミュレーション、将来の自律制御を担当し、ESP32はモータ出力、エンコーダ読み取り、アクチュエータ制御、フェイルセーフ停止などの低レベルI/Oを担当します。

## クイックスタート

Windowsでは、まず次の順番で実行してください。

```cmd
tools\setup_windows.bat
tools\run_dashboard.bat
```

環境を確認したい場合:

```cmd
tools\check_environment.bat
```

ESP32のCOMポートを確認したい場合:

```cmd
tools\list_ports.bat
```

## ミニPCでの運用

ロボット搭載ミニPCでは、OneDrive配下ではなく次の場所に置くことを推奨します。

```text
C:\robot_pc_system
```

手順:

1. プロジェクトを `C:\robot_pc_system` に配置
2. `tools\setup_windows.bat` を実行
3. `tools\run_dashboard.bat` を実行
4. ESP32を使う場合は `tools\list_ports.bat` でCOMポートを確認
5. `pc\config.yaml` の `serial.port`、`communication.usb.port`、`controllers.drive.port` を実機に合わせる

## できること

- 日本語PySide6ダッシュボード表示
- ボタン操作ごとの処理中、成功、失敗表示
- Mock / Simulation / Real のデータ種別表示
- Mockカメラ、Mockセンサによる実機なしの動作確認
- ESP32へのUSBシリアル指令送信
- `DRIVE VEL 100 100` などのPC中心の走行指令
- 自己位置マップ、センサ値、接続状態、安全状態の表示
- Escキーまたはボタンによる緊急停止
- CSVログ保存
- Arduino CLIによるESP32スケッチのコンパイルと書き込み
- 将来のアーム / ツール / センサ用コントローラ構成の準備

## 操作フィードバック

時間がかかる操作では、ボタンの一時無効化、状態ラベル、進行バー、画面上部の最新通知で状況を表示します。
対象はESP32書き込み、ファームウェア編集、シリアルモニタ、実機接続、実機クイック確認です。
詳しくは `docs/loading_and_feedback.md` を参照してください。

## テストフィールド

`テストフィールド` タブでは、現在位置、向き、移動軌跡、開始地点からの距離、累積移動距離を確認できます。表示倍率はUIから変更でき、表示単位は `mm`、`cm`、`m` から選べます。詳しくは `docs/test_field.md` を参照してください。

## PCダッシュボードとESP32の関係

PCダッシュボードが高レベル制御を担当し、ESP32は低レベルI/Oを担当します。

- PC: UI、ログ、センサ統合、自己位置表示、走行指令生成
- ESP32: モータドライバ出力、エンコーダ読み取り、将来のアクチュエータI/O、フェイルセーフ停止

PCからESP32へ送る主な走行指令:

```text
DRIVE VEL 100 100
DRIVE VEL 0 0
DRIVE VEL -80 80
DRIVE VEL 80 -80
EMERGENCY_STOP
```

## ESP32書き込み

Arduino CLIを使う場合:

```cmd
tools\setup_arduino_cli.bat
tools\check_arduino_cli.bat
tools\upload_esp32_drive.bat COM10
```

COM番号は `tools\list_ports.bat` で確認します。

Arduino IDEを使う場合:

```text
esp32\drive_controller\drive_controller.ino
```

をArduino IDEで開き、ボードとCOMポートを選んで書き込んでください。

Arduino CLIは任意です。インストールされていなくてもPCダッシュボードは動作します。

## tools説明

- `tools\setup_windows.bat`: 初回セットアップ。`.venv` を作成し、必要ライブラリを入れます。
- `tools\run_dashboard.bat`: ダッシュボード起動。
- `tools\check_environment.bat`: Python、ライブラリ、必要ファイルを確認。
- `tools\clean_cache.bat`: `__pycache__` や `*.pyc` を削除。
- `tools\list_ports.bat`: ESP32のCOMポート確認。
- `tools\setup_arduino_cli.bat`: Arduino CLI / ESP32 coreのセットアップ。
- `tools\check_arduino_cli.bat`: Arduino CLI環境確認。
- `tools\upload_esp32_drive.bat`: ESP32走行コントローラの書き込み。
- `tools\serial_monitor_esp32.bat`: ESP32シリアルモニタ。

## 仮想環境について

`.venv` は各PCで作成します。`.venv` をチームで共有すると、PCごとのパスやDLL差で壊れやすくなります。
そのため、他のPCでは必ず `tools\setup_windows.bat` を実行してください。

## 手動起動

batファイルを使わずに起動する場合:

```cmd
.venv\Scripts\python.exe pc\main_ui.py
```

検証:

```cmd
.venv\Scripts\python.exe -m compileall pc
```

## モード説明

- モックモード: 実機センサは未接続です。表示値はダミーデータです。
- シミュレーションモード: 仮想フィールド上の計算値を表示します。
- 実機モード: 接続されたセンサの実データを表示します。

設定は `pc\config.yaml` の `mode`、`serial`、`camera`、`display` セクションで変更します。

## トラブル対応

### pythonコマンドがWindows Storeを開く

Windowsのアプリ実行エイリアスが原因のことがあります。batファイルは `py -3` を優先して使います。
うまくいかない場合はPython公式版をインストールし、`tools\setup_windows.bat` を再実行してください。

### PySide6が見つからない

```cmd
tools\setup_windows.bat
```

### COMポートがわからない

ESP32をUSB接続した状態で次を実行してください。

```cmd
tools\list_ports.bat
```

### Arduino CLIが見つからない

Arduino CLIをインストールし、`arduino-cli.exe` にPATHを通してください。
詳細は `tools\arduino_cli_guide.md` を参照してください。

### カメラが映らない

Mockモードではカメラ未接続でも起動できます。実カメラを使う場合は `pc\config.yaml` の `camera.index` と `camera.mock` を確認してください。
## ESP32接続

ダッシュボードの `設定 / 診断` タブからCOMポートを更新し、ESP32を接続/切断できます。接続中はセンサ値パネルにESP32から受信したIMU / ジャイロ / エンコーダ値を表示できます。

詳しい手順は `docs\esp32_connection.md` を参照してください。

接続基盤の構成と、Simulation / Mock / Real の送信先ルールは `docs\connection.md` にまとめています。

初回の実機確認は `設定 / 診断` タブの `ESP32通信テスト` で、`COMポート更新`、`ESP32接続`、`接続テスト`、`受信確認` の順に実行します。
## IMU / ジャイロ

IMU / ジャイロは初期状態ではESP32ダミー出力です。実IMUを接続する場合の設定と配線メモは `docs\imu_gyro.md` を参照してください。

## ESP32未接続でのコンパイル確認

ESP32をUSB接続していなくても、Arduino CLIで `drive_controller` のコンパイル確認ができます。

```cmd
tools\compile_esp32_drive.bat
```

ESP32接続後に書き込む場合は次を使います。

```cmd
tools\upload_esp32_drive.bat COM10
```

Arduino CLIはPATH上の `arduino-cli` を優先し、見つからない場合は `C:\Program Files\Arduino CLI\arduino-cli.exe` も確認します。詳しくは `docs\arduino_compile.md` を参照してください。

## LiDAR接続準備

初回確認では `LIDAR_STATUS,DUMMY` と `LIDAR,1200,1200,1200,1200` が出ていれば正常です。これは実LiDARではなく、ESP32側のダミー出力です。

実LiDAR接続後は `LIDAR_STATUS,OK` が出ることを確認してください。未接続のまま `LIDAR_STATUS,DUMMY` でも異常ではありません。詳しくは `docs\lidar_connection.md` を参照してください。

## UIレイアウト

現在のダッシュボードは、実機テスト時に見たい情報を優先して表示します。

- `実機確認`: ESP32接続、IMU、LiDAR、エンコーダ、モータ出力、現在指令を大きなカードで確認します。
- `シミュレーション`: 仮想フィールド、シミュレーション操作、自動走行、走行操作をまとめています。
- `センサ詳細`: センサ値と接続状態を細かく確認します。
- `ログ`: ESP32受信ログ、操作ログ、診断ログを分けて表示します。
- `設定 / 診断`: COMポート選択、ESP32接続、接続テスト、受信確認、テスト送信、環境診断を行います。

`IMU_STATUS,DUMMY`、`LIDAR_STATUS,DUMMY`、`MOTOR_DUMMY,left,right` は実データではなく、ESP32側の接続確認用ダミー出力として表示されます。詳しくは `docs\ui_layout.md` を参照してください。

## デスクトップ起動

ダッシュボードはデスクトップショートカットから起動できます。

```cmd
tools\create_desktop_shortcut.bat
```

作成先は現在のユーザーのデスクトップです。ショートカット名は `ロボットPCダッシュボード` です。

起動できない場合は、原因を確認するために次を直接実行してください。

```cmd
tools\check_startup.bat
tools\run_dashboard.bat
```

`assets\app_icon.ico` を置くと、ショートカットとウィンドウのアイコンに使われます。詳しくは `docs\desktop_app.md` と `assets\README.md` を参照してください。

## 実機クイック確認

`実機確認` タブの `実機クイック確認を実行` を押すと、ESP32接続、生存信号、IMU/LiDAR/エンコーダ受信、`DRIVE VEL 50 50` 応答、`DRIVE STOP` 応答をまとめて確認できます。

現在は `MOTOR_OUTPUT_ENABLED 0` のため、テスト送信しても実モータ出力は行わず `MOTOR_DUMMY` を確認します。詳しくは `docs\hardware_quick_check.md` を参照してください。

コマンドライン確認:

```cmd
.venv\Scripts\python.exe examples\quick_hardware_check.py COM10
```

## 実機確認結果の保存

`実機確認` タブの実機クイック確認を実行すると、結果が `logs\hardware_checks\` にJSONとTXTで保存されます。

- JSON: プログラムで集計しやすい形式
- TXT: 人が読みやすい共有用の形式

最新結果は `実機確認` タブの `最新結果をコピー` でクリップボードへコピーできます。`結果フォルダを開く` で保存先を開けます。

最後に使ったCOMポートは `config\local_settings.json` に保存され、次回起動時に自動選択されます。詳しくは `docs\hardware_check_logs.md` を参照してください。

## 実ハードウェア接続準備

実IMU、実LiDAR、モータドライバ、エンコーダを接続する前の計画メモとして、次を追加しています。

- `config\hardware_profile.yaml`: ボード、IMU、LiDAR、モータドライバ、エンコーダ、アクチュエータの接続計画
- `docs\real_lidar_templates.md`: 実LiDAR接続テンプレート
- `docs\real_imu_templates.md`: 実IMU接続テンプレート
- `docs\motor_driver_safety.md`: モータドライバ安全確認
- `docs\encoder_connection.md`: エンコーダ接続メモ
- `docs\hardware_integration_roadmap.md`: 実機統合ロードマップ
- `docs\current_status_summary.md`: 現在の状態まとめ

`設定 / 診断` タブには `ハードウェア構成メモ` を表示します。これは配線計画メモであり、実出力を有効化するものではありません。
# UI機能分割

ダッシュボードは目的別タブに分かれています。

- ホーム: 全体状況
- 実機接続: ESP32接続と実機クイック確認
- センサ: IMU / LiDAR / エンコーダ / カメラ
- 駆動: 走行操作とモータ出力状態
- シミュレーション: 仮想フィールドと自動走行
- ログ: ESP32受信ログ、操作ログ、診断ログ、実機確認結果
- 設定: ハードウェア構成とローカル設定
- 診断: 環境診断とESP32通信テスト
- ドキュメント: 関連資料リンク

詳しくは `docs/ui_feature_split.md` を参照してください。

## アプリからのESP32コンパイル / 書き込み

`診断` タブの `ESP32書き込み` セクションから、Arduino CLI確認、ボード一覧更新、コンパイル確認、ESP32への書き込みができます。

書き込みは自動実行されません。`安全確認しました` にチェックし、確認ダイアログで承認した時だけ実行されます。

詳しくは `docs/arduino_upload_from_app.md` を参照してください。

## 初心者向けの作業順

作業に迷った時は `ホーム` タブの `次にやること` を見てください。

詳しい流れは `docs/usability_guide.md` を参照してください。

## ハードウェア構成の編集

`設定` タブの `ハードウェア構成エディタ` で、LiDAR、IMU、モータドライバ、エンコーダ、アクチュエータのメモを編集できます。

保存しても実モータ出力は有効になりません。詳しくは `docs/hardware_profile_editor.md` を参照してください。

`設定` タブの `配線表を作成` から、`logs\wiring_reports\` にTXT/JSON形式の配線表と接続チェックシートを保存できます。

## 全画面表示

`F11` で全画面表示と通常表示を切り替えできます。ヘッダーと緊急停止ボタンは全画面でも表示されます。

詳しくは `docs/fullscreen_ui.md` を参照してください。

## ESP32プログラム編集

`診断` タブの `ESP32プログラム編集` で、`esp32/drive_controller/drive_controller.ino` を直接編集、保存、コンパイル確認できます。保存前に `backups/firmware/` へバックアップを作成します。危険そうなコードは警告しますが、自由編集は止めません。詳しくは `docs/firmware_editor.md` を参照してください。

## シリアルモニタ

`シリアル` タブで、ESP32の生Serial出力を直接確認できます。I2Cスキャナ、9軸IMUアドレス確認、任意の `Serial.println()` デバッグに使います。通常の実機接続と同じCOMポートは同時に開けません。詳しくは `docs/serial_monitor.md` を参照してください。

9軸IMUを確認する場合は、`診断` タブの `ESP32書き込み` で `9軸IMUテストを書き込む` または `9軸IMUテストをコンパイルして書き込み` を使います。
書き込み後に `シリアルで確認` を押すと、`シリアル` タブにCOMポートと `115200 bps` が設定され、I2Cアドレスと `IMU_STATUS,OK` を確認しやすくなります。詳しくは `docs/real_9axis_imu_test.md` を参照してください。

LiDAR、エンコーダ、光学式オドメトリ、距離センサ、ライン/カラーセンサ、シリアル通信、全センサダミーのESP32テストスケッチも用意しています。
`診断` タブの `ESP32書き込み` にある `センサテスト近道` から選択できます。詳しくは `docs/sensor_test_sketches.md` を参照してください。

光学式オドメトリは `OPTICAL_STATUS,OK` と `OPTICAL,dx,dy` を受信したときだけ、テストフィールド上のR2位置へ反映できます。Mock、Simulation、未接続、ERROR、古い受信値ではR2を動かしません。詳しくは `docs/optical_odometry_field_integration.md` を参照してください。

## F3RC2026公式フィールドモデル

テストフィールドタブをF3RC2026公式フィールド図面ベースのmm座標モデルに更新しました。

- フィールド全体: 4500 × 2400 mm
- 木材: 38 × 89 mm
- 通常ライン幅: 19 mm
- 倉庫Bゾーン橙ライン幅: 38 mm
- 寸法公差: ±5%
- 座標系: 左上原点、X右方向、Y下方向、単位mm

定義ファイルは `config/field/f3rc2026_field.yaml` です。
詳しくは `docs/f3rc2026_field_model.md` を参照してください。

## テストフィールド表示

テストフィールドタブを通常のFC開発向けに整理しました。

- R1/R2を公式スタートゾーンに表示し、R2はR2スタートライン枠内に初期表示
- R2の現在位置、角度、スタートからの距離、累積移動距離を右側に表示
- センサ未接続、未受信、ERROR、DUMMY時の通常値は0表示
- LiDAR距離は `LIDAR_STATUS,OK` のときだけ表示
- オブジェクト編集モードで黒レンガ、白レンガ、じょうろなどをmm座標で追加、ドラッグ移動、複製、削除可能
- R2位置、軌跡、オブジェクト配置、全体を個別にリセット可能

ESP32への自動アップロードや実モータ出力の有効化は行いません。
## 書き込みタブ

メイン画面の `書き込み` タブで、ESP32スケッチの選択、コード編集、検証、確認付き書き込みができます。シリアル出力確認は別の `シリアル` タブで行います。

- 上部の `かんたん書き込み` で `1 ESP32を探す` → `9軸IMUテストを書き込む` / `通常制御を書き込む` を実行可能
- 既定ボード: `ESP32 Dev Module`
- 既定FQBN: `esp32:esp32:esp32`
- COM10が見つかった場合は優先選択
- Bluetooth COMやIntel管理用COMはESP32書き込み先として自動選択しません
- ESP32未検出時はCOM10を手入力候補として表示します。実際に書き込む前にESP32をUSB接続して `更新` を押してください
- 書き込みは必ず確認ダイアログ後に実行
- 自動アップロードなし
- 実モータ出力は有効化しない

詳細は `docs/arduino_ide_tab.md` を参照してください。
# メンバー共有

メンバーへ共有する場合は、GitHubなどのGitリポジトリにこの `robot_pc_system` フォルダを置いて共有します。
メンバー側はリポジトリをcloneして、CodexまたはVS Codeで開きます。

詳しい手順は `docs/member_share.md` を参照してください。
