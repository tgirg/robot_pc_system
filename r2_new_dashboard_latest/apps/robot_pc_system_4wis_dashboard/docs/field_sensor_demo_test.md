# フィールド反映デモスケッチ

## 目的

`field_sensor_demo_test` は、ESP32からセンサ形式の出力を流して、PCダッシュボードのテストフィールドにR2の移動が反映されるか確認するためのスケッチです。

実モータ出力は使いません。

## 出力する主な行

```text
STATUS,OK
IMU_STATUS,OK
IMU,theta,0.00,0.00
ODOM_STATUS,OK
ODOM,x_mm,y_mm,theta_deg
OPTICAL,dx_mm,dy_mm
ENC_STATUS,OK
ENC,left,right
LIDAR_STATUS,OK
LIDAR,front,left,right,rear
```

## 使い方

1. `書き込み` タブを開きます。
2. スケッチ選択で `field_sensor_demo_test` を選びます。
3. `検証` でコンパイル確認します。
4. 必要なときだけ `書き込み` でESP32へ書き込みます。
5. `シリアル` タブへ移動します。
6. テストフィールドでR2が動くか確認します。

## リセット

シリアル送信欄から次を送ると、ESP32側のデモ座標を0に戻します。

```text
RESET_POSE
```

テストフィールド側の `R2位置リセット` を押すと、PC側のR2位置推定もR2スタート位置へ戻ります。

## ホイール操作対策

コンボボックス、数値入力、タブバーの上でマウスホイールを回しても、勝手に選択が切り替わらないようにしています。
