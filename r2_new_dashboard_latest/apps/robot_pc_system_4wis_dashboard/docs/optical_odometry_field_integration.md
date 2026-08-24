# 光学式オドメトリのフィールド反映

光学式オドメトリの `OPTICAL,dx,dy` をR2のフィールド位置へ反映します。座標はmmで管理し、表示時だけpxへ変換します。

## 受信形式

```text
OPTICAL_STATUS,OK
OPTICAL,12,-5
```

`optical_odometry_test` では、SparkFun Qwiic Optical Tracking Odometry Sensor / PAA5160E1の位置レジスタを読み、前回値との差分countとして `OPTICAL,dx,dy` を出力します。

絶対座標を送る場合は次の形式も使えます。

```text
ODOM_STATUS,OK
ODOM,1250.0,1870.0,90.0
```

## 反映条件

R2へ反映するのは次の条件を満たす場合だけです。

- 実データ受信である
- `OPTICAL_STATUS,OK` または `ODOM_STATUS,OK`
- 受信が古くない
- `dx/dy` が異常値ではない
- テストフィールドの `光学式位置反映` がON

`DUMMY`、`ERROR`、未接続、Mock、Simulation、ログ再生、更新ボタンの再読込ではR2位置へ足し込みません。

## 設定

設定ファイルは `config/optical_odometry.yaml` です。

```yaml
scale_x_mm_per_count: 0.30517578125
scale_y_mm_per_count: 0.30517578125
invert_x: false
invert_y: false
swap_xy: false
coordinate_mode: robot_relative
```

既定値は `0.30517578125 mm/count` です。これは公式ライブラリの位置換算 `10000 mm / 32768 count` に合わせています。

`coordinate_mode: robot_relative` の場合、R2の角度 `theta` を使ってロボット座標の差分をフィールド座標へ変換します。

## ESP32読み取り仕様

`esp32/optical_odometry_test/optical_odometry_test.ino` は次の仕様で読み取ります。

- I2Cアドレス: `0x17`
- Product IDレジスタ: `0x00`
- 期待Product ID: `0x5F`
- 位置レジスタ開始: `0x20`
- データ長: 6バイト
- 並び: X low/high, Y low/high, Heading low/high
- 型: リトルエンディアン符号付き16bit
- 出力: 前回位置との差分count

起動時は `BOOT,OPTICAL_ODOMETRY_TEST_READY`、`FW,optical_odometry_test,0.3.0`、I2Cスキャン結果を出力します。

## シリアルコマンド

```text
SCAN
STATUS
ZERO
DEBUG ON
DEBUG OFF
```

`DEBUG ON` のときだけ `OPTICAL_RAW,...` を出力します。通常時はログが増えすぎないように詳細ログを止めています。

## ゼロ点設定

テストフィールドの `光学式ゼロ点設定` を押すと、光学式オドメトリの累積値を0にします。R2のフィールド位置は変えません。

## スケール調整

1. テストフィールドで `光学式ゼロ点設定` を押します。
2. センサまたはR2を実際に500mm動かします。
3. テストフィールドに表示される累積countを確認します。
4. 実測距離に `500 mm` を入力します。
5. `X scale保存` または `Y scale保存` を押します。
6. `config/optical_odometry.yaml` に保存されたscaleを確認します。

## 注意

光学式オドメトリは床材、速度、センサ高さで値が変わります。最終的な自己位置推定ではIMU、エンコーダ、LiDAR、手動位置補正と組み合わせて使います。
