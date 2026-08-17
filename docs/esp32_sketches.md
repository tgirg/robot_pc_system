# ESP32スケッチ一覧

この資料は、`esp32/` 配下の主なスケッチと用途をまとめたものです。

## 安全方針

- 自動アップロードはしません。
- 書き込みはユーザー確認後に実行します。
- 実モータ出力は有効化しません。
- モータを動かすコードを触る場合は、必ず安全設定を確認します。

## drive_controller

場所:

```text
esp32/drive_controller/drive_controller.ino
```

用途:

- 通常のESP32側コントローラ
- PCからの走行指令確認
- 将来のモータ制御の土台

注意:

- `MOTOR_OUTPUT_ENABLED` は0のまま維持します。

## imu_9axis_test

場所:

```text
esp32/imu_9axis_test/imu_9axis_test.ino
```

用途:

- 9軸IMU確認
- I2Cアドレス確認
- 115200bpsシリアル確認

見る出力:

```text
BOOT,IMU_9AXIS_TEST_READY
I2C device found at 0x68
IMU_STATUS,OK
```

## optical_odometry_test

場所:

```text
esp32/optical_odometry_test/optical_odometry_test.ino
```

用途:

- 光学式オドメトリ単体確認
- `OPTICAL_STATUS,OK`
- `OPTICAL,dx,dy`

## imu_optical_fusion_test

場所:

```text
esp32/imu_optical_fusion_test/
```

用途:

- IMUと光学式オドメトリを組み合わせた確認
- PC側Localizationへの入力確認

## imu_optical_distance_heading_test

場所:

```text
esp32/imu_optical_distance_heading_test/imu_optical_distance_heading_test.ino
```

用途:

- SparkFun Qwiic OTOS公式ライブラリを使った位置・向き確認
- OTOSの公式X/Y/Heading出力
- FC Run向けの本番寄り確認

見る出力:

```text
OTOS_STATUS,OK
OTOS_POSITION,x_mm,y_mm,heading_deg
OTOS_DELTA,dx_mm,dy_mm,dtheta_deg
FUSION,...
```

コマンド:

```text
ZERO
STATUS
SCAN
CALIBRATE_OTOS
```

## imu_optical_fusion_wifi_udp

場所:

```text
esp32/imu_optical_fusion_wifi_udp/
```

用途:

- Wi-Fi / UDPで遠隔受信するための実験用
- USBケーブルなしでセンサ値を送る構成の準備

注意:

- Wi-Fi設定はPCや会場環境に依存します。
- 本番で使う前に必ず通信安定性を確認します。

## NeoPixelテスト

用途:

- ESP32のRGB LED動作確認
- `Adafruit_NeoPixel` ライブラリ確認
- GPIO15などのLEDピン確認

## コンパイル確認

例:

```cmd
arduino-cli compile --fqbn esp32:esp32:esp32 esp32\imu_optical_distance_heading_test
```

## 書き込み時の注意

- COMポートを確認します。
- Arduino IDEのシリアルモニタを閉じます。
- 書き込み後はシリアルモニタで起動ログを確認します。
- センサが認識されない場合は、3.3V / GND / SDA / SCLを確認します。

