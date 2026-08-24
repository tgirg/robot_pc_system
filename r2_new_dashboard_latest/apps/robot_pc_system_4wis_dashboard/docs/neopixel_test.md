# NeoPixel LEDテスト

## 目的

Arduino-ESP32 coreの `neopixelWrite()` を使って、ESP32のGPIO15に接続したNeoPixel 1個を赤、緑、青の順に点灯確認します。
追加のAdafruit NeoPixelライブラリは不要です。

## 対象スケッチ

```text
esp32/neopixel_test/neopixel_test.ino
```

## 既定設定

```cpp
#define RGB_PIN 15
#define LED_COUNT 1
```

## 書き込み手順

1. `書き込み` タブを開きます。
2. `ESP32を探す` を押してCOMポートを確認します。
3. `NeoPixelテストを書き込む`、またはスケッチ選択で `neopixel_test` を選びます。
4. 確認ダイアログを見てからESP32へ書き込みます。
5. `シリアル` タブに移動し、115200bpsで接続します。

## 動作

500msごとに次の順でLEDが切り替わります。

```text
赤 -> 緑 -> 青 -> 赤 ...
```

## シリアル出力例

```text
BOOT,NEOPIXEL_TEST_READY
FW,neopixel_test,0.2.0
STATUS,OK
NEOPIXEL_STATUS,OK
RGB_PIN,15
LED_COUNT,1
RGB,RED,255,0,0
RGB,GREEN,0,255,0
RGB,BLUE,0,0,255
```

## シリアルコマンド

```text
RED
GREEN
BLUE
OFF
STATUS
```

## 注意

NeoPixelの5Vまたは3.3V、GND、信号線GPIO15を確認してください。
ESP32とNeoPixelのGNDは共通にしてください。
このスケッチはLED確認用で、実モータ出力は有効化しません。
