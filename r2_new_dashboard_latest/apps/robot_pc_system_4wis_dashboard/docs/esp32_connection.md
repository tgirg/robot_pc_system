# ESP32接続

## 接続基盤
ESP32接続は `pc/connection` の共通接続ライブラリを使います。走行用ESP32だけでなく、将来のアーム、ツール、センサ用ESP32にも拡張しやすい構成です。詳しくは `docs\connection.md` を参照してください。

## 最初の接続確認手順
モータドライバや実IMUを接続する前に、まずESP32単体でシリアル通信だけを確認します。

1. `esp32\drive_controller\drive_controller.ino` をESP32へ書き込みます。
2. Arduino IDEのシリアルモニタを閉じます。
3. ESP32をUSB接続し、COMポートを確認します。
4. 次を実行します。

```cmd
.venv\Scripts\python.exe examples\esp32_first_connection_test.py COM10
```

書き込み直後またはリセット直後、ESP32は次を出力します。

```text
BOOT,DRIVE_CONTROLLER_READY
```

その後、500 msごとに次を出力します。

```text
STATUS,OK
IMU,0.0,0.0,0.0
GYRO,0.0,0.0,0.0
ENC,0,0
```

この段階ではIMU/GYRO/ENCはダミー値です。実センサを接続しなくてもPC側の受信確認ができます。

## UIから接続する方法
ダッシュボードを起動し、`設定 / 診断` タブを開きます。

1. `ESP32通信テスト` セクションで `COMポート更新` を押します。
2. `COMポート` からESP32のポートを選びます。
   例: `COM10 - Silicon Labs CP210x USB to UART Bridge`
3. ESP32候補が見つかった場合は自動選択されます。必要なら `ESP32候補を自動選択` も使えます。
4. `ESP32接続` を押します。
5. 接続できると、接続状態が `接続中 / データ種別: 実通信` になります。
6. `接続テスト` を押すと `STATUS,OK` の受信を確認します。

## UIだけで接続確認する手順
Arduino IDEのシリアルモニタを閉じてから、次の順で確認します。

1. `COMポート更新`
2. `ESP32候補を自動選択`
3. `ESP32接続`
4. `接続テスト`
5. `受信確認`
6. 必要な場合だけ `テスト送信`
7. 最後に `停止送信` または `ESP32切断`

`受信確認` は約2秒間、ESP32から届いた行を `ESP32受信ログ` に表示します。この欄は選択してコピーできます。

`テスト送信` は次を接続中のESP32へ送信します。

```text
DRIVE VEL 50 50
DRIVE STOP
```

`テスト送信` は明示的なハードウェア確認用です。Simulationモード中でも、このボタンだけは接続中のESP32へ送信します。通常の走行操作ボタンはSimulationモードでは実機へ送られません。

切断するときは `ESP32切断` を押します。接続中の場合は `DRIVE STOP` を送ってからシリアル接続を閉じます。

## 設定に保存
接続に成功したCOMポートを次回も使いたい場合は、`設定に保存` を押します。保存先は主に次の項目です。

```yaml
communication:
  usb:
    port: "COM10"

controllers:
  drive:
    port: "COM10"

serial:
  port: "COM10"
```

## 接続できないときの確認
- Arduino IDEやシリアルモニタが同じCOMポートを開いていないか確認します。
- `tools\list_ports.bat` またはUIの `更新` でCOMポート番号を確認します。
- USBケーブルがデータ通信対応か確認します。
- ESP32の電源、ドライバ、ボード種別を確認します。
- 書き込み直後は一度USBを抜き差しすると安定する場合があります。
- `drive_controller.ino` が書き込まれているか確認します。
- COM10が表示されるのに接続テストが失敗する場合、Arduino IDEのシリアルモニタや別のターミナルがCOM10を開いたままになっていないか確認します。
- `STATUS,OK` が出ない場合、ボーレートが115200になっているか、ESP32がリセットを繰り返していないか確認します。

## IMU/GYRO受信形式
PC側は次のシリアル行を解析します。

```text
BOOT,DRIVE_CONTROLLER_READY
STATUS,OK
IMU,45.2,1.0,-0.5
GYRO,0.01,-0.03,0.20
ENC,698,703
DRIVE,100,100
RX,DRIVE VEL 100 100
EMERGENCY,STOP
```

現在のESP32スケッチは、実IMUがなくてもPC側表示を確認できるよう、ダミーのIMU/GYRO/ENC値を定期送信します。将来、実ジャイロや実エンコーダの読み取りに置き換えます。

## UI表示
センサ値パネルには次のように表示されます。

```text
IMU角度: 実データ yaw 45.2 / pitch 1.0 / roll -0.5 deg
ジャイロ: 実データ x 0.01 / y -0.03 / z 0.20
```

データがない場合は `データなし` と表示します。

## 送信先の安全ルール
- Simulationモード: 走行指令はシミュレータへ送ります。ESP32が接続されていても実モータへは送信しません。
- Mockモード: Mock通信として扱います。
- Realモード: 接続済みESP32へ送信します。
- 例外: `ESP32通信テスト` の `テスト送信` と `停止送信` は、ユーザーが明示的に押した場合だけ接続中ESP32へ送信します。
## IMU / ジャイロについて
初回接続では `IMU_STATUS,DUMMY` と `IMU,0.0,0.0,0.0`、`GYRO,0.0,0.0,0.0` が出ていれば正常です。これは実IMUではなく、ESP32側のダミー出力です。

実IMU接続後は `IMU_STATUS,OK` が出ることを確認してください。`IMU_STATUS,ERROR` の場合でもESP32は停止せず、通信と走行コマンド処理は継続します。詳しくは `docs\imu_gyro.md` を参照してください。

## LiDAR接続準備

初回確認では `LIDAR_STATUS,DUMMY` と `LIDAR,1200,1200,1200,1200` が出ていれば正常です。これは実LiDARではなく、ESP32側のダミー出力です。

実LiDAR接続後は `LIDAR_STATUS,OK` が出ることを確認してください。未接続のまま `LIDAR_STATUS,DUMMY` でも異常ではありません。詳しくは `docs\lidar_connection.md` を参照してください。

## 実機クイック確認

ダッシュボードの `実機確認` タブにある `実機クイック確認を実行` で、ESP32との通信確認をワンクリックで実行できます。

この確認では次を行います。

1. COMポート更新とESP32候補選択
2. ESP32接続
3. `STATUS,OK`、`IMU_STATUS`、`LIDAR_STATUS`、`ENC` などの受信確認
4. `DRIVE VEL 50 50` の送信
5. `RX`、`DRIVE`、`MOTOR_DUMMY` 応答の確認
6. `DRIVE STOP` の送信

`MOTOR_OUTPUT_ENABLED 0` のため、実モータ出力は行われません。`MOTOR_DUMMY` は安全ダミー応答です。

コマンドラインで確認する場合:

```cmd
.venv\Scripts\python.exe examples\quick_hardware_check.py COM10
```

詳しくは `docs\hardware_quick_check.md` を参照してください。
