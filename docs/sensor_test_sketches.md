# ESP32センサテストスケッチ

## 目的

センサごとに専用のESP32テストスケッチを書き込み、ダッシュボード内のシリアルモニタで出力を確認します。
実センサが未接続でも、まずはダミー出力でPC側UI、パーサ、COM通信を確認できます。

自動アップロードは行いません。書き込みはユーザーが `ESP32へ書き込み` を押した時だけ実行します。
実モータ出力は有効化しません。

## スケッチ一覧

| スケッチ | 目的 | 主な出力 |
|---|---|---|
| `drive_controller` | 通常の安全ダミー駆動確認 | `STATUS,OK`, `MOTOR_DUMMY` |
| `imu_9axis_test` | 9軸IMU / I2C確認 | `I2C device found at 0x68`, `IMU_STATUS,OK` |
| `lidar_uart_test` | UART LiDAR準備確認 | `LIDAR_STATUS,DUMMY`, `LIDAR,1200,1200,1200,1200` |
| `encoder_test` | 左右エンコーダ形式確認 | `ENC_STATUS,DUMMY`, `ENC,0,0` |
| `optical_odometry_test` | 光学式オドメトリ実機確認 | `OPTICAL_STATUS,OK`, `OPTICAL,dx,dy` |
| `optical_field_reflect_example` | 光学式反映の最小例 | `OPTICAL_STATUS,OK`, `OPTICAL,dx,dy` |
| `distance_sensor_test` | 距離センサ形式確認 | `DIST_STATUS,DUMMY`, `DIST,front,800` |
| `line_color_sensor_test` | ライン/カラーセンサ形式確認 | `LINE_STATUS,DUMMY`, `COLOR_STATUS,DUMMY` |
| `serial_echo_test` | COM送受信の最小確認 | `RX,<text>`, `ECHO,<text>` |
| `all_sensor_dummy_test` | PC側UI/パーサ総合確認 | 全センサのダミー行 |

## 書き込み手順

1. `診断` タブを開きます。
2. `ESP32書き込み` の `センサテスト近道` から目的のテストを押します。
3. `ボード一覧更新` を押してCOMポートを確認します。
4. `コンパイル確認` を押します。
5. 必要な時だけ `安全確認しました` にチェックします。
6. `ESP32へ書き込み` を押し、確認ダイアログで承認します。
7. 書き込み後、`シリアルモニタ` を `115200 bps` で接続します。

## シリアルモニタで見る値

シリアルモニタにはRawログのほか、次の要約が表示されます。

- ファームウェア名とバージョン
- I2C認識
- IMU状態
- LiDAR状態
- エンコーダ状態
- オドメトリ状態
- 距離センサ状態
- ライン状態
- カラー状態

`DUMMY` は実センサ値ではなく、ESP32側のテスト出力です。
実センサを接続した場合は、スケッチを編集して `OK` や実値出力へ差し替えます。

## 光学式オドメトリ確認

`optical_odometry_test` はI2Cアドレス `0x17`、SDA `GPIO21`、SCL `GPIO22` でSparkFun Qwiic Optical Tracking Odometry Sensor / PAA5160E1を確認します。

シリアルモニタで次を確認します。

```text
BOOT,OPTICAL_ODOMETRY_TEST_READY
I2C device found at 0x17
OPTICAL_PRODUCT,0x5F
OPTICAL_STATUS,OK
OPTICAL,dx,dy
```

使えるコマンドは `SCAN`、`STATUS`、`ZERO`、`DEBUG ON`、`DEBUG OFF` です。`DEBUG ON` では `OPTICAL_RAW,...` が表示されます。

## 光学式反映の最小例

`optical_field_reflect_example` は実センサを読まず、FCアプリへ光学式形式の値だけを送る例です。
テストフィールドの `光学式位置反映` がONの状態で、シリアルタブから次のコマンドを送るとR2の動き方を確認できます。

```text
FORWARD
RIGHT
LEFT
SQUARE
STOP
ZERO
STATUS
```

実センサの確認には `optical_odometry_test`、反映経路だけの確認には `optical_field_reflect_example` を使います。

## 実センサ接続時の注意

- 電圧を確認する
- GNDを共通にする
- SDA/SCL、UART TX/RX、エンコーダA/B相を取り違えない
- Arduino IDEや別のシリアルモニタを閉じる
- モータ出力ピンを使わない

`MOTOR_OUTPUT_ENABLED`、`USE_REAL_IMU`、`USE_REAL_LIDAR` は既存の安全設定を維持してください。
## DUMMY表示の扱い

`all_sensor_dummy_test` はUI受信確認用として残します。

ただし実センサ値と誤解しないよう、アプリ側では次の扱いにしています。

- `*_STATUS,DUMMY` はDUMMY状態として表示
- 通常のセンサ値欄は0表示
- LiDARの `1200 mm` などのダミー距離は実値欄に表示しない
- `LIDAR_STATUS,OK` のときだけLiDAR距離を表示
- `ERROR`、未受信、未接続は0表示
