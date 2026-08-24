# 自作ESP32センサ基板 GPIO定義

この資料は、R2で使用する自作ESP32接続基板の9個のセンサコネクタを正式なGPIO定義として整理したものです。

## 共通配線

距離センサ用4ピンコネクタは以下の順で扱います。

| ピン | 信号 | 内容 |
| --- | --- | --- |
| 1 | SIG | 各GPIOへ接続。基板上の抵抗を経由 |
| 2 | NC | 未接続 |
| 3 | VCC | 3.3V |
| 4 | GND | GND |

## GPIO一覧

| センサ名 | GPIO | 用途 |
| --- | ---: | --- |
| FL | GPIO13 | 前左の距離センサ |
| FR | GPIO14 | 前右の距離センサ |
| RR | GPIO27 | 右後の距離センサ |
| BR | GPIO26 | 後右の距離センサ |
| BL | GPIO25 | 後左の距離センサ |
| LB | GPIO33 | 左後の距離センサ |
| LF | GPIO32 | 左前の距離センサ |
| US1 | GPIO35 | 超音波センサ1 |
| US2 | GPIO23 | 超音波センサ2 |

## 共通ヘッダ

新規テストスケッチではGPIO番号を直書きせず、以下をincludeしてください。

```cpp
#include "../custom_board_pins.h"
```

またはスケッチ配置に合わせて `custom_board_pins.h` を同じフォルダへコピーしてください。

定義済み定数:

```cpp
constexpr int PIN_FL  = 13;
constexpr int PIN_FR  = 14;
constexpr int PIN_RR  = 27;
constexpr int PIN_BR  = 26;
constexpr int PIN_BL  = 25;
constexpr int PIN_LB  = 33;
constexpr int PIN_LF  = 32;

constexpr int PIN_US1 = 35;
constexpr int PIN_US2 = 23;
```

## GPIO35の注意

US1のGPIO35はESP32では入力専用GPIOです。

1線式Grove超音波センサのように、同じSIGピンを一度OUTPUTにしてTrigを出し、その後INPUTでEchoを読む方式では、GPIO35からTrigを出せません。US1でその方式の超音波センサを使う場合は、GPIO35のままでは動作しません。

GPIO35で確認できるのは、外部回路またはセンサ側が自力で出力する信号の入力読み取りです。

## 個別確認順

1. FL / GPIO13
2. FR / GPIO14
3. RR / GPIO27
4. BR / GPIO26
5. BL / GPIO25
6. LB / GPIO33
7. LF / GPIO32
8. US1 / GPIO35
9. US2 / GPIO23

シリアル出力の形式は以下を基準にします。

```text
SENSOR,FL,GPIO13,RAW,1234
SENSOR,FR,GPIO14,RAW,987
ULTRASONIC,US1,GPIO35,DISTANCE_MM,350
```

