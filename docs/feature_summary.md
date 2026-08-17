# 機能詳細まとめ

このファイルは、GitHubで共有したときにメンバーが「何が入っているか」を確認するための一覧です。

## 1. 開発用ダッシュボード

起動:

```cmd
tools\run_dashboard.bat
```

主な機能:

- ホーム表示
- 実機接続
- センサ状態表示
- ESP32書き込み
- シリアルモニタ
- テストフィールド
- 遠隔受信
- 3Dモデル表示
- ログ確認
- 設定確認
- 診断

実機なしでも落ちにくいように、未接続時は0表示または未接続表示を基本にしています。

## 2. 本番用 FC Run

起動:

```cmd
run_fc.bat
```

本番で迷わず使うためのシンプル画面です。

表示:

- ESP32
- Optical
- IMU
- Localization
- X [mm]
- Y [mm]
- theta [deg]
- フィールド上のR2
- R2の向き
- R2の軌跡

操作:

- 接続
- 切断
- ZERO
- 自己位置推定 START
- 自己位置推定 STOP
- 位置リセット
- 緊急停止

開発用のArduino書き込み、Rawログ、大量デバッグ表示はFC Runには出しません。

## 3. ESP32書き込み

開発用ダッシュボードの `書き込み` タブからESP32スケッチを選択して書き込めます。

主な対象:

- drive_controller
- imu_9axis_test
- optical_odometry_test
- imu_optical_fusion_test
- imu_optical_distance_heading_test
- NeoPixelテスト
- LiDARテスト

安全方針:

- 自動アップロードなし
- 書き込みは確認後のみ
- 実モータ出力は有効化しない

## 4. シリアルモニタ

開発用ダッシュボードの `シリアル` タブでESP32の生ログを確認できます。

用途:

- I2Cスキャン確認
- IMU認識確認
- 光学式オドメトリ確認
- ESP32起動ログ確認
- `STATUS,OK` 確認
- 任意コマンド送信

Arduino IDEのシリアルモニタと同じCOMポートは同時に使えません。

## 5. 9軸IMU確認

ESP32側でIMUを読み取り、PC側で状態を表示します。

確認する主な出力:

```text
IMU_STATUS,OK
IMU,yaw,pitch,roll
GYRO,gx,gy,gz
```

未接続または未受信の場合、UIでは未接続または0表示にします。

## 6. SparkFun Qwiic OTOS光学式オドメトリ

公式SparkFun Qwiic OTOSライブラリを使う構成です。

確認する主な出力:

```text
OTOS_STATUS,OK
OTOS_POSITION,x_mm,y_mm,heading_deg
OTOS_DELTA,dx_mm,dy_mm,dtheta_deg
```

FC Runでは、OTOSの公式X/Y/Headingを使う `OTOS_DIRECT` を基本にします。

## 7. IMU + 光学式オドメトリ自己位置推定

ESP32から受信したIMUと光学式オドメトリの値を使い、PC側でR2の自己位置を更新します。

基本経路:

```text
ESP32
↓
シリアル / 遠隔受信
↓
Sensor Parser
↓
Localization
↓
LocalizationState
↓
ホーム / センサ / テストフィールド / FC Run
```

## 8. テストフィールド

F3RC2026公式寸法をもとにしたmm座標フィールドです。

表示:

- フィールド寸法
- R1/R2
- R2向き
- R2軌跡
- ゾーン
- オブジェクト
- センサ状態

R2位置はmm単位で管理し、表示時だけpxへ変換します。

## 9. 遠隔受信

USBシリアル以外に、遠隔から送られた位置・センサデータを受信してフィールドへ反映する準備があります。

対象:

- UDPなどの遠隔データ
- フィールド上のR2位置
- 自己位置推定状態

詳細は `docs/remote_receiver.md` と `docs/imu_optical_wifi_remote.md` を参照してください。

