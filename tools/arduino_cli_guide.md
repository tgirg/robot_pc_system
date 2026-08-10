# Arduino CLIガイド

## Arduino CLIとは

Arduino CLIは、Arduino IDEを開かずにコマンドラインからスケッチのコンパイル、書き込み、ボード管理、シリアルモニタを実行するためのツールです。

## なぜこのプロジェクトで使うのか

チームメンバーのPCやロボット搭載ミニPCで、同じ手順でESP32を書き込めるようにするためです。
PCダッシュボードはArduino CLIがなくても動きますが、ESP32のファームウェア更新にはArduino CLIがあると便利です。

## Arduino IDEとの違い

- Arduino IDE: 画面上でスケッチ編集、ボード選択、書き込みを行う。
- Arduino CLI: batファイルやコマンドで同じ処理を実行する。

Arduino IDEに慣れている場合はIDEを使っても構いません。チームで手順をそろえる場合はArduino CLIが便利です。

## インストール方法の概要

1. Arduino CLIをインストール
2. `arduino-cli.exe` にPATHを通す
3. コマンドプロンプトで `arduino-cli version` が動くことを確認
4. `tools\setup_arduino_cli.bat` を実行

PATHが通っていない場合、batファイルから `arduino-cli` を見つけられません。

## ESP32 core setup

次を実行します。

```cmd
tools\setup_arduino_cli.bat
```

このbatはESP32 board manager URLを追加し、`esp32:esp32` coreをインストールします。

## upload_esp32_drive.batの使い方

```cmd
tools\upload_esp32_drive.bat COM10
```

COM番号は `tools\list_ports.bat` で確認します。
FQBNが違う場合は `tools\upload_esp32_drive.bat` の `FQBN` を変更してください。

## serial_monitor_esp32.batの使い方

```cmd
tools\serial_monitor_esp32.bat COM10
```

ボーレートは `115200` です。

## よくあるエラー

### COMポートが違う

`tools\list_ports.bat` で確認し、正しいCOM番号を指定してください。

### ポートが使用中

Arduino IDE、別のシリアルモニタ、PCダッシュボードが同じCOMポートを開いている場合があります。閉じてから再実行してください。

### FQBNが違う

ESP32 DevKit、ESP32-C3、ESP32-S3などでFQBNが異なります。`tools\upload_esp32_drive.bat` 内の候補を参考に変更してください。

### USBケーブルが充電専用

充電専用ケーブルではCOMポートが出ないことがあります。データ通信対応ケーブルを使ってください。

### BOOTボタンが必要

一部のESP32ボードでは書き込み開始時にBOOTボタンを押す必要があります。

### ドライバ未導入

CP210x、CH340などのUSBシリアルドライバが必要な場合があります。ボードに合うドライバをインストールしてください。
