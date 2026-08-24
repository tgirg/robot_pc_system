# 実機クイック確認

## 目的

実機クイック確認は、ESP32との接続、受信データ、走行指令への応答をワンクリックで確認するためのベンチテスト機能です。

この確認では `DRIVE VEL 50 50` をESP32へ送信しますが、現在のESP32ファームウェアでは `MOTOR_OUTPUT_ENABLED 0` が既定です。そのため実モータ出力は行わず、`MOTOR_DUMMY,50,50` のような安全ダミー応答を確認します。

最後には必ず `DRIVE STOP` を送信します。

## 実行前の注意

- モータ出力は無効のままにしてください。
- Arduino IDEのシリアルモニタを閉じてください。
- COM10など対象COMポートを他のアプリで使わないでください。
- ESP32へ `drive_controller.ino` が書き込まれていることを確認してください。
- 実機配線中でも、最初は車輪を浮かせるなど安全な状態で確認してください。

## UIでの実行方法

1. ダッシュボードを起動します。
2. `実機確認` タブを開きます。
3. `実機クイック確認` セクションの `実機クイック確認を実行` を押します。
4. チェックリストが `OK` になることを確認します。

表示されるチェック項目:

- ESP32接続
- STATUS受信
- IMU受信
- LiDAR受信
- エンコーダ受信
- モータダミー受信
- テスト送信
- STOP送信

## 成功時に出るログ

操作ログには次のような内容が出ます。

```text
実機クイック確認を開始しました
COMポートを更新しました
ESP32へ接続しました
テスト送信しました: DRIVE VEL 50 50
STOP送信しました
実機クイック確認に成功しました
```

ESP32受信ログには次のような行が出ます。

```text
STATUS,OK
IMU_STATUS,DUMMY
IMU,0.0,0.0,0.0
GYRO,0.0,0.0,0.0
ENC,0,0
LIDAR_STATUS,DUMMY
LIDAR,1200,1200,1200,1200
RX,DRIVE VEL 50 50
DRIVE,50,50
MOTOR_DUMMY,50,50
RX,DRIVE STOP
DRIVE,0,0
MOTOR_DUMMY,0,0
```

## ダミー表示の意味

`IMU_STATUS,DUMMY` は、実IMUではなくESP32側の接続確認用ダミー出力です。

`LIDAR_STATUS,DUMMY` は、実LiDARではなくESP32側の接続確認用ダミー出力です。

`MOTOR_DUMMY,left,right` は、モータ出力が無効であることを示す安全ダミー応答です。実モータが回ったという意味ではありません。

## 失敗時の確認ポイント

- `ESP32接続` が失敗する場合: COMポート、USBケーブル、Arduino IDEのシリアルモニタを確認します。
- `STATUS受信` が失敗する場合: ESP32へ `drive_controller.ino` が書き込まれているか確認します。
- `IMU受信` や `LiDAR受信` が失敗する場合: ファームウェアが該当行を出しているか、ESP32受信ログを確認します。
- `テスト送信` が失敗する場合: ESP32接続が切れていないか確認します。
- `STOP送信` が失敗する場合: 接続状態を確認し、必要ならESP32をリセットしてください。

## コマンドラインでの確認

UIを使わずに確認する場合:

```cmd
.venv\Scripts\python.exe examples\quick_hardware_check.py COM10
```

COM番号が違う場合は `COM10` を実際のポートに置き換えてください。

## 実IMU / 実LiDAR接続後

実IMUを接続した後は `IMU_STATUS,OK` が出ることを確認してください。

実LiDARを接続した後は `LIDAR_STATUS,OK` が出ることを確認してください。

`DUMMY` のままでも通信テストとしては使えますが、実センサ値ではありません。

## 結果保存

実機クイック確認の完了時に、結果は `logs\hardware_checks\` に保存されます。

保存形式:

- JSON: 機械処理用
- TXT: 人が読む共有用

`実機確認` タブの `最新結果をコピー` でTXT内容をコピーできます。`結果フォルダを開く` で保存先を確認できます。

コマンドライン版で保存する場合:

```cmd
.venv\Scripts\python.exe examples\quick_hardware_check.py COM10 --save
```

詳しくは `docs\hardware_check_logs.md` を参照してください。
