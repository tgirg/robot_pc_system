# モータドライバ安全メモ

## 最重要
実モータをつなぐ前に `MOTOR_OUTPUT_ENABLED 0` を維持してください。これはPWMを実ピンへ出さない安全設定です。

## MOTOR_OUTPUT_ENABLED 1にする前に確認すること
- 車輪を浮かせる
- 緊急停止ボタンが使える
- `DRIVE STOP` が効く
- 電源電圧とGNDを確認する
- PWM/DIR/STBYピンを確認する
- 配線写真を保存する

## 電源とGND
モータ電源とロジック電源を混同しないでください。GNDは共通化が必要です。

## 想定ドライバ
- TB6612FNG
- BTS7960
- L298N

## 変更する場所
- `esp32/drive_controller/motor_driver.cpp`
- `esp32/drive_controller/motor_driver.h`
- `esp32/drive_controller/drive_controller.ino`

## 初回試験
短時間・低速で行います。車輪を浮かせ、いつでも緊急停止できる状態で確認してください。
