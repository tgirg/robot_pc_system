# センサデータの流れ

この資料は、ESP32からPCアプリのフィールド表示まで、センサ値がどのように流れるかを説明します。

## 全体像

```text
ESP32
  ↓
USBシリアル または 遠隔受信
  ↓
pc/sensors/serial_sensor_parser.py
  ↓
pc/sensors/imu_state.py
pc/sensors/optical_odometry_state.py
  ↓
pc/localization/
  ↓
LocalizationState
  ↓
ホーム / センサ / テストフィールド / FC Run
```

## ESP32が出す主な行

生存確認:

```text
STATUS,OK
```

IMU:

```text
IMU_STATUS,OK
IMU,yaw,pitch,roll
GYRO,gx,gy,gz
```

光学式オドメトリ:

```text
OPTICAL_STATUS,OK
OPTICAL,dx,dy
```

SparkFun Qwiic OTOS:

```text
OTOS_STATUS,OK
OTOS_POSITION,x_mm,y_mm,heading_deg
OTOS_DELTA,dx_mm,dy_mm,dtheta_deg
```

融合データ:

```text
FUSION,sequence,timestamp_ms,x_mm,y_mm,theta_deg,quality,mode
```

## Parserの役割

`pc/sensors/serial_sensor_parser.py` は、ESP32から来た1行の文字列をPC側のデータ構造へ変換します。

ここで行うこと:

- `STATUS,OK` の判定
- `IMU_STATUS` の判定
- `OPTICAL_STATUS` の判定
- `OTOS_POSITION` の読み取り
- 不正値、NaN、inf、未接続値の0化
- 古い値や未受信状態の扱い

## Localizationの役割

`pc/localization/` は、センサ値からR2のX/Y/thetaを決めます。

主なモード:

- `OTOS_DIRECT`: SparkFun Qwiic OTOSの公式X/Y/Headingをそのまま使う
- `IMU_OPTICAL_FUSION`: IMUの向きと光学式オドメトリの移動量を組み合わせる

本番では、まず `OTOS_DIRECT` を優先します。

## UIの役割

UIは、シリアル解析や自己位置計算を直接行わない方針です。

UIが見るもの:

- LocalizationState
- センサ状態
- 接続状態
- 安全状態

表示先:

- ホーム
- センサ
- テストフィールド
- FC Run

## 未接続時のルール

センサ信号がない場合:

- 状態は未接続または未受信
- 数値は0
- LiDARはOK時のみ距離表示
- 古い値でR2を動かさない
- DUMMY値を実値のように表示しない

## よく見る確認ポイント

ESP32が生きているか:

```text
STATUS,OK
```

IMUが見えているか:

```text
IMU_STATUS,OK
```

光学式オドメトリが見えているか:

```text
OTOS_STATUS,OK
OTOS_POSITION,...
```

フィールドに反映されるか:

- テストフィールドを開く
- ZERO
- START
- R2の矢印と軌跡が動くか確認

