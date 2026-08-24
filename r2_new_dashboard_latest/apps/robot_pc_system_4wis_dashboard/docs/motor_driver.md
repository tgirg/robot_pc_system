# モータドライバ

## 目的
ESP32の走行制御スケッチに、将来の実モータ出力用の抽象化を追加しています。現時点では安全のため、実ピンへのPWM出力は無効です。

## 既定設定
`esp32/drive_controller/motor_driver.h` では次の設定になっています。

```cpp
#define MOTOR_OUTPUT_ENABLED 0
```

この状態では、`DRIVE VEL` などの走行指令を受けても実ピンへPWMは出ません。代わりにシリアルへ次を出力します。

```text
MOTOR_DUMMY,left,right
```

例:

```text
MOTOR_DUMMY,50,50
DRIVE,50,50
```

`DRIVE,left,right` はこれまで通りPC側の応答確認用に出力します。

## 実モータ出力を有効にする前に
実モータへ出力する前に、必ず次を確認してください。

- モータドライバの型番
- PWMピン
- 方向ピン
- Enable / Sleep / Fault ピン
- 電源電圧
- GND共通
- 非常停止方法
- タイヤが浮いた状態での低速テスト

## 実装場所
実ピン設定は `esp32/drive_controller/motor_driver.cpp` のTODO部分に追加します。

用意済みの関数:

- `initMotorDriver()`
- `setMotorSpeed(left, right)`
- `stopMotors()`
- `emergencyStopMotors()`

## 注意
`MOTOR_OUTPUT_ENABLED` を `1` にするだけでは、まだ実モータ出力は完成しません。ピン設定、PWM設定、方向制御、非常停止処理を実機に合わせて実装してから有効化してください。
