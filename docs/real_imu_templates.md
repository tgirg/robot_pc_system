# 実IMU接続テンプレート

## 想定センサ
- MPU6050
- BNO055
- ICM系IMU

## I2C配線
- SDA/SCLピンを `config/hardware_profile.yaml` に記録します。
- 3.3V対応か確認します。
- GNDをESP32と共通にします。

## 出力フォーマット
ESP32からPCへ送る形式は次を維持します。

```text
IMU_STATUS,OK
IMU,yaw,pitch,roll
GYRO,x,y,z
```

## 変更する場所
- `esp32/drive_controller/imu_reader.cpp`
- `esp32/drive_controller/imu_reader.h`
- `esp32/drive_controller/drive_controller.ino`

## USE_REAL_IMUを1にする前の注意
必要ライブラリをArduino環境へ入れ、I2Cアドレスと電源電圧を確認してから切り替えます。未接続時は `USE_REAL_IMU 0` のままにします。

## ダミーモードとの違い
ダミーモードは接続確認用の固定値です。実センサ値ではありません。
