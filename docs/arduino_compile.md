# ESP32コンパイル確認

## 目的
ESP32をPCに接続していなくても、`drive_controller` スケッチがArduino CLIでコンパイルできるか確認できます。ハードウェア接続や書き込みの前に、コードの構文、ESP32 core、FQBNの設定を確認するための手順です。

## 使い方

```cmd
tools\compile_esp32_drive.bat
```

このbatはアップロードを行いません。COMポートも不要です。

## Arduino CLIの場所
batはまずPATH上の `arduino-cli` を探します。見つからない場合は次の場所を確認します。

```text
C:\Program Files\Arduino CLI\arduino-cli.exe
```

どちらを使っているかは実行時に表示されます。

## FQBNとは
FQBNはArduino CLIが使うボード識別名です。ESP32の種類に合わせて変更します。

代表例:

```text
esp32:esp32:esp32
esp32:esp32:esp32c3
esp32:esp32:esp32c5
esp32:esp32:esp32s3
```

`tools\compile_esp32_drive.bat` の先頭付近にある次の行を編集します。

```bat
set "FQBN=esp32:esp32:esp32"
```

## 安全設定
既定では実モータ出力は無効です。

```cpp
#define MOTOR_OUTPUT_ENABLED 0
```

既定ではIMUもダミーモードです。

```cpp
#define USE_REAL_IMU 0
```

そのため、初回コンパイル確認ではモータドライバや実IMUが接続されていなくても問題ありません。

## よくあるコンパイルエラー
- `arduino-cli` が見つからない: PATHを設定するか、`C:\Program Files\Arduino CLI\arduino-cli.exe` にインストールしてください。
- ESP32 coreがない: `tools\setup_arduino_cli.bat` を実行してください。
- FQBNが違う: ESP32-C5などの場合は `esp32:esp32:esp32c5` を試してください。
- 実IMUを有効にしてライブラリがない: Adafruit MPU6050などをインストールするか、`USE_REAL_IMU` を `0` に戻してください。

## 書き込み
ESP32を接続して書き込む場合は次を使います。

```cmd
tools\upload_esp32_drive.bat COM10
```

書き込み前にArduino IDEのシリアルモニタを閉じてください。
# ダッシュボードからのコンパイル確認

`診断` タブの `ESP32書き込み` セクションで、Arduino CLI確認、ボード一覧更新、コンパイル確認ができます。

ESP32未接続でも `コンパイル確認` は実行できます。書き込みが必要な場合だけ `安全確認しました` にチェックし、確認ダイアログで承認してください。

詳しくは `docs/arduino_upload_from_app.md` を参照してください。
