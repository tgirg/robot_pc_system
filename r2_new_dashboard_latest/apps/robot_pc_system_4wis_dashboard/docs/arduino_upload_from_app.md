# アプリからESP32へ書き込む方法

## 目的

ダッシュボードからArduino CLIを呼び出し、PowerShellを開かずにESP32の `drive_controller` をコンパイル、必要な時だけ書き込みできるようにします。

## 画面の場所

ダッシュボードの `診断` タブに `ESP32書き込み` セクションがあります。

設定タブの `ESP32書き込み画面を開く` ボタンからも移動できます。

## Arduino CLI確認

`Arduino CLI確認` を押すと、次を確認します。
実行中はボタンが一時的に無効化され、進行バーと状態ラベルに処理中であることを表示します。

- Arduino CLIのバージョン
- ESP32 coreの有無
- 接続ボード一覧

Arduino CLIがPATHに無い場合は、次の場所も自動で探します。

`C:\Program Files\Arduino CLI\arduino-cli.exe`
`C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe`
`C:\Program Files (x86)\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe`

## コンパイル確認

`コンパイル確認` を押すと、次を実行します。
完了時には成功または失敗と経過時間を表示します。

```text
arduino-cli compile --fqbn <FQBN> esp32\drive_controller
```

COMポートは不要です。ESP32を接続していなくても確認できます。

通常のFQBNは次です。

```text
esp32:esp32:esp32
```

## ボード一覧更新

`ボード一覧更新` を押すと、次を実行します。

```text
arduino-cli board list
```

ESP32らしいCOMポートが見つかった場合、COM欄へ反映します。
COM10、CP210x、CH340、USB Serial、USB to UART などをESP32候補として優先します。
BluetoothリンクやIntel管理用COMポートはESP32書き込み先として自動選択しません。
候補が見つからない場合は、COM10を手入力候補として表示しますが、実際に書き込むにはESP32をUSB接続してから `更新` または `ボード一覧更新` を押してください。

## 9軸IMUテストの書き込み

`9軸IMUテストを書き込む` を押すと、スケッチを `imu_9axis_test` に切り替え、FQBNを `esp32:esp32:esp32` に設定します。
この時点では書き込みません。続けて `コンパイル確認` または `ESP32へ書き込み` を押してください。

`9軸IMUテストをコンパイルして書き込み` を押すと、`imu_9axis_test` を選択してコンパイルします。
コンパイル成功後に確認ダイアログが表示され、承認した場合だけESP32へ書き込みます。
書き込み後は `シリアルで確認` を押すと、`シリアル` タブへCOMポートと `115200 bps` を設定できます。

## センサテスト近道

`センサテスト近道` から、LiDAR、エンコーダ、光学式オドメトリ、距離センサ、ライン/カラーセンサ、シリアル通信、全センサダミーの各テストスケッチを選べます。
近道ボタンはスケッチ、FQBN、COM候補を設定するだけで、自動書き込みは行いません。
各スケッチの目的は `docs/sensor_test_sketches.md` を参照してください。

## ESP32へ書き込み

`ESP32へ書き込み` は自動実行されません。必ずユーザーがボタンを押した時だけ実行します。

書き込み前に、`安全確認しました` にチェックしてください。その後、確認ダイアログで承認すると書き込みを開始します。
書き込み中は進行バーが表示され、完了後に結果が表示されます。

書き込み前にダッシュボードがESP32へ接続している場合は、一時的に切断します。書き込み完了後は、`実機接続` タブから手動で再接続してください。

実行内容:

```text
arduino-cli upload -p <PORT> --fqbn <FQBN> esp32\drive_controller
```

## よくある失敗

- COMポートが違う
- COM4/COM5などのBluetooth COMを選んでいる
- Arduino IDEのシリアルモニタがCOMポートを使っている
- FQBNが実際のボードと違う
- ESP32が接続されていない
- USBケーブルが通信非対応
- ESP32 coreが入っていない

## 安全注意

`MOTOR_OUTPUT_ENABLED` は `0` のままです。

`USE_REAL_IMU` は `0` のままです。

`USE_REAL_LIDAR` は `0` のままです。

実モータ接続前は、必ず安全ダミー状態で確認してください。

## UI外で確認する場合

```bat
.venv\Scripts\python.exe examples\arduino_compile_upload_check.py --board-list
.venv\Scripts\python.exe examples\arduino_compile_upload_check.py --compile
.venv\Scripts\python.exe examples\arduino_compile_upload_check.py --upload COM10
```

検証時は、明示的に指示がある場合を除きアップロードは実行しません。

## ESP32プログラム編集

`診断` タブには `ESP32プログラム編集` があります。ここで `esp32/drive_controller/drive_controller.ino` を直接編集し、保存、コンパイル確認できます。保存時は `backups/firmware/` にバックアップを作成します。危険そうなコードは警告しますが、自由編集は止めません。

詳しくは `docs/firmware_editor.md` を参照してください。

## 書き込み後のシリアル確認

ESP32へ書き込んだ後は、`シリアル` タブで生Serial出力を確認できます。Arduino IDEのシリアルモニタを開かずに、I2Cスキャナやセンサテスト出力を確認できます。詳しくは `docs/serial_monitor.md` を参照してください。

9軸IMU確認用に `imu_9axis_test` スケッチを選べます。通常は `9軸IMUテストを書き込む` または `9軸IMUテストをコンパイルして書き込み` を使います。書き込み後はシリアルモニタを115200 bpsで接続します。
## 書き込みタブからの書き込み

`書き込み` タブでは、検証と書き込みを簡単に実行できます。シリアル確認は別の `シリアル` タブで行います。

### かんたん書き込み

通常は画面上部の `かんたん書き込み` を使います。

1. ESP32をUSB接続します。
2. `1 ESP32を探す` を押します。
3. `ESP32候補: COMxx` と表示されることを確認します。
4. 目的に合わせて `9軸IMUテストを書き込む`、`通常制御を書き込む`、または `選択中を書き込む` を押します。
5. コンパイル成功後の確認ダイアログで承認すると書き込みます。
6. 書き込み後は `シリアルで確認` を押して出力を確認します。

ESP32が見つからない場合、Bluetooth COMやIntel管理用COMは自動選択しません。ESP32を挿し直して `1 ESP32を探す` を押してください。

- `✓ 検証`: 現在のスケッチを保存してコンパイル
- `→ 書き込み`: 保存、コンパイル、確認ダイアログ、アップロードの順で実行
- `シリアルで確認`: 書き込み後にCOMポートと115200 bpsを設定して `シリアル` タブへ移動
- `更新`: ESP32のUSBシリアル候補を再検出。Bluetooth COMは書き込み先として除外

従来の `診断` タブのESP32書き込み画面は残しています。通常の書き込み作業では `書き込み` タブを使ってください。
## 高速書き込み

`高速書き込み` をONにすると、前回の `コンパイル確認` または書き込み前コンパイルで作成したビルドを再利用します。
同じスケッチを何度も書き込む時は、コンパイルを省略できるため速くなります。

初回やスケッチ変更後はキャッシュがないため、通常どおりコンパイルしてから書き込んでください。
キャッシュは日本語パス問題を避けるため、次の場所に保存します。

```text
%LOCALAPPDATA%\robot_pc_system\arduino_cache
```

注意:
- コードを変更した後は、必ず一度 `コンパイル確認` または通常書き込みを実行してください。
- 古いキャッシュのまま高速書き込みすると、古いプログラムが入ります。
- COMポートがアプリやArduino IDEに使われている場合は、高速書き込みでも失敗します。
