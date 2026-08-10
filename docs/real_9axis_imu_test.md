# 9軸IMU認識確認

## 目的

Arduino IDEで認識できている9軸IMUを、ダッシュボード側のESP32開発環境でも確認します。

## 追加スケッチ

次のスケッチを使います。

```text
esp32/imu_9axis_test/imu_9axis_test.ino
```

既定のI2Cピンは次の通りです。

- SDA: GPIO21
- SCL: GPIO22
- Serial: 115200 bps

## アプリから書き込む手順

1. `診断` タブを開きます。
2. `ESP32書き込み` の `9軸IMUテストを書き込む` を押します。
3. `ボード一覧更新` でCOMポートを確認します。COM10が見つかれば自動で優先します。
4. `コンパイル確認` を押します。
5. 成功したら、安全確認にチェックして `ESP32へ書き込み` を押します。
6. 書き込み後、`シリアルで確認` を押します。
7. COMポートと `115200` bps が設定されたら、`接続` を押します。

短縮手順として、`9軸IMUテストをコンパイルして書き込み` も使えます。
このボタンは `imu_9axis_test` を選択してコンパイルし、成功した場合だけ確認ダイアログを出します。
確認しない限り書き込みは実行されません。

## 成功時の表示例

```text
BOOT,IMU_9AXIS_TEST_READY
I2C scan start
I2C device found at 0x68
I2C scan done
STATUS,OK
```

`0x68`、`0x69`、`0x28` などが表示されれば、I2C上でIMUを認識できています。
`IMU_STATUS,OK`、`IMU,...`、`GYRO,...` が表示されれば、IMUテスト出力も確認できています。

## 認識できない時の確認

- Arduino IDEのシリアルモニタを閉じる
- SDAがGPIO21、SCLがGPIO22に入っているか確認する
- 3.3VとGNDを確認する
- COMポートが正しいか確認する
- `接続時にESP32をリセット` をオンにして起動ログを取り直す

## 注意

`drive_controller` は壊さず、安全ダミーモードのままです。`MOTOR_OUTPUT_ENABLED 0`、`USE_REAL_LIDAR 0` は維持してください。
