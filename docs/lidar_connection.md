# LiDAR接続準備

## 目的
LiDARは、ロボット周囲の距離を取得して障害物回避や自動走行に使うためのセンサです。現在は実LiDARが手元になくてもPC側の受信口とUI表示を確認できるよう、ESP32側でダミーLiDAR値を出力します。

## 現在のダミーモード
既定では `USE_REAL_LIDAR 0` です。この状態では実LiDARや外部ライブラリは不要です。

```text
LIDAR_STATUS,DUMMY
LIDAR,1200,1200,1200,1200
```

PCダッシュボードでは `LiDAR状態: ESP32ダミー出力` と表示します。これは実センサ値ではありません。

## シリアル形式

```text
LIDAR_STATUS,DUMMY
LIDAR_STATUS,OK
LIDAR_STATUS,ERROR
LIDAR,front,left,right,rear
```

`LIDAR,front,left,right,rear` の単位はmmです。

- `front`: 前方距離
- `left`: 左距離
- `right`: 右距離
- `rear`: 後方距離

`LIDAR_STATUS` の意味:

- `DUMMY`: 実LiDARを使わず、ESP32がダミー値を出力しています。
- `OK`: 実LiDARの初期化と読み取りができています。
- `ERROR`: 実LiDARの初期化または読み取りに失敗しています。

## UART LiDARを使う場合
UART LiDARでは、型番ごとの通信速度、電圧、TX/RXの接続先を確認してください。

- LiDAR TX -> ESP32 RX
- LiDAR RX -> ESP32 TX
- GNDはESP32と共通
- 電源電圧が3.3Vか5Vかを必ず確認

ESP32側では `lidar_reader.cpp` にHardwareSerialの初期化と読み取り処理を追加します。

## I2C LiDARを使う場合
I2C LiDARでは、SDA/SCL、I2Cアドレス、電源電圧を確認してください。

- SDA -> ESP32 SDA
- SCL -> ESP32 SCL
- GNDはESP32と共通
- ESP32のSDA/SCL既定ピンはボードにより異なります

必要なら `Wire.begin(SDA_PIN, SCL_PIN)` を使って明示してください。

## 実LiDARを有効にする
実LiDARを接続するときは、型番、端子名、電圧、通信方式を確認してから `drive_controller.ino` の設定を変更します。

```cpp
#define USE_REAL_LIDAR 1
#define LIDAR_TYPE_UART 1
#define LIDAR_TYPE_I2C 2
```

実装するセンサに合わせて `LIDAR_TYPE` や読み取り処理を追加してください。

## 安全設計
LiDARが未接続でもESP32スケッチは止まりません。`LIDAR_STATUS,DUMMY` または `LIDAR_STATUS,ERROR` を出しながら、`STATUS,OK` と走行コマンド処理は継続します。

初回確認では `LIDAR_STATUS,DUMMY` が出れば正常です。実LiDAR接続後は `LIDAR_STATUS,OK` を確認してください。
