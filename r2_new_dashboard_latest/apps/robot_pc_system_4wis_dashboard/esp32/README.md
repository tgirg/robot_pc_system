# ESP32

このフォルダにはESP32向けArduinoスケッチを置きます。現在の主なスケッチは `drive_controller/drive_controller.ino` です。

## ダミーIMUモード
既定では `esp32/drive_controller/imu_reader.h` の設定が次のようになっています。

```cpp
#define USE_REAL_IMU 0
#define IMU_TYPE_MPU6050 1
```

`USE_REAL_IMU 0` の場合、実IMUやAdafruitライブラリがなくてもコンパイルできます。ESP32は次のダミー値を出力します。

```text
IMU_STATUS,DUMMY
IMU,0.0,0.0,0.0
GYRO,0.0,0.0,0.0
ENC,0,0
```

初回接続確認では、このダミー値が出ていれば正常です。

## モータ出力
既定では実モータ出力も無効です。

```cpp
#define MOTOR_OUTPUT_ENABLED 0
```

この状態ではPWMピンへ出力せず、代わりに次のシリアル行を出します。

```text
MOTOR_DUMMY,left,right
```

`DRIVE,left,right` は従来通り出力されます。実モータ出力を有効にする前に、`docs\motor_driver.md` を確認してください。

## 実IMUモード
MPU6050などの実IMUを使う場合は、`USE_REAL_IMU` を `1` に変更します。

```cpp
#define USE_REAL_IMU 1
```

実IMUモードでは追加ライブラリが必要になる場合があります。

- Adafruit MPU6050
- Adafruit Unified Sensor
- Wire

コンパイルに失敗する場合は、必要ライブラリをArduino IDEまたはArduino CLIでインストールするか、`USE_REAL_IMU` を `0` に戻してください。

## 書き込み

```cmd
tools\setup_arduino_cli.bat
tools\check_arduino_cli.bat
tools\upload_esp32_drive.bat COM10
```

COM番号は実際のESP32に合わせて変更してください。

## 初回接続確認

```cmd
.venv\Scripts\python.exe examples\esp32_first_connection_test.py COM10
```

Arduino IDEのシリアルモニタを開いていると、PCダッシュボードやテストスクリプトがCOMポートを開けません。接続テスト前に閉じてください。

## LSB基板/ユニバーサル基板確認

`lsb_sensor_node` は、2026F3F LSB RevA ver0 用のシリアルセンサノード確認スケッチです。
LSB実基板がない段階でも、ユニバーサル基板でPCアプリの受信、表示、ログ経路を確認できます。

主な出力は次の形式です。

```text
LSB,ID,2026F3F_LSB_REVA_VER0,0.1.0
LSB,I2C,0x20:OK,0x29:OK
LSB,SENS,0,tof=0/0/0/0,us=800/820/900/920/1500/1480/1200/1180,imu=0.0/0.0/0.0
```

アプリ側は `LSB,SENS` を受信すると、LSB欄、ToF 4方向、超音波8ch、IMU欄へ反映します。
この確認はファームウェア/通信プロトコルの確認であり、LSB実基板の配線や製造状態の確認ではありません。

## LiDARダミーモード

既定では実LiDARは無効です。

```cpp
#define USE_REAL_LIDAR 0
```

この状態では外部LiDARライブラリや実LiDARは不要で、ESP32は次を出力します。

```text
LIDAR_STATUS,DUMMY
LIDAR,1200,1200,1200,1200
```

実LiDARを接続する場合は、型番、電圧、UART/I2C、端子名を確認してから `lidar_reader.cpp` を実装してください。詳細は `docs\lidar_connection.md` を参照してください。
