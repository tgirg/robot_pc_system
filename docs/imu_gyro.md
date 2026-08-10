# IMU / ジャイロ

## 目的
IMU / ジャイロは、ロボットの向き、傾き、角速度をPCダッシュボードへ送るためのセンサです。現在は実IMUが未接続でも動作確認できるよう、ESP32側でダミー値を出力する構成にしています。

## 現在のダミー出力
既定では `USE_REAL_IMU 0` です。この状態では追加Arduinoライブラリは不要で、ESP32は次の形式を出力します。

```text
IMU_STATUS,DUMMY
IMU,0.0,0.0,0.0
GYRO,0.0,0.0,0.0
```

PCダッシュボードでは `IMU状態: ESP32ダミー出力` と表示されます。これは実IMUデータではありません。

## シリアル形式

```text
IMU_STATUS,DUMMY
IMU_STATUS,OK
IMU_STATUS,ERROR
IMU,yaw,pitch,roll
GYRO,x,y,z
```

`IMU_STATUS` の意味:

- `DUMMY`: 実IMUを使わず、ESP32がダミー値を出力しています。
- `OK`: 実IMUの初期化に成功し、実センサ値を出力しています。
- `ERROR`: 実IMUの初期化に失敗しました。システムは停止せず、0値を出力します。

## MPU6050を使う場合
MPU6050をESP32へI2C接続する想定です。

- VCC: 3.3V
- GND: GND
- SDA: ESP32のI2C SDA
- SCL: ESP32のI2C SCL

注意:

- MPU6050モジュールは3.3Vで使う構成を基本にしてください。
- ESP32のSDA/SCL既定ピンはボードにより異なります。
- 必要なら `imu_reader.cpp` の `Wire.begin()` を `Wire.begin(SDA_PIN, SCL_PIN)` に変更してください。

## 実IMUを有効にする
`esp32/drive_controller/imu_reader.h` で次を変更します。

```cpp
#define USE_REAL_IMU 1
#define IMU_TYPE_MPU6050 1
```

MPU6050実IMUモードでは、Arduinoライブラリが必要です。

- Adafruit MPU6050
- Adafruit Unified Sensor
- Wire

ダミーモードではAdafruitライブラリは不要です。実IMUを有効にしてコンパイルエラーが出る場合は、必要ライブラリをインストールするか、`USE_REAL_IMU` を `0` に戻してください。

## 安全設計
IMUが未接続でもESP32スケッチは止まりません。`IMU_STATUS,ERROR` を出しながら、`STATUS,OK` と走行コマンド処理は継続します。
