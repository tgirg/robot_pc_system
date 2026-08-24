# 現在の状態まとめ

## 現在できていること
- Windowsデスクトップショートカット起動
- PySide6ダッシュボード
- Mock / Simulation / Real の区別
- ESP32通信テスト
- 実機クイック確認
- 実機確認結果のJSON/TXT保存
- Arduino CLIコンパイル/アップロード補助
- IMU/LiDAR/Motorのダミー出力対応

## まだダミーのもの
- 実IMU読み取り
- 実LiDAR読み取り
- 実モータPWM出力
- 実エンコーダ割り込み読み取り
- アクチュエータ制御

## 実機で確認済みにするもの
- `STATUS,OK`
- `IMU_STATUS,DUMMY`
- `LIDAR_STATUS,DUMMY`
- `MOTOR_DUMMY`
- `ENC,left,right`
- `DRIVE STOP`

## 次に必要な部品情報
- IMU型番
- LiDAR型番
- モータドライバ型番
- エンコーダ仕様
- 電源電圧
- ESP32の使用ピン

## 次に見るファイル
- `config/hardware_profile.yaml`
- `docs/hardware_integration_roadmap.md`
- `docs/motor_driver_safety.md`
- `docs/real_imu_templates.md`
- `docs/real_lidar_templates.md`
- `docs/encoder_connection.md`

## ミニPCへ移すとき
`C:\robot_pc_system` に置き、`tools\setup_windows.bat`、`tools\create_desktop_shortcut.bat`、`tools\check_startup.bat` を順に実行します。

## チームへの説明
このプロジェクトは、PCが判断とUIを担当し、ESP32は低レベルI/Oを担当します。現時点では安全のため、実モータ出力は無効です。
# ハードウェア構成

- `config/hardware_profile.yaml` は `設定` タブのエディタから編集可能
- 保存しても `MOTOR_OUTPUT_ENABLED 0` / `USE_REAL_IMU 0` / `USE_REAL_LIDAR 0` は維持
- 実機クイック確認ログには最新の構成サマリーが含まれる
