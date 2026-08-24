# 実LiDAR接続テンプレート

## 接続前に確認すること
- 型番、データシート、電源電圧、通信方式を確認します。
- 3.3V入力か5V入力かを必ず確認します。
- GNDをESP32と共通にします。
- 未接続時は `USE_REAL_LIDAR 0` のままにします。

## 型番
`config/hardware_profile.yaml` の `lidar.type` に記録します。

## 電源電圧
`lidar.voltage` に記録します。ESP32の3.3V端子から直接供給できるかは部品ごとに確認してください。

## 通信方式
### UARTの場合
- `uart_rx_pin` と `uart_tx_pin` を記録します。
- ESP32側RX/TXとセンサ側TX/RXを交差して接続します。

### I2Cの場合
- `i2c_sda_pin` と `i2c_scl_pin` を記録します。
- プルアップ抵抗の有無を確認します。

### USBの場合
- PCへ直接USB接続する方式と、ESP32へ接続する方式を分けて考えます。

## 出力フォーマット
ESP32からPCへ送る形式は次を維持します。

```text
LIDAR_STATUS,OK
LIDAR,front,left,right,rear
```

## 変更する場所
- `esp32/drive_controller/lidar_reader.cpp`
- `esp32/drive_controller/lidar_reader.h`
- `esp32/drive_controller/drive_controller.ino`
- `pc/sensors/serial_sensor_parser.py`

## USE_REAL_LIDARを1にする前の注意
実LiDARと電源、配線、出力形式を確認するまで `USE_REAL_LIDAR 0` のままにします。
