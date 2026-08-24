# ロボット制作プロジェクト

## R2を新GUIから動かす経路

新しい共有ダッシュボードに、R2実機専用の起動経路を追加しています。旧ダッシュボードや
`run-pc-controller.cmd`は起動しません。

```cmd
.\run-r2-new-dashboard.cmd --port COM7
```

既定ではアクチュエータのARM・走行入力を抑止します。接続確認後、車輪を浮かせた実機確認に限り
`--enable-motion`を明示し、PWM 120以下で開始します。手順は
`docs/r2_new_gui_first_motion.md`を参照してください。

このフォルダは、4輪独立ステアリング車両の基板資料、ESP32ファームウェア、Windows PC側コントローラ、設定ファイル、検証用テストをまとめた作業場所です。

フォルダ全体の見取り図だけ見たい場合は、まず `00_START_HERE.md` を開いてください。詳しい置き場ルールは `docs/project-map.md` にあります。

このREADMEは「何をどうすれば実機を動かせるか」を優先して書いています。まだ設定が未完のまま通常走行させないよう、最初は必ず車輪を浮かせて、低出力のDEBUG動作から確認してください。

## まず結論

R2を新GUIから動かす順番は次の通りです。

1. ESP32に `esp32_firmware/esp32_firmware.ino` を書き込む。
2. PC側は `run-r2-new-dashboard.cmd` から起動する。旧GUIや旧CLI制御画面は起動しない。
3. 通常はCOMポートを手で指定しない。PC側が各COMへ `who_are_you` を送り、`role=drive` のESP32を自動選択する。
4. まず `--enable-motion` なしで接続し、R2が `ONLINE / SAFE / READY_DISARMED` になることを確認する。
5. 車輪を浮かせ、`.\run-r2-new-dashboard.cmd --enable-motion --max-pwm 60` で低出力確認する。
6. 起動後にARMボタンを一度すべて放し、`L1 + R1 + ×`を1秒保持してNORMAL ARMする。`OPTIONS`でSAFEへ戻す。
7. 車輪・ステア・エンコーダの対応が一致した後だけ、上限120まで段階的に上げる。

重要: `run-r2-new-dashboard.cmd`は新GUIを開き、内部で検証済みの`ControllerApp`、NDJSONプロトコル、再接続、安全監視だけを再利用します。`--enable-motion`がない限り、コントローラのARMと走行軸は抑止されます。

旧`run-pc-controller.cmd`は比較・診断用の既存CLIとして残しますが、R2の通常オペレータ起動経路には使用しません。

旧ダッシュボードの`DRIVE VEL 100 100`形式の走行ボタンは、新GUIの実機経路から完全に分離しています。R2の新GUIは`apps/robot_pc_system_4wis_dashboard/pc/real_dashboard_main.py`を入口にし、v29 NDJSON経路だけを所有します。

最後に作られたログを見るには、PowerShellで次を実行します。

```powershell
Get-ChildItem .\logs\pc-controller-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Get-ChildItem .\logs\pc-controller-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 80
```

ログ内では、PCからESP32へ送った行は `serial TX ...`、ESP32からPCへ返ってきた行は `serial RX ...` と表示されます。例えば `serial RX` の中に `encoder_count` と `wheel_rpm` が出ていれば、エンコーダと回転数の記録が残っています。

## 実機を動かすまでの詳細手順

この章は、初回セットアップから浮かせた状態の低出力テストまでを順番に並べたものです。途中で失敗したら、先に進まず、そのステップを直してから次へ進みます。

### 0. 作業前にやること

1. 車体を台の上に置き、4輪が地面に触れない状態にする。
2. モータ電源は最初は切っておく。
3. サーボ電源も、配線確認が終わるまでは切っておく。
4. ESP32だけUSBでPCへ接続する。
5. Arduino Serial Monitor、別のPython、別ターミナルなど、同じCOMポートを開くソフトを閉じる。

確認する配線:

| 対象 | 確認内容 |
| --- | --- |
| ESP32 USB | PCにCOMポートとして見える |
| PCA9685 | SDA=`GPIO21`, SCL=`GPIO22`, address=`0x40` |
| GND | ESP32、PCA9685、MD10Cロジック、エンコーダGNDが共通 |
| サーボ電源 | PCA9685のV+へ外部5〜6Vを入れる。ESP32の3V3/5Vからサーボを駆動しない |
| モータ電源 | MD10Cのモータ電源へ入れる。ESP32の5V/3V3へ入れない |
| エンコーダ | AMT102-Vを5V出力で使う場合はESP32 GPIOへ直結せず、レベルシフタを使う |

### 1. PowerShellでプロジェクトへ移動する

PowerShellを開き、次を実行します。

```powershell
cd "C:\Users\kgenk\OneDrive\Desktop\ロボット制作プロジェクト"
```

今いる場所を確認します。

```powershell
pwd
```

表示が次の場所なら正しいです。

```text
C:\Users\kgenk\OneDrive\Desktop\ロボット制作プロジェクト
```

### 2. PC側Pythonを使える状態にする

現在のこのPCでは、プロジェクト内の `.venv` と `.venv_win` は日本語パスの文字化けの影響で壊れている可能性があります。そのため、実機操作ではプロジェクト内venvを直接有効化せず、ASCIIパスに作った次の環境を使います。

```powershell
C:\robot_venvs\robot_project_kicad\Scripts\python.exe
```

通常は仮想環境を有効化しなくて構いません。プロジェクト直下で次の起動スクリプトを使います。PowerShellの実行ポリシーで `.ps1` が止まることがあるため、通常は `.cmd` を使います。

```powershell
.\run-pc-controller.cmd --list-controllers
```

`Activate.ps1` をダブルクリックすると、PowerShellではなくメモ帳などで開くことがあります。これは異常ではありません。`.ps1` はダブルクリックで開くものではなく、PowerShellの画面にコマンドとして入力して実行します。

手動で有効化したい場合だけ、PowerShellで次を実行します。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "C:\robot_venvs\robot_project_kicad\Scripts\Activate.ps1"
```

成功すると、PowerShellの先頭に次のように表示されます。

```text
(robot_project_kicad) PS C:\Users\kgenk\OneDrive\Desktop\ロボット制作プロジェクト>
```

ただし、以降の手順では有効化なしで `.\run-pc-controller.cmd ...` を使うのが一番確実です。

### 3. PC側ソフトが動くか確認する

プロジェクト直下で実行します。

```powershell
& "C:\robot_venvs\robot_project_kicad\Scripts\python.exe" -m pytest
.\run-pc-controller.cmd --simulate --once
```

期待する結果:

| コマンド | 成功条件 |
| --- | --- |
| `& "C:\robot_venvs\robot_project_kicad\Scripts\python.exe" -m pytest` | 全テストが `passed` になる |
| `.\run-pc-controller.cmd --simulate --once` | エラーを出さずに終了する |

この段階ではESP32やモータは動きません。PC側の設定読み込み、運動学、プロトコル生成が壊れていないかを見るだけです。

### 4. ESP32のCOMポートを確認する

ESP32をUSB接続した状態で実行します。

```powershell
@'
from serial.tools import list_ports
for p in list_ports.comports():
    print(p.device, p.description)
'@ | python -
```

例:

```text
COM7 USB-SERIAL CH340
```

このREADMEでは `COM7` を例にしています。違う番号なら、以降の `COM7` を実際の番号に置き換えます。

COMポートが出ない場合:

- USBケーブルが充電専用でないか確認する。
- ESP32の電源LEDが点いているか見る。
- デバイスマネージャーでUSBシリアルドライバを確認する。
- Arduino IDEやSerial Monitorを閉じる。

### 5. ESP32ファームウェアを書き込む

Arduino IDEで行う場合:

1. Arduino IDEを開く。
2. Board ManagerでESP32 board packageを入れる。
3. Library Managerで `ArduinoJson` を入れる。
4. `esp32_firmware/esp32_firmware.ino` を開く。
5. Boardは `ESP32 Dev Module` 系を選ぶ。
6. Portは手順4で確認したCOMポートを選ぶ。
7. Uploadする。
8. Serial Monitorを開く場合は `115200 bps` にする。ただし、Pythonで通信確認する前には閉じる。

Arduino CLIで行う場合:

```powershell
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile --fqbn esp32:esp32:esp32 --build-path "$env:TEMP\arduino-build-4wis" esp32_firmware
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" upload -p COM7 --fqbn esp32:esp32:esp32 esp32_firmware
```

コンパイルが通ってアップロードだけ失敗する場合:

- Serial Monitorを閉じる。
- 別PowerShellで同じCOMポートを開いていないか確認する。
- Arduino IDEを一度閉じる。
- USBを抜き差しする。
- `COM7` が実際のCOM番号と一致しているか再確認する。

### 6. ESP32と通信できるか確認する

モータ電源はまだ切ったままで構いません。サーボ電源も、必要ならまだ切ったままで構いません。

```powershell
@'
import json
import time
import serial

port = "COM7"
ser = serial.Serial(port, 115200, timeout=1)
time.sleep(0.5)

ser.write((json.dumps({"v": 1, "type": "hello"}) + "\n").encode())
deadline = time.time() + 3
while time.time() < deadline:
    line = ser.readline()
    if line:
        print(line.decode(errors="replace").strip())
ser.close()
'@ | python -
```

期待する結果:

```text
{"v":1,"type":"hello_ack",...}
```

`pca9685_ok:false` が出る場合は、PCA9685のI2C配線、VCC/GND、アドレスを確認します。PCA9685が見つからない状態ではNORMAL ARMできません。

### 7. `vehicle_config.json` の必須項目を埋める

`config/vehicle_config.json` を編集します。初期状態では次が0なので、そのままではNORMAL ARMできません。

最低限、実測値に置き換えます。

```json
"motion": {
  "wheelbase_m": 0.327,
  "track_width_m": 0.327,
  "wheel_diameter_m": 0.055,
  "max_wheel_rpm": 520.0
}
```

意味:

| 項目 | 入れる値 |
| --- | --- |
| `wheelbase_m` | 前輪中心と後輪中心の距離。単位m |
| `track_width_m` | 左右輪中心間距離。単位m |
| `wheel_diameter_m` | 車輪直径。単位m |
| `max_wheel_rpm` | 初回は控えめな最大回転数 |

サーボchは共有リンクで動いた値を反映済みです。

```json
"servos": [
  {"name": "FL", "channel": 6, "center_us": 1490, ...},
  {"name": "FR", "channel": 5, "center_us": 1580, ...},
  {"name": "RL", "channel": 7, "center_us": 1590, ...},
  {"name": "RR", "channel": 4, "center_us": 1550, ...}
]
```

最初は `pid_enabled` を `false` のままにします。PIDは、モータ方向、エンコーダ方向、1回転カウントが確定してから有効にします。

### 8. PC側設定をESP32へ送る

設定ファイルを編集したら、ESP32へ送ります。

```powershell
python -m pc_controller.main --port COM7 --once
```

成功すると、ESP32側へ `config` が送られ、ESP32のNVSにも保存されます。

注意:

- このコマンドだけでは走行しません。
- `--once` は設定送信と通信確認だけで終了します。ジョイスティック走行ループは継続実行時だけ動きます。
- `ValueError: wheelbase_m and track_width_m must be set` が出る場合は、手順7の車体寸法が0のままです。

### 9. DEBUGでモータを1輪ずつ確認する

ここで初めてモータ電源を入れます。必ず4輪を浮かせたままにします。

次は `wheel=0`、つまりFLだけを低PWMで短時間回す例です。

```powershell
@'
import json
import time
import serial

port = "COM7"
ser = serial.Serial(port, 115200, timeout=1)

def send(obj):
    ser.write((json.dumps(obj) + "\n").encode())
    time.sleep(0.05)

send({"v": 1, "type": "hello"})
send({"v": 1, "type": "arm", "mode": "debug"})
send({"v": 1, "type": "debug", "action": "motor_test", "wheel": 0, "pwm": 80, "direction": True})
time.sleep(0.5)
send({"v": 1, "type": "debug", "action": "motor_stop", "wheel": 0})
send({"v": 1, "type": "disarm"})
ser.close()
'@ | python -
```

確認すること:

| 見るもの | OK | NGなら |
| --- | --- | --- |
| 動く車輪 | FLだけが動く | `motors[].physical` を見直す |
| 回転方向 | 想定した正転 | `motors[].inverted` を切り替える |
| 停止 | 0.5秒後に止まる | すぐDISARMし、配線とログを見る |
| 音/発熱 | 異常なし | 電源を切って原因を探す |

同じ確認を `wheel=1`, `wheel=2`, `wheel=3` でも行います。

### 10. DEBUGでサーボを1個ずつ確認する

サーボ電源を入れます。モータ電源は切っていて構いません。

最初は各輪の中心値付近だけを試します。v29相当の中心値は `FL=1490us`, `FR=1580us`, `RL=1590us`, `RR=1550us` です。

```powershell
@'
import json
import time
import serial

port = "COM7"
wheel = 0
pulses = [1490, 1510, 1470, 1490]

ser = serial.Serial(port, 115200, timeout=1)

def send(obj):
    ser.write((json.dumps(obj) + "\n").encode())
    time.sleep(0.2)

send({"v": 1, "type": "hello"})
send({"v": 1, "type": "arm", "mode": "debug"})
for pulse in pulses:
    send({"v": 1, "type": "debug", "action": "servo_us", "wheel": wheel, "pulse_us": pulse})
send({"v": 1, "type": "disarm"})
ser.close()
'@ | python -
```

確認すること:

| 見るもの | OK | NGなら |
| --- | --- | --- |
| 動く車輪 | `wheel=0` ならFLサーボ | `servos[].channel` と配線ラベルを確認 |
| 方向 | 角度増加方向が想定通り | `direction_inverted` を切り替える |
| 中心 | 各輪の `center_us` 付近で前方 | `center_us` と `trim_deg` を調整 |
| 可動範囲 | 機械的に当たらない | `min_us/max_us`, `min_angle_deg/max_angle_deg` を狭める |

4個すべてで中心と安全範囲を確認したら、該当サーボの `calibrated` を `true` にします。未確認のまま `true` にしないでください。

### 11. DEBUGでエンコーダを確認する

対象輪のカウントを0にして、手でゆっくり1回転させます。

```powershell
@'
import json
import time
import serial

port = "COM7"
wheel = 0
ser = serial.Serial(port, 115200, timeout=1)

def send(obj):
    ser.write((json.dumps(obj) + "\n").encode())
    time.sleep(0.05)

send({"v": 1, "type": "hello"})
send({"v": 1, "type": "arm", "mode": "debug"})
send({"v": 1, "type": "debug", "action": "encoder_zero", "wheel": wheel})

print("対象輪を手で1回転させてください")
time.sleep(5)

send({"v": 1, "type": "ping", "seq": 1})
deadline = time.time() + 3
while time.time() < deadline:
    line = ser.readline()
    if line:
        print(line.decode(errors="replace").strip())

send({"v": 1, "type": "disarm"})
ser.close()
'@ | python -
```

確認すること:

| 見るもの | OK | NGなら |
| --- | --- | --- |
| カウント変化 | 対象輪の `encoder_count` だけ変わる | `encoders[].physical` を見直す |
| 符号 | 正転でプラス | `encoders[].inverted` を切り替える |
| 1回転カウント | 3回以上測って近い値になる | 配線、ノイズ、AMT102-V設定を確認 |

PIDを使う予定がある場合は、3回以上測った中央値または平均値を `encoders[].counts_per_wheel_rev` に書きます。

### 12. NORMAL ARMの条件を満たす

NORMALで低速走行テストする前に、必ず次を満たします。

| 条件 | 必須か |
| --- | --- |
| PCA9685が `pca9685_ok:true` | 必須 |
| `wheelbase_m`, `track_width_m`, `wheel_diameter_m`, `max_wheel_rpm` が0より大きい | 必須 |
| 4個すべての `servos[].calibrated` が `true` | 必須 |
| モータの対応と回転方向をDEBUGで確認済み | 必須 |
| エンコーダ対応と符号をDEBUGで確認済み | PID使用時は必須 |
| `pid_enabled=false` | 初回推奨 |

設定を直したら、もう一度ESP32へ送ります。

```powershell
python -m pc_controller.main --port COM7 --once
```

### 13. 浮かせた状態でNORMAL低出力テストをする

ここでも車輪は地面から浮かせたままです。次はNORMAL ARMし、前進相当の低PWMを短時間だけ送る例です。

```powershell
@'
import json
import time
import serial

port = "COM7"
ser = serial.Serial(port, 115200, timeout=1)
seq = 1

def send(obj):
    global seq
    if obj.get("type") == "drive":
        obj["seq"] = seq
        seq += 1
    ser.write((json.dumps(obj) + "\n").encode())
    time.sleep(0.03)

send({"v": 1, "type": "hello"})
send({"v": 1, "type": "arm", "mode": "normal"})

start = time.time()
while time.time() - start < 1.0:
    send({
        "v": 1,
        "type": "drive",
        "armed": True,
        "control": "pwm",
        "steer_deg": [0.0, 0.0, 0.0, 0.0],
        "drive_target": [80, 80, 80, 80]
    })

for _ in range(10):
    send({
        "v": 1,
        "type": "drive",
        "armed": True,
        "control": "pwm",
        "steer_deg": [0.0, 0.0, 0.0, 0.0],
        "drive_target": [0, 0, 0, 0]
    })

send({"v": 1, "type": "disarm"})
ser.close()
'@ | python -
```

期待する動作:

1. `arm_ack` が `ok:true`, `state:"NORMAL"` になる。
2. 4輪サーボが0度付近へ向く。
3. 4輪が同じ方向へ低速で回る。
4. `drive_target` を0にした瞬間にモータ出力が0へ落ちる。
5. DISARM後はモータが完全停止する。

このテストが成功したら、共有リンクで確認した順に近い形で、次を行います。

| 段階 | やること |
| --- | --- |
| 25% | 低PWMで短時間回す。ニュートラルで即停止するか見る |
| 50% | 異音、発熱、方向ズレがないか見る |
| 100% | 2〜3秒だけ。ニュートラルで即停止するか見る |

地面に置くのは、浮かせた状態で対応、方向、停止、サーボ範囲がすべて正しいと確認してからです。

## 安全前提

- 初回は必ず車輪を地面から浮かせる。
- モータ電源、サーボ電源、ESP32/PC側制御電源を混同しない。
- ESP32 GND、MD10CロジックGND、PCA9685 GND、エンコーダGNDは共通にする。
- モータ用バッテリをESP32の5V/3V3へ直結しない。
- AMT102-Vを5V出力で使う場合、ESP32 GPIOへ直結しない。レベルシフタを入れる。
- Arduino Serial Monitor、他のPythonプロセス、別ターミナルがCOMポートを開いていると、このREADMEのコマンドは失敗する。
- モータが逆転、急加速、スパーク、異音、異常発熱したらすぐDISARMし、電源を切る。

## フォルダ構成

```text
esp32_firmware/
  esp32_firmware.ino        ESP32側メイン
  board_pins.h              MCB44向けピン定義
  vehicle_config.h          設定構造体と制御定数
  motor_control.*           MD10C向けDIR/PWM出力
  encoder_control.*         4輪AB相エンコーダ読み取り
  servo_control.*           PCA9685サーボ制御
  pid_controller.*          RPM PID制御
  serial_protocol.*         USB Serial NDJSONプロトコル
  config_storage.*          ESP32 NVSへの設定保存
  safety_manager.*          SAFE/NORMAL/DEBUG管理
  external_estop.*          外部非常停止のスタブ

pc_controller/
  main.py                   PC側エントリポイント
  app.py                    PC側実行ループ
  kinematics.py             4輪独立ステアリング運動学
  steering_optimizer.py     斜行時のサーボ角最適化
  protocol.py               NDJSON生成/検証
  serial_link.py            pyserial通信
  controller_input.py       pygameジョイスティック入力部品
  debug_mode.py             DEBUGコマンド生成部品
  calibration.py            エンコーダ校正用ヘルパ
  simulator.py              ESP32なしの簡易シミュレータ

config/
  vehicle_config.json       車体寸法、モータ、エンコーダ、サーボ設定
  controller_mapping.json   コントローラ軸/ボタン設定

tests/
  test_*.py                 pytest自動テスト

PINMAP_REPORT.md            ピン採用理由と照合結果
requirements.txt            Python依存ライブラリ
```

## 採用ピン

論理輪の順番は全ファイルで固定です。

| Logical | 位置 | Motor | PWM | DIR | Encoder | A | B | PCA9685 |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| 0 | FL Front Left | M3 | GPIO25 | GPIO26 | ENC1 / J5 | GPIO35 | GPIO34 | ch6 |
| 1 | FR Front Right | M2 | GPIO27 | GPIO23 | ENC2 / J6 | GPIO36 | GPIO39 | ch5 |
| 2 | RL Rear Left | M4 | GPIO18 | GPIO16 | ENC3 / J7 | GPIO4 | GPIO13 | ch7 |
| 3 | RR Rear Right | M1 | GPIO19 | GPIO14 | ENC4 / J8 | GPIO33 | GPIO32 | ch4 |

| 機能 | ピン |
| --- | ---: |
| I2C SDA | GPIO21 |
| I2C SCL | GPIO22 |
| USB Serial TX0 | GPIO1 予約 |
| USB Serial RX0 | GPIO3 予約 |
| PCA9685初期アドレス | 0x40 |
| Serial baudrate | 115200 |

## v29相当の実機動作構成

2026-08-09時点で実機動作したESP32 v29相当の構成を、このプロジェクトの正解として反映しています。

- モータ物理対応は `FL=M3`, `FR=M2`, `RL=M4`, `RR=M1`。`motors[].physical` は `[2, 1, 3, 0]`。
- モータは全輪 `inverted=true`。
- サーボchは `FL=6`, `FR=5`, `RL=7`, `RR=4`。`servos[].channel` は `[6, 5, 7, 4]`。
- サーボ中心値は `FL=1490us`, `FR=1580us`, `RL=1590us`, `RR=1550us`。
- `config/vehicle_config.json`、PC側の既定値、ESP32側のNVS初期値、README、`PINMAP_REPORT.md` を同じ割り当てへ同期済み。
- エンコーダはESP32のPCNTハードウェアカウンタをNORMAL必須条件にする。PCNTが無い、または初期化できない場合はNORMAL ARMを拒否する。
- 走行指令の `driveTarget` が4輪すべて0になった時は、PID積分値をリセットし、モータPWMの目標値・現在値・実出力を即0にする。
- 低速の実機確認は、車輪を浮かせて `25% -> ニュートラル`, `50% -> ニュートラル`, `100%を2〜3秒 -> ニュートラル` の順で行う。

注意:

- GPIO34, GPIO35, GPIO36, GPIO39は入力専用です。エンコーダ入力には使えますが出力には使えません。
- GPIO21/22はI2C用に予約しています。
- GPIO16はFreenove系ESP32ではオンボードRGB LEDとしても使われますが、このファームウェアでは `M4_DIR` として扱います。
- 実機配線前に、MD10C側コネクタのGND/DIR/PWM順は必ずテスタで確認してください。

## PC環境を作る

PowerShellをこのフォルダで開きます。

```powershell
cd "C:\Users\kgenk\OneDrive\Desktop\ロボット制作プロジェクト"
```

すでにこの作業環境では `.venv_win` を作成済みです。まずこれを使います。

```powershell
.\.venv_win\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

もしPowerShellの実行ポリシーで有効化できない場合は、そのPowerShellだけ一時的に許可してから再実行します。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv_win\Scripts\Activate.ps1
```

`.venv_win` が存在しない場合は、Windows用Pythonで作り直します。`python` がInkscape同梱Pythonを指す場合があるので、先に確認します。

```powershell
where python
py -3 -m venv .venv_win
.\.venv_win\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PC側だけの動作確認:

```powershell
python -m pytest
python -m pc_controller.main --simulate --once
```

`--simulate --once` はESP32なしで1回だけ制御ループを回します。実機は動きません。

## ESP32ファームウェアを書き込む

Arduino IDEで行う場合:

1. Arduino IDEを開く。
2. Board ManagerでESP32 board packageを入れる。
3. Library Managerで `ArduinoJson` を入れる。
4. `esp32_firmware/esp32_firmware.ino` を開く。
5. Boardは `ESP32 Dev Module` 系を選ぶ。
6. PortはESP32のCOMポートを選ぶ。
7. Uploadする。
8. Serial Monitorは `115200 bps` にする。

Arduino CLIでコンパイルする場合:

```powershell
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile --fqbn esp32:esp32:esp32 --build-path C:\tmp\arduino-build-4wis esp32_firmware
```

Arduino CLIで書き込む場合:

```powershell
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" upload -p COM7 --fqbn esp32:esp32:esp32 esp32_firmware
```

COM番号は自分の環境に合わせて変更してください。日本語パスでArduinoビルドが失敗する場合は、上のように `--build-path C:\tmp\arduino-build-4wis` のような短いASCIIパスを使います。

## COMポートを確認する

`.venv_win` を有効化したPowerShellで実行します。

```powershell
@'
from serial.tools import list_ports

for port in list_ports.comports():
    print(f"{port.device}: {port.description}")
'@ | python -
```

ESP32が `COM7` として見えているなら、以下は `COM7` のままで進めます。違う場合は、以降の `port = "COM7"` を実際のCOM番号に変えます。

ESP32が応答するか確認します。

```powershell
@'
import serial
import time

port = "COM7"

with serial.Serial(port, 115200, timeout=0.2) as ser:
    time.sleep(2.0)
    ser.write(b'{"v":1,"type":"hello","client":"manual"}\n')
    until = time.time() + 3.0
    while time.time() < until:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").strip())
'@ | python -
```

正常なら `hello_ack` や `telemetry` が出ます。`pca9685_ok:false` が出る場合は、PCA9685のI2C配線、電源、アドレスを先に直してください。NORMAL ARMはPCA9685が見つからないと拒否されます。

## まずDEBUGで1輪ずつ動かす

ここではNORMAL走行を使いません。DEBUG ARMは低出力、短時間、単体確認のためのモードです。

### モータ1個だけ回す

車輪を必ず浮かせてから実行します。`wheel = 0` はFLです。`pwm = 80` は10bit PWMの低出力です。ESP32側でもDEBUGモータ出力は最大約10%に制限されます。

```powershell
@'
import json
import serial
import time

port = "COM7"
wheel = 0
pwm = 80
forward = True

def send(ser, msg, wait=0.15):
    ser.write((json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8"))
    until = time.time() + wait
    while time.time() < until:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").strip())

with serial.Serial(port, 115200, timeout=0.05) as ser:
    time.sleep(2.0)
    send(ser, {"v": 1, "type": "hello", "client": "manual"})
    send(ser, {"v": 1, "type": "arm", "mode": "debug"})
    send(ser, {"v": 1, "type": "debug", "action": "motor_test", "wheel": wheel, "pwm": pwm, "direction": forward}, wait=0.35)
    send(ser, {"v": 1, "type": "debug", "action": "motor_stop", "wheel": wheel})
    send(ser, {"v": 1, "type": "disarm"})
'@ | python -
```

確認すること:

- FLだけが回るか。
- 想定と逆方向なら `config/vehicle_config.json` の `motors[0].inverted` を切り替える。
- 別の車輪が回ったら、`motors[].physical` の対応が違う。
- `wheel = 1`, `2`, `3` に変えてFR/RL/RRも同じ確認をする。

`motors[].physical` は、論理輪から実際のM1/M2/M3/M4への対応です。例えば論理FLでM2が回るなら、FLの `physical` を `1` にするか、配線側を直します。

### サーボ1個だけ動かす

未校正のサーボはNORMALでは動かしません。DEBUGでは `servo_us` を使い、パルス幅で少しずつ確認します。

```powershell
@'
import json
import serial
import time

port = "COM7"
wheel = 0
pulses = [1490, 1510, 1470, 1490]

def send(ser, msg, wait=0.35):
    ser.write((json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8"))
    until = time.time() + wait
    while time.time() < until:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").strip())

with serial.Serial(port, 115200, timeout=0.05) as ser:
    time.sleep(2.0)
    send(ser, {"v": 1, "type": "arm", "mode": "debug"})
    for pulse in pulses:
        send(ser, {"v": 1, "type": "debug", "action": "servo_us", "wheel": wheel, "pulse_us": pulse})
    send(ser, {"v": 1, "type": "disarm"})
'@ | python -
```

確認すること:

- 各輪の `center_us` 付近で車輪が車体前方を向くか。
- 前方からずれている場合は、そのサーボの `center_us` を調整する。
- 機械的に当たる手前の安全な下限/上限を `min_us`, `max_us` に書く。
- 角度範囲を `min_angle_deg`, `max_angle_deg` に書く。270度サーボなら例として `-135.0` から `135.0`。
- 4個すべてを確認してから `calibrated` を `true` にする。

ESP32には `servo_calibrated` debug commandもありますが、PC側の `config/vehicle_config.json` が実質の元データです。ESP32へcommitしても、後でPCから古いconfigを送ると上書きされます。校正結果は必ず `config/vehicle_config.json` にも反映してください。

### エンコーダを読む

まず対象輪のカウントを0にして、手で1回転させてカウントを読みます。

```powershell
@'
import json
import serial
import time

port = "COM7"
wheel = 0

def send(ser, msg, wait=0.15):
    ser.write((json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8"))
    until = time.time() + wait
    while time.time() < until:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").strip())

with serial.Serial(port, 115200, timeout=0.05) as ser:
    time.sleep(2.0)
    send(ser, {"v": 1, "type": "arm", "mode": "debug"})
    send(ser, {"v": 1, "type": "debug", "action": "encoder_zero", "wheel": wheel})
    print("Rotate the wheel by exactly one wheel revolution now.")
    until = time.time() + 10.0
    while time.time() < until:
        line = ser.readline()
        if line:
            text = line.decode(errors="replace").strip()
            if '"type":"telemetry"' in text:
                print(text)
    send(ser, {"v": 1, "type": "disarm"})
'@ | python -
```

確認すること:

- `encoder_count` の該当要素が変化するか。
- 違う要素が変わるなら `encoders[].physical` が違う。
- 正転でマイナスになるなら `encoders[].inverted` を切り替える。
- 1回転の絶対値を3回以上測り、中央値または平均を `encoders[].counts_per_wheel_rev` に書く。

`counts_per_wheel_rev` はエンコーダ単体のPPRではなく、実際の車輪1回転あたりにESP32が数えたカウントです。ギヤ比や4逓倍読み取りを含んだ実測値を使います。

## `vehicle_config.json` を埋める

初期値ではNORMAL ARMできません。以下が0またはfalseのままだと、通常走行は拒否されます。

```json
{
  "pid_enabled": false,
  "motion": {
    "wheelbase_m": 0.327,
    "track_width_m": 0.327,
    "wheel_diameter_m": 0.055,
    "max_wheel_rpm": 520.0,
    "max_linear_speed_mps": 1.5,
    "max_angular_speed_radps": 4.0,
    "pid_max_target_rpm": 80.0,
    "pid_pivot_max_target_rpm": 60.0,
    "open_loop_max_pwm": 120
  }
}
```

値の意味:

| 項目 | 意味 | NORMAL ARMに必要 |
| --- | --- | --- |
| `motion.wheelbase_m` | 前後輪中心間距離 m | 必要 |
| `motion.track_width_m` | 左右輪中心間距離 m | 必要 |
| `motion.wheel_diameter_m` | 車輪直径 m | 必要 |
| `motion.max_wheel_rpm` | 安全に許可する最大車輪RPM | 必要 |
| `motion.max_linear_speed_mps` | PC側で使う並進速度上限の目安 | 推奨 |
| `motion.max_angular_speed_radps` | PC側で使う旋回速度上限の目安 | 推奨 |
| `motion.pid_max_target_rpm` | PID有効時にPCから送る通常RPM目標の上限 | PID使用時に推奨 |
| `motion.pid_pivot_max_target_rpm` | PID有効時に純旋回だけへ使うRPM目標上限 | PID使用時に推奨 |
| `motion.open_loop_max_pwm` | PID無効時のスティック全倒しPWM。通常前進/横移動の実効速度調整はここを変える | 推奨 |
| `pid_enabled` | drive_targetをPWMではなくRPMとして扱うか | 最初はfalse推奨 |

モータ設定:

| 項目 | 使い方 |
| --- | --- |
| `motors[].physical` | 論理輪FL/FR/RL/RRを物理M1/M2/M3/M4へ割り当てる |
| `motors[].inverted` | 正転方向が逆ならtrue |
| `motors[].kp/ki/kd` | PID有効時だけ使う。現在の実測調整値は `kp=1.0`, `ki=1.2`, `kd=0` |
| `motors[].counts_per_wheel_rev` | 古い互換用。基本は `encoders[]` 側にも同じ値を書く |

エンコーダ設定:

| 項目 | 使い方 |
| --- | --- |
| `encoders[].physical` | 論理輪を物理ENC1/ENC2/ENC3/ENC4へ割り当てる |
| `encoders[].inverted` | 正転時のカウント/RPMがマイナスならtrue |
| `encoders[].counts_per_wheel_rev` | 車輪1回転あたりの実測カウント |

サーボ設定:

| 項目 | 使い方 |
| --- | --- |
| `servos[].channel` | PCA9685のch番号 |
| `servos[].center_us` | 車輪が車体前方を向くパルス幅 |
| `servos[].min_us/max_us` | 機械的に当たらない安全なパルス範囲 |
| `servos[].min_angle_deg/max_angle_deg` | 使ってよい角度範囲 |
| `servos[].trim_deg` | 角度指令に加える微調整 |
| `servos[].direction_inverted` | 角度方向が逆ならtrue |
| `servos[].calibrated` | 実機確認が終わったらtrue |

設定を編集したら、PC側からESP32へ送ってNVSに保存します。

```powershell
python -m pc_controller.main --port COM7 --once
```

このコマンドは `config/vehicle_config.json` と `config/controller_mapping.json` を作成または読み込み、ESP32へ `config` を送ります。終了時に `disarm` も送ります。走行はしません。

## NORMALで低速走行テストする

NORMAL ARMに必要な条件:

- PCA9685が見つかる。
- `wheelbase_m`, `track_width_m`, `wheel_diameter_m`, `max_wheel_rpm` が0より大きい。
- 4個すべての `servos[].calibrated` が `true`。
- `pid_enabled=true` の場合、4輪すべての `counts_per_wheel_rev` が0より大きい。
- `arm` の後、500ms以内に有効な `drive` を送り続ける。

最初は `pid_enabled=false` のPWM制御で、低いPWMだけを試してください。次の例は2秒間だけ全輪を前向き、低PWMで回し、その後DISARMします。

```powershell
@'
import json
import serial
import time
from pathlib import Path

port = "COM7"
config_path = Path("config/vehicle_config.json")

with config_path.open("r", encoding="utf-8") as handle:
    config = json.load(handle)

def send(ser, msg, wait=0.08):
    ser.write((json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8"))
    until = time.time() + wait
    while time.time() < until:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").strip())

with serial.Serial(port, 115200, timeout=0.03) as ser:
    time.sleep(2.0)
    send(ser, {"v": 1, "type": "hello", "client": "manual"})
    send(ser, config, wait=0.2)
    send(ser, {"v": 1, "type": "arm", "mode": "normal"}, wait=0.2)

    seq = int(time.time() * 1000) % 4000000000
    start = time.time()
    while time.time() - start < 2.0:
        seq += 1
        send(
            ser,
            {
                "v": 1,
                "type": "drive",
                "seq": seq,
                "armed": True,
                "control": "pwm",
                "steer_deg": [0.0, 0.0, 0.0, 0.0],
                "drive_target": [80, 80, 80, 80],
            },
            wait=0.05,
        )

    send(ser, {"v": 1, "type": "disarm"}, wait=0.2)
'@ | python -
```

期待する動作:

- `arm_ack` が `ok:true`, `state:"NORMAL"` になる。
- 4輪が前方0度へ向き、低出力で同じ方向へ回る。
- 2秒後にDISARMする。

`arm_ack` が `ok:false` の場合は、同じ行の `reason` を見ます。多い原因は `vehicle dimensions required`, `servo calibration required`, `encoder counts required`, PCA9685未検出です。

斜行テストは、直進の確認が終わってから行います。純粋な斜行では4輪を同じ角度に向け、同じ出力にします。

```json
{
  "steer_deg": [45.0, 45.0, 45.0, 45.0],
  "drive_target": [80, 80, 80, 80]
}
```

いきなり地面に置いて試さず、まず車輪を浮かせてサーボの向き、回転方向、左右前後の対応を見てください。

## 斜行とステアリング移行

このソフトでは、斜行を「車体の向きを変えず、4輪を同じ走行方向へ向けて平行移動する動作」と扱います。

純粋な斜行の基本条件:

- 4輪の目標ステア角が同じ。
- 4輪の車輪速度が同じ。
- `omega` は0。
- 車体姿勢は変えない。

PC側運動学は次の式で各輪の速度ベクトルを作ります。

```text
wheel_vx = vx - omega * y_i
wheel_vy = vy + omega * x_i
target_angle = atan2(wheel_vy, wheel_vx)
target_speed = sqrt(wheel_vx^2 + wheel_vy^2)
```

270度サーボでは、同じ車輪速度ベクトルを次の2通りで実現できます。

```text
候補A: servo = theta,       motor = +speed
候補B: servo = theta +/-180, motor = -speed
```

`pc_controller/steering_optimizer.py` は、サーボ可動範囲に入る候補だけを残し、現在角度からの移動量が小さい候補を選びます。純粋な斜行では4輪でできるだけ同じ候補を使い、正転/逆転が細かく切り替わらないようにします。

大きな角度変更が必要な場合は、走りながら無理に回さず、`DECELERATE -> ALIGN -> SETTLE -> ACCELERATE` のような移行を想定しています。現在の安全実装では、未校正サーボや範囲外指令はNORMAL走行へ進めません。

## 詳細仕様

ここからは、添付要件に含まれている実装仕様を、後で作業を再開しても追えるように整理したものです。すでに実装済みの内容、部品として存在するがメインループ未接続の内容、今後実装すべき内容を分けて読んでください。

### 実装対象

実装対象は2種類です。

| 対象 | 役割 | 現在の状態 |
| --- | --- | --- |
| Freenove ESP32 Dev用Arduinoファームウェア | モータ、エンコーダ、PCA9685、PID、安全状態、USB Serialを担当 | 実装済み、コンパイル確認済み |
| Windows PC用Pythonコントローラ | 設定管理、運動学、斜行角最適化、pygameジョイスティック入力、USB Serial 50Hz drive送信を担当 | 実装済み。GUIは最小表示用 |

ピン番号は推測で決めず、基板資料と `PINMAP_REPORT.md` を根拠にします。基板資料間で矛盾がある場合は、原則として `2026F^3_MCB44ver0.1` の明示的なピン定義、最新コード、変更履歴、ログの順で確認します。

### 車輪モジュール

車輪モジュールは4個あり、論理順は常に次です。

```text
0: FL = Front Left
1: FR = Front Right
2: RL = Rear Left
3: RR = Rear Right
```

各車輪モジュールは次の構成です。

| 部品 | 数量/輪 | 用途 |
| --- | ---: | --- |
| DCモータ | 1 | 推進 |
| AMT102-V系エンコーダ | 1 | 車輪回転方向、積算カウント、RPM |
| 270度サーボ | 1 | ステアリング角 |

### DCモータ制御

各DCモータは `DIR` と `PWM` の2信号で制御します。

| 項目 | 仕様 |
| --- | --- |
| 正転 | `DIR = HIGH` |
| 逆転 | `DIR = LOW` |
| 出力 | PWM dutyで制御 |
| 停止 | PWMを0にする |
| PWM周波数 | 20 kHz |
| PWM分解能 | 10 bit |
| PWM範囲 | `-1023` から `1023` |

安全上のルール:

- DIRを変える前にPWMを0へ落とす。
- 正転/逆転を急に切り替えない。
- SAFE遷移時は最初に全モータPWMを0にする。
- DEBUGモータテストは最大約10%出力に制限する。
- モータごとに `motors[].inverted` を持ち、配線やギヤの向き違いを設定で吸収する。

ESP32 Arduino Core 2系/3系でLEDC APIが異なるため、`motor_control.cpp` では使用中のCoreに合わせて `ledcAttachChannel` または `ledcSetup/ledcAttachPin` を使います。

### エンコーダ制御

エンコーダはAMT102-V系を前提にします。

| 項目 | 仕様 |
| --- | --- |
| 使用相 | A相/B相 |
| 未使用相 | Z相は現時点では未使用 |
| 取付位置 | 車輪軸 |
| 計測 | 4輪独立 |
| 用途 | 正逆判定、積算カウント、一定周期のRPM計算 |
| 電圧注意 | 5V出力時はESP32へ直結せずレベルシフタを入れる |

ソフトウェアではPPRという名前に依存せず、実測値 `counts_per_wheel_rev` を使います。これは「車輪を正確に1回転させたときにESP32が数えたカウント」です。エンコーダ本体のPPR、ギヤ比、A/B相の読み取り方式を含んだ最終値として扱います。

エンコーダ1回転測定の仕様:

1. 対象輪をFL/FR/RL/RRから選ぶ。
2. 対象エンコーダのカウントを0にする。
3. ユーザーが対象車輪を手で正確に1回転させる。
4. 絶対カウントを表示する。
5. 同じ測定を複数回行う。
6. 中央値または平均値を候補として表示する。
7. ユーザー確認後、`counts_per_wheel_rev` として保存する。
8. PC側JSONとESP32側NVSの両方へ保存する。

現在のファームウェアは、ESP32の `driver/pcnt.h` を使うPCNTハードウェアカウンタでA/B相を読みます。PCNTが無い、または初期化できない環境ではNORMAL ARMを拒否します。高速回転時にGPIO割り込みだけで4輪を読むと制御処理を圧迫し、ニュートラル後も前回モータ指令が残る原因になるため、通常走行ではPCNTを必須にしています。

### サーボ制御

ステアリングはPCA9685で4個の270度サーボを制御します。

| 項目 | 仕様 |
| --- | --- |
| サーボ数 | 4 |
| 制御IC | PCA9685 |
| I2C初期アドレス | `0x40` |
| I2Cピン | SDA=`GPIO21`, SCL=`GPIO22` |
| サーボPWM周波数 | 50 Hz |
| 標準角度範囲 | `-135 deg` から `+135 deg` |
| 0度 | 車体前方 |
| 正角度 | 車体上面から見て反時計回り |
| 負角度 | 車体上面から見て時計回り |

PCA9685についての注意:

- `0x00` は通常のPCA9685スレーブアドレスとして使いません。
- A0からA5が未設定なら通常は `0x40` です。
- 起動時にPCA9685応答を確認します。
- PCA9685が検出できない場合、NORMAL ARMを拒否します。

現在の採用ch:

| 論理輪 | 実車位置 | PCA9685 ch |
| --- | --- | ---: |
| `0=FL` | 左前 | 6 |
| `1=FR` | 右前 | 5 |
| `2=RL` | 左後 | 7 |
| `3=RR` | 右後 | 4 |

この割り当ては共有リンクで最終的に動いた配線に合わせています。違う輪のサーボが動く場合は、まず配線ラベルとこの表を照合し、それでも合わない時だけ `servos[].channel` を変更します。

各サーボは次の設定を持ちます。

| 項目 | 意味 |
| --- | --- |
| `channel` | PCA9685チャンネル |
| `center_us` | 0度、車体前方のパルス幅 |
| `min_us` | 機械的に安全な最小パルス幅 |
| `max_us` | 機械的に安全な最大パルス幅 |
| `min_angle_deg` | 使用を許可する最小角度 |
| `max_angle_deg` | 使用を許可する最大角度 |
| `trim_deg` | 中立ズレ補正 |
| `direction_inverted` | 角度方向の反転 |
| `calibrated` | 実機校正済みか |
| `max_rate_deg_per_sec` | サーボ角速度制限 |

未校正時の安全動作:

- `calibrated=false` のサーボはNORMAL走行では使わない。
- 未校正サーボを起動時に広い範囲へ自動移動させない。
- DEBUGでユーザーが明示した1個だけを `servo_us` で動かす。
- 最初は各輪の `center_us` 付近から始め、1us、5us、10us程度の小さい単位で確認する。
- ユーザーが中央、最小、最大を確認するまでNORMAL走行を許可しない。
- 校正済みサーボだけ、SAFE時に速度制限付きで中央へ戻す。

### PID速度制御

PID処理はESP32側で実行します。PID対象は各車輪の推進速度です。

| 状態 | PCから送る値 | ESP32側の動作 |
| --- | --- | --- |
| PID無効 | 符号付きPWM | PWMを制限して出力 |
| PID有効 | 目標RPM | エンコーダRPMを読み、PIDでPWMを計算 |

PID設定項目:

```text
pid_enabled
kp
ki
kd
integral_limit
output_min
output_max
counts_per_wheel_rev
```

現在のPID設定:

```text
pid_enabled = false
Kp = 1.0
Ki = 1.2
Kd = 0
integral_limit = 100
output_min = -140
output_max = 140
pid_max_target_rpm = 80
pid_pivot_max_target_rpm = 60
open_loop_max_pwm = 120
```

2026-08-10現在、実機ログでFL/RL系のエンコーダRPMが0付近へ落ちたり過大に跳ねたりする症状が残っているため、外注基板が届くまでPIDは封印します。
通常走行は `pid_enabled=false` のオープンループPWMで行い、PC側で `open_loop_max_pwm=120` を上限にします。

PID安全ルール:

- 未調整のPIDを自動的に有効化しない。
- 目標RPMが0、SAFE、PID無効化、通信断では積分値をリセットする。
- 出力飽和と積分飽和を実装する。
- 微小な目標付近で不要な正逆反転を繰り返さないようにする。
- 4輪一括設定と個別設定の両方を扱える構造にする。
- ただし初回実機試験ではPIDを使わず、PWM低出力で確認する。

2026-08-10のケーブル作り直し後、PWM100で4輪すべてのエンコーダ対応を確認しました。
その後PIDを試しましたが、エンコーダ計測が不安定な輪でPWMが上限へ張り付く挙動が出たため、通常走行設定ではPIDを無効にしています。
外注基板が届いてエンコーダ信号が安定してから、低い `pid_max_target_rpm` で再調整します。

制御周期:

| 処理 | 周期 |
| --- | ---: |
| ESP32制御更新 | 100 Hz |
| テレメトリ送信 | 20 Hz |
| PC側通常tick | 50 Hz |

### PC側の役割

PC側は次を担当します。

- コントローラ入力取得。
- デッドゾーン処理。
- 入力スケーリング。
- `vx`, `vy`, `omega` の生成。
- 4輪独立ステアリング運動学。
- 各輪の目標ステア角計算。
- 各輪の目標速度計算。
- 270度サーボ向けの最短候補選択。
- 設定JSONの保存。
- 起動時のESP32への設定送信。
- ARM/DISARM処理。
- 通信断検出。
- コントローラ切断検出。
- テレメトリ表示。
- DEBUG操作。
- サーボ校正。
- エンコーダ1回転測定。
- PID調整。

現時点で `controller_input.py` はpygame入力部品として存在しますが、`app.py` の実機走行ループにはまだ接続されていません。将来の実機操作画面では次のページまたはタブを用意する想定です。

```text
NORMAL
DEBUG
SERVO CALIBRATION
ENCODER CALIBRATION
PID TUNING
SETTINGS
```

GUIに最低限表示する項目:

- シリアル接続状態。
- 接続COMポート。
- ESP32応答状態。
- コントローラ接続状態。
- コントローラ名。
- 現在モード。
- ARM状態。
- `vx`, `vy`, `omega`。
- FL/FR/RL/RRの目標ステア角。
- FL/FR/RL/RRの推定サーボ角。
- 目標RPMまたはPWM。
- 実測RPM。
- 出力PWM。
- エンコーダ積算カウント。
- 通信指令経過時間。
- fault内容。
- PID有効/無効。
- Kp, Ki, Kd。
- `counts_per_wheel_rev`。
- サーボ校正状態。
- モータ、サーボ、エンコーダのマッピング。

危険な操作には確認手順または長押しを設けます。マウス操作とコントローラ操作の両方を使ってよいですが、通常走行のARMは明示的な操作に限定します。

### コントローラ設定

`config/controller_mapping.json` の初期設定:

| 項目 | 初期値 | 意味 |
| --- | --- | --- |
| `axis_vx` | `1` | 前後入力 |
| `axis_vy` | `0` | 左右入力 |
| `axis_omega` | `2` | 旋回入力 |
| `invert_vx` | `true` | 前後軸反転 |
| `invert_vy` | `false` | 左右軸反転 |
| `invert_omega` | `true` | 旋回軸反転 |
| `deadzone` | `0.12` | スティック中心デッドゾーン |
| `arm_buttons` | `[9, 10, 0]` | ARM用同時押し |
| `arm_hold_seconds` | `1.0` | ARM長押し時間 |
| `safe_button` | `6` | SAFE/DISARM |
| `mode_button` | `8` | モード切替 |
| `debug_select_buttons` | `[13, 14]` | DEBUG対象選択 |
| `debug_execute_button` | `1` | DEBUG実行 |

この割り当てはpygame上のボタン番号です。ゲームパッドによって番号が変わるため、実機操作前にpygameでボタン番号を確認してください。

### 起動シーケンス

ESP32起動時:

1. 全モータ出力を安全状態にする。
2. SAFE状態へ遷移する。
3. NVSから前回設定を読み込む。
4. モータピンを初期化する。
5. エンコーダを初期化する。
6. I2CとPCA9685を確認する。
7. USB Serialを開始する。
8. PCからの `hello` を待つ。
9. PCから `config` を受信する。
10. 設定を検証する。
11. 有効な設定をNVSへ保存する。
12. `config_ack` を返す。
13. SAFEのまま明示的なARM操作を待つ。

PC起動時の最終仕様:

1. JSON設定を読み込む。
2. pygameを初期化する。
3. コントローラを検出する。
4. シリアルポートを検出またはユーザー指定で開く。
5. `hello` を送る。
6. `hello_ack` を確認する。
7. `config` を送る。
8. `config_ack` を確認する。
9. SAFE状態を表示する。
10. ユーザーの明示的なARM操作を待つ。

設定送信完了だけでは走行を開始しません。

### 設定保存

設定は2か所に保存します。

| 保存先 | ファイル/機能 | 用途 |
| --- | --- | --- |
| PC | `config/vehicle_config.json` | 編集元、実質的なマスター設定 |
| PC | `config/controller_mapping.json` | コントローラ割り当て |
| ESP32 | Preferences/NVS | 起動後に保持する直近の車体設定 |

設定には `schema_version` と `config_revision` を持たせます。PCから新しい有効設定が送信された場合、ESP32は検証後にNVSへ保存します。古い形式や不正な形式は適用せず、理由を `config_ack` または `fault` で返します。

重要: ESP32側NVSに保存しても、次回PCから古い `vehicle_config.json` を送るとESP32側設定は上書きされます。実機校正結果は必ずPC側JSONにも反映してください。

### 斜行角度の定義

斜行方向はPC側で次のように求めます。

```text
translation_magnitude = sqrt(vx^2 + vy^2)
translation_angle = atan2(vy, vx)
```

角度基準:

| 角度 | 意味 |
| ---: | --- |
| `0 deg` | 前進 |
| `+45 deg` | 左前方向への斜行 |
| `+90 deg` | 真左への横移動 |
| `+135 deg` | 左後方向への斜行 |
| `+/-180 deg` | 後退 |
| `-135 deg` | 右後方向への斜行 |
| `-90 deg` | 真右への横移動 |
| `-45 deg` | 右前方向への斜行 |

スティック中心付近ではノイズで斜行角が大きく暴れるため、次の条件では新しい斜行角を計算しません。

```text
translation_magnitude < translation_deadzone
```

このとき:

- 車輪速度指令を0にする。
- サーボは最後に有効だった角度を保持する。
- SAFEへ遷移した場合だけ校正済みサーボを中央へ戻す。

初期値:

```text
translation_deadzone = 0.12
```

`translation_deadzone` が1.0以下の場合は、m/sの絶対値ではなくスティック全倒し前進に対する比率として扱います。現在の `linear_scale=0.12` では、実効しきい値は `max_linear_speed_mps * linear_scale * translation_deadzone` なので約 `0.0216 m/s` です。これにより、低速で前進しながら右スティックを入れても、超信地旋回へ誤判定されずMIX旋回として残ります。絶対m/sで指定したい場合は `translation_deadzone_mps` を追加します。

### 270度サーボ候補選択

同じ車輪速度ベクトルは2通りで表せます。

```text
候補A:
  サーボ角度 = target_angle
  モータ速度 = +target_speed

候補B:
  サーボ角度 = target_angle +/- 180 deg
  モータ速度 = -target_speed
```

例: 目標移動方向が `+150 deg` でサーボ可動範囲が `-135 deg` から `+135 deg` の場合、`+150 deg` は直接指令できません。その代わり `-30 deg` に向け、モータを逆回転させることで同じ地面基準の速度ベクトルを実現します。

候補選択ルール:

1. 元の目標角候補を作る。
2. 360度の整数倍を加減した候補を作る。
3. 180度反転したモータ逆転候補を作る。
4. サーボ校正済み可動範囲に入る候補だけ残す。
5. 現在角度からの移動量が小さい候補を優先する。
6. 可動端に近すぎる候補へペナルティを加える。
7. モータ回転方向の切り替えにもペナルティを加える。

純粋な斜行では、4輪がそれぞれ勝手に候補を選ぶのではなく、まず4輪で共通の表現を試します。

```text
共通候補A:
  4輪サーボ角度 = translation_angle
  4輪モータ速度符号 = 正

共通候補B:
  4輪サーボ角度 = translation_angle +/- 180 deg
  4輪モータ速度符号 = 負
```

両方が使える場合は次のコストが小さい候補を選びます。

```text
group_cost =
    4輪の角度移動量の合計
    + 最大角度移動量への重み
    + モータ回転方向変更ペナルティ
    + サーボ可動端接近ペナルティ
```

4輪共通候補が成立しない場合だけ、個別候補を使います。その場合でも、各車輪が作る地面基準の速度ベクトルは同一になるようにします。

初期値:

```text
candidate_switch_hysteresis_deg = 20
servo_end_margin_deg = 10
```

`candidate_switch_hysteresis_deg` は、候補が境界付近で頻繁に切り替わることを防ぐための値です。新候補による角度移動量の改善が20度未満なら、現在候補を維持します。

`servo_end_margin_deg` は、可動端から10度以内に入る候補へペナルティを加えるための値です。別の等価候補があるなら、可動端から遠い候補を優先します。

### 斜行移行ステートマシン

通常走行から斜行へ移行するとき、サーボ角を走行中に無理に大きく変えると横滑りや機械負荷が出ます。最終仕様では次の状態を持ちます。

```text
DRIVE
DECELERATE
ALIGN
SETTLE
ACCELERATE
BLOCKED
```

| 状態 | 内容 |
| --- | --- |
| DRIVE | 通常走行。現在角度と新しい目標角の差を監視する |
| DECELERATE | 全輪速度を現在値から0へ減速する |
| ALIGN | モータ停止のままサーボを目標斜行角へ動かす |
| SETTLE | 4輪が許容角度内に入った状態を一定時間確認する |
| ACCELERATE | 全輪速度を0から目標値へ増加させる |
| BLOCKED | 有効な候補がない、または整列タイムアウトした状態 |

DRIVEからDECELERATEへ入る条件:

```text
steering_error_deg >= realign_threshold_deg
```

または次の場合です。

- モータ回転方向を切り替える必要がある。
- ステアリング候補表現を切り替える必要がある。
- サーボ可動端を避ける必要がある。
- 現在速度のままでは横滑りが大きい。
- 4輪の目標角が大きく変化した。

初期値:

```text
realign_threshold_deg = 30
decel_time_ms = 200
accel_time_ms = 200
alignment_servo_rate_deg_per_sec = 180
alignment_tolerance_deg = 5
alignment_settle_time_ms = 100
alignment_timeout_ms = 2000
```

DECELERATE:

- 急停止ではなく設定時間で0へ近づける。
- 4輪の速度比をできる限り維持する。
- PWMまたは目標RPMが0付近になったらブレーキ停止する。
- DIR変更が必要な場合は、PWMが0になってから変える。

ALIGN:

- 全DCモータは停止したまま。
- サーボだけを目標角へ動かす。
- 4輪同時に動かしてよい。
- サーボ可動範囲外には動かさない。

SETTLE:

```text
abs(target_angle - commanded_or_estimated_angle)
    <= alignment_tolerance_deg
```

4輪すべてが5度以内に100ms連続で入った場合だけACCELERATEへ進みます。サーボ実位置フィードバックがない場合は、現在の推定角度、目標角度、角速度制限、送信した指令値、安全余裕時間から到達を推定します。

ACCELERATE:

- 急加速を避ける。
- 4輪の速度比を維持する。
- 目標角が再び大きく変わった場合はDECELERATEへ戻す。
- 目標速度到達後にDRIVEへ戻る。

BLOCKED:

- 全モータを停止する。
- 走行出力を禁止する。
- GUIへ対象輪と理由を表示する。
- 無理にサーボ可動端へ押し付けない。
- 重大な設定異常や通信異常の場合はBLOCKEDではなくSAFEへ遷移する。

現状の実装状態:

| 項目 | 状態 |
| --- | --- |
| 候補生成と可動範囲チェック | `steering_optimizer.py` に実装済み |
| 純粋斜行の共通候補選択 | 実装済み |
| `candidate_switch_hysteresis_deg` | 実装済み |
| `servo_end_margin_deg` | 設定値として存在、一部仕様扱い |
| DECELERATE/ALIGN/SETTLE/ACCELERATEの状態保持 | 未実装 |
| BLOCKEDのGUI表示 | 未実装 |

### 小さな角度変更の扱い

目標角変化が `realign_threshold_deg` 未満なら、完全停止せずに走行しながら追従してよいです。ただしステアリング誤差に応じて速度を制限します。

初期ルール:

```text
誤差 0..8 deg:
  速度倍率 1.0

誤差 8..30 deg:
  誤差に応じて速度倍率を1.0から0.2まで線形に下げる

誤差 30 deg以上:
  速度倍率 0
  DECELERATEまたはALIGNへ遷移
```

4輪独立に速度倍率を掛けると車体の走行ベクトルが崩れる可能性があります。純粋な斜行中は4輪のうち最も小さい速度倍率を全輪へ適用し、4輪の速度比を維持します。

### 斜行中の方向変更

斜行中にスティック方向がゆっくり変化した場合:

- 目標角変化が小さい場合は連続追従する。
- 目標角変化が大きい場合はDECELERATEへ入る。
- サーボ候補の180度反転が必要な場合もDECELERATEへ入る。
- 方向反転前にモータを停止する。
- サーボ整列後に新しい速度方向で再加速する。

スティックを急に左斜行から右斜行へ切り替えた場合、走行しながらサーボを高速反転させてはいけません。必ず減速、ブレーキ停止、サーボ角変更、必要なDIR変更、整列確認、再加速の順にします。

### 斜行指令のキャンセル

DECELERATE、ALIGN、SETTLE中にスティックがニュートラルへ戻った場合:

- 全モータは停止を維持する。
- 進行中の斜行開始をキャンセルする。
- サーボを自動的に中央へ戻さない。
- サーボはその時点の角度、または最後の有効角度を保持する。
- 次の有効な走行指令を待つ。

SAFE操作が行われた場合だけ、校正済みサーボを中央へ戻します。

### 斜行と旋回の同時入力

`omega` がほぼ0の場合は純粋な斜行として扱い、4輪共通候補選択と同期整列を使います。

```text
abs(omega) < 0.05 rad/s:
  純粋な斜行または平行移動

abs(omega) >= 0.05 rad/s:
  移動と旋回の合成
```

移動と旋回の合成では各輪の目標角が異なるため、各輪ごとに等価角度候補を選びます。ただし、いずれかの車輪で30度以上の再整列が必要な場合は、安全性と走行精度を優先し、初期実装では4輪すべてを停止してから再整列します。

将来的に実機試験で安全性を確認した後、各輪独立の速度制限へ変更できます。

### 斜行制御テレメトリ

斜行制御については、最終的に次の内部値をGUIへ出せるようにします。

```text
translation_angle
translation_magnitude
selected_steering_representation
steering_error_deg[4]
steering_speed_scale
transition_state
alignment_elapsed_ms
alignment_complete[4]
candidate_switched[4]
drive_direction_reversed[4]
```

DECELERATE、ALIGN、SETTLE中は、「故障による停止」ではなく「斜行方向への整列中」であることが分かる表示にします。

### プロトコル検証

ESP32は次を拒否します。

- 不正JSON。
- `v` または `type` がないメッセージ。
- 未知の `type`。
- 配列長が4ではない `drive`。
- NaN、Infinityなどの非有限値。
- 古い `drive.seq`。
- DEBUG ARMしていない状態のDEBUGコマンド。
- NORMAL ARM条件を満たしていないARM要求。

古い `seq` を拒否する理由は、遅延した古い走行指令を誤適用しないためです。

### 自動テスト観点

Python側テストで最低限確認する観点:

運動学:

- 前進時に4輪が前向きかつ同速度になる。
- 後退時に適切な角度または速度反転になる。
- 左右移動時に4輪が横向きになる。
- 純粋旋回時に各輪が車体中心への接線方向を向く。
- 移動と旋回の合成が正しい。
- 最大速度超過時に速度比を維持したまま正規化される。
- ゼロ入力時に角度が不要に暴れない。

ステアリング最適化:

- 目標角と180度反転候補を比較できる。
- サーボ可動範囲内の候補を選べる。
- 現在角度から最短の候補を選べる。
- 速度符号が正しく反転する。
- 候補がない場合は速度0とfaultになる。
- 純粋斜行で4輪共通候補を優先する。

プロトコル:

- 正常NDJSONを解析できる。
- 不正JSONを拒否できる。
- 配列長異常を拒否できる。
- NaN/Infinityを拒否できる。
- 古い `seq` を拒否できる。
- configの範囲検査が動く。

安全処理:

- 起動直後はSAFE。
- config受信だけではARMしない。
- 300ms通信断でモータ停止。
- 500ms通信断でDISARM。
- コントローラ切断でSAFE。
- 再接続しても自動ARMしない。

設定:

- JSON保存と読み込み。
- スキーマバージョン不一致時の処理。
- 不正設定時の安全なフォールバック。
- 論理から物理へのマッピング重複検出。

斜行制御の追加テスト候補:

1. 前進から左前45度斜行へ移行する。
2. 前進から真横90度移動へ移行する。
3. 前進から左後135度斜行へ移行する。
4. `+135 deg` を超える目標で、180度反転候補とモータ逆転が選ばれる。
5. `-135 deg` を下回る目標で、180度反転候補とモータ逆転が選ばれる。
6. 左斜行から右斜行へ急操作した場合、先にモータが停止する。
7. モータ停止前にDIRが変更されない。
8. 4輪整列前に駆動が開始されない。
9. 角度誤差が大きい場合に速度が0になる。
10. 小さな角度変化では停止せず速度制限付きで追従する。
11. スティック中心付近で角度が暴れない。
12. 候補境界付近で正転と逆転が頻繁に切り替わらない。
13. ALIGN中に指令角度が変わった場合に最新目標へ更新される。
14. ALIGN中に入力がキャンセルされた場合にモータ停止を維持する。
15. 整列タイムアウト時にBLOCKEDまたはSAFEへ遷移する。
16. 純粋斜行で4輪の地面基準速度ベクトルが一致する。
17. サーボ可動端を超える指令が生成されない。

### 初回実機試験の制限値

初回試験は車輪を浮かせた状態だけを想定します。

| 項目 | 初期制限 |
| --- | --- |
| DEBUG最大PWM | 最大出力の約10% |
| モータ単発テスト | ボタンを押している間だけ、推奨1秒以内 |
| サーボ角度変更 | 低速、小刻み |
| 同時動作対象 | 原則1個 |
| NORMAL最大速度 | 設定完了まで低く制限 |

設定が完了するまで全出力を許可しないでください。

### 完成条件

この制御ソフトの完成条件は次です。

- ESP32ファームウェア一式が存在する。
- PC用Pythonプログラム一式が存在する。
- ピン配置がローカル資料から反映されている。
- `PINMAP_REPORT.md` が存在する。
- 通常走行モードが実装されている。
- SAFEモードが実装されている。
- DEBUGモードが実装されている。
- サーボ校正が実装されている。
- エンコーダ1回転測定が実装されている。
- PID有効/無効切替が実装されている。
- PC JSON保存が実装されている。
- ESP32 NVS保存が実装されている。
- USB NDJSON通信が実装されている。
- 通信断安全処理が実装されている。
- pygame画面が存在する。
- PS4系コントローラ入力が実装されている。
- シミュレーションモードが動く。
- Pythonテストが通る。
- READMEに操作手順が書かれている。

現時点では上記の一部、特に完成版GUIと外部非常停止入力の実ピン割り当てが未完です。実機ジョイスティック走行ループと斜行移行ステートマシンの基本経路は実装済みです。

## USB Serial NDJSONプロトコル

通信は `115200 bps`, UTF-8, 1 JSON 1行です。すべてのメッセージに `v:1` と `type` を入れます。

PCからESP32:

```json
{"v":1,"type":"hello","client":"pc_controller"}
{"v":1,"type":"arm","mode":"normal"}
{"v":1,"type":"arm","mode":"debug"}
{"v":1,"type":"disarm"}
{"v":1,"type":"ping","seq":1}
```

PWM走行:

```json
{
  "v": 1,
  "type": "drive",
  "seq": 100,
  "armed": true,
  "control": "pwm",
  "steer_deg": [0.0, 0.0, 0.0, 0.0],
  "drive_target": [80, 80, 80, 80]
}
```

RPM走行:

```json
{
  "v": 1,
  "type": "drive",
  "seq": 101,
  "armed": true,
  "control": "rpm",
  "steer_deg": [45.0, 45.0, 45.0, 45.0],
  "drive_target": [30.0, 30.0, 30.0, 30.0]
}
```

DEBUG:

```json
{"v":1,"type":"debug","action":"motor_test","wheel":0,"pwm":80,"direction":true}
{"v":1,"type":"debug","action":"motor_stop","wheel":0}
{"v":1,"type":"debug","action":"encoder_zero","wheel":0}
{"v":1,"type":"debug","action":"servo_us","wheel":0,"pulse_us":1490}
{"v":1,"type":"debug","action":"servo_deg","wheel":0,"value":5.0}
{"v":1,"type":"debug","action":"servo_calibrated","wheel":0,"commit":true}
{"v":1,"type":"debug","action":"counts_commit","wheel":0,"value":8192,"commit":true}
```

ESP32からPC:

```json
{
  "v": 1,
  "type": "telemetry",
  "seq": 10,
  "state": "SAFE",
  "armed": false,
  "encoder_count": [0, 0, 0, 0],
  "wheel_rpm": [0.0, 0.0, 0.0, 0.0],
  "motor_pwm": [0, 0, 0, 0],
  "servo_deg": [0.0, 0.0, 0.0, 0.0],
  "fault_flags": 0,
  "command_age_ms": 0
}
```

## SAFE, DEBUG, NORMAL

| 状態 | 目的 | モータ | サーボ |
| --- | --- | --- | --- |
| SAFE | 初期状態、異常時、DISARM後 | 0 | 校正済みのみ中央へ戻す |
| DEBUG | 単体確認 | 低出力の短時間確認だけ | `servo_us` で未校正サーボも単体確認可能 |
| NORMAL | 通常走行 | drive指令を継続受信したときだけ | 校正済みサーボのみ |

通信断の挙動:

| 最後の有効指令から | 動作 |
| ---: | --- |
| 200ms | PC側で警告扱い |
| 300ms | モータPWM 0 |
| 500ms | DISARM + SAFE |

そのため、NORMAL走行では `drive` を50ms程度ごとに送り続けます。1回だけ `drive` を送って放置すると、すぐSAFEへ落ちます。

## PIDを使う場合

最初は `pid_enabled=false` のPWM制御で、配線、回転方向、サーボ向き、エンコーダ方向を確認してください。

PIDを有効にする前提:

- 4輪すべての `counts_per_wheel_rev` が実測済み。
- 正転時の `wheel_rpm` が正になるよう `encoders[].inverted` を調整済み。
- PWM低出力でモータ方向が正しい。
- `kp`, `ki`, `kd` は小さい値から始める。

推奨順:

1. `pid_enabled=false` で全輪の方向を確認する。
2. エンコーダ1回転カウントを入れる。
3. `pid_enabled=true` にする前に、1輪ずつ低RPMで試す。
4. `kp` を少しずつ上げる。
5. 振動や急反転が出たらすぐDISARMし、PWM制御へ戻す。
6. `ki` は最後に少量だけ入れる。

## よくあるエラー

### `ValueError: wheelbase_m and track_width_m must be set`

`config/vehicle_config.json` の車体寸法が0のままです。実機NORMAL走行前に、少なくとも次を0より大きい値にしてください。

- `motion.wheelbase_m`
- `motion.track_width_m`
- `motion.wheel_diameter_m`
- `motion.max_wheel_rpm`

なお、`.\run-pc-controller.cmd --port COM7` だけでは現在は実機走行しません。ゲームパッドが見えていてARM操作をした場合だけ走行指令が出ます。設定保存と通信確認だけなら `--once` を付けます。

### 仮想環境コマンドでメモ帳が出る

`.ps1` をダブルクリックすると、実行ではなくメモ帳などで開くことがあります。PowerShellスクリプトはダブルクリックせず、PowerShellにコマンドとして入力します。

ただし、このPCではプロジェクト内 `.venv` / `.venv_win` が日本語パス文字化けで壊れていたため、通常は仮想環境を有効化せず次を使います。

```powershell
.\run-pc-controller.cmd --list-controllers
```

### COMポートが開けない

- Arduino Serial Monitorを閉じる。
- 別のPythonプロセスを止める。
- USBを抜き差しする。
- `python` のポート一覧コマンドでCOM番号を確認する。
- ESP32の書き込み直後は数秒待つ。

### `ESP32 fault: flags=128 reason=bad json`

COMポートを開いた直後にESP32がリセット中で、PCから送ったJSONの先頭が欠けたときに出ることがあります。
現在のPC側コードは、シリアルを開いた後に1.5秒待ってからバッファをクリアし、その後で `hello` / `config` を送るようにしています。
このエラーが続く場合は、Arduino Serial Monitorや別ターミナルがCOM7を開いたままになっていないか確認し、必要なら次で残プロセスを止めてから再実行します。

```powershell
.\stop-pc-controller.cmd
.\run-pc-controller.cmd --port COM7 --once
```

### `pca9685_ok:false`

- SDA/SCLが `GPIO21/GPIO22` か確認する。
- PCA9685のVCC/GNDとESP32 GND共通を確認する。
- サーボ電源V+とPCA9685ロジック電源を混同していないか確認する。
- アドレスが `0x40` 以外なら `config/vehicle_config.json` の `pca9685_address` を変える。

### DEBUGで違う車輪が動く

`motors[].physical`, `encoders[].physical`, `servos[].channel` の対応を直します。論理順は必ず `0=FL`, `1=FR`, `2=RL`, `3=RR` です。

### 正転方向が逆

モータなら `motors[].inverted`、エンコーダなら `encoders[].inverted`、サーボ角なら `servos[].direction_inverted` を切り替えます。

### `stale drive seq`

ESP32は古い `drive.seq` を拒否します。手動スクリプトでは時刻ベースの大きい `seq` を使っています。手書きで小さい番号から再送した場合は、ESP32をリセットするか、前回より大きい `seq` にしてください。

## 検証

Pythonテスト:

```powershell
& "C:\robot_venvs\robot_project_kicad\Scripts\python.exe" -m pytest
```

この作業環境で確認した結果:

```text
40 passed
```

Arduinoコンパイル:

```powershell
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile --fqbn esp32:esp32:esp32 --build-path C:\tmp\arduino-build-4wis esp32_firmware
```

確認済み結果:

```text
Sketch uses 347043 bytes (26%)
Global variables use 26328 bytes (8%)
```

## 2026-08-09 実機確認メモ

COM7 の ESP32 で、修正ファームを書き込んだあとに次を確認しました。

- `hello_ack` が返り、`pca9685_ok: true`, `pca9685_address: 64` だった。
- `config/vehicle_config.json` の送信に対して `config_ack ok: true reason: stored` が返った。
- `arm normal` に対して `arm_ack ok: true state: NORMAL` が返った。
- その後、drive コマンドを送らない状態では約 500ms で `SAFE` に戻り、`motor_pwm` は `[0,0,0,0]` のままだった。

今回の「動かない」直接原因は、古い ESP32 ファームの受信バッファが `1536` byte しかなく、現在の設定JSONを受け取れず `fault: line too long` になっていたことです。現在のコードでは `esp32_firmware/serial_protocol.h` の `RX_BUFFER_SIZE` を `4096` にしています。

もし `.\run-pc-controller.cmd --port COM7 --once` のあとも ESP32 から `line too long` や `vehicle dimensions or max rpm unset` が返る場合は、古いファームが残っています。Arduino CLI のキャッシュを避けるため、次のようにクリーンビルドしてからアップロードしてください。

```powershell
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile --clean --fqbn esp32:esp32:esp32 esp32_firmware
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" upload -p COM7 --fqbn esp32:esp32:esp32 esp32_firmware
```

アップロード時は Arduino Serial Monitor、別の Python プロセス、別ターミナルなど、COM7 を開いているソフトを閉じてください。最初の確認ではモータ電源を切るか、車輪を浮かせた状態にしてください。

## 2026-08-10 PWM/DIRピン修正メモ

単体の `ESP32 standalone debug controller v29` スケッチを書き込むと実機が動いたため、そのスケッチを正としてプロジェクト版との差分を確認しました。根本原因は、プロジェクト版の `esp32_firmware/board_pins.h` で4モータすべてのPWMピンとDIRピンを逆に定義していたことです。

現在のプロジェクト版は、単体v29スケッチと同じ次の定義です。

| 物理モータ | PWM | DIR | 実機位置 |
| --- | --- | --- | --- |
| M1 | GPIO19 | GPIO14 | RR |
| M2 | GPIO27 | GPIO23 | FR |
| M3 | GPIO25 | GPIO26 | FL |
| M4 | GPIO18 | GPIO16 | RL |

修正後、COM7へプロジェクト版ファームを書き込み、DEBUG ARMで `PWM=120` を0.25秒ずつ1輪確認しました。テレメトリ上、4輪すべてでPWM出力とエンコーダカウント増加を確認済みです。最後は `disarm` で `motor_pwm=[0,0,0,0]`、`fault_flags=0` でした。

## 2026-08-10 コントローラ走行の開始手順

このプロジェクト版のコントローラ走行は、PCでゲームパッドを読み、USBシリアルでESP32へ `drive` を送る方式です。ESP32へ直接PS4/DS4をペアリングするBluepad32方式ではありません。

ESP32のCOM番号は自動発見できます。PC側が見えている各COMポートを開き、最初に `who_are_you` を送って、ESP32から返る自己紹介で基板と役割を判定します。

```powershell
.\run-pc-controller.cmd --list-nodes
```

複数ESP32構成をfail-closedで確認する場合は、確認済みnode manifestも指定します。

```powershell
.\run-pc-controller.cmd --list-nodes --node-manifest config\node_manifest.json
```

required nodeの欠落、同一`node_id`の重複、期待roleとの不一致、不完全identityがある場合は
`node inventory: BLOCKED`として終了します。optional nodeの欠落とmanifest外のnodeは警告ですが、
required nodeが正しければREADYを維持します。詳細は`docs/serial_node_inventory.md`を参照してください。

R1/R2 autonomyのhardware-independent state machineとFake Robot E2Eは次で確認できます。

```powershell
C:\robot_venvs\robot_project_kicad\Scripts\python.exe -m pc_controller.fake_autonomy_scenarios --config-dir config
```

これは実競技taskや実機autonomyを有効化するcommandではありません。状態遷移と
STOP/SKIP/FALLBACK/retry policyをFake ESP32経路だけで検証します。詳細は
`docs/autonomy_state_machine.md`を参照してください。

Fail-closedなCOMPETITION session、追記専用local log、POST_COMPETITION outboxは
Fake ESP32だけを使って次で検証できます。

```powershell
C:\robot_venvs\robot_project_kicad\Scripts\python.exe -m pc_controller.fake_competition_demo `
  --config-dir config `
  --output-dir 99_作業用\tmp\fake-competition `
  --session-id local-validation
```

COMPETITION enable、全robotの外部ARM確認、START確認はそれぞれ明示的に必要です。
この層はARMを送信しません。生成されるoutboxはlocal stagingのみで、remote転送は
宛先・認証・retention policyが決まるまで無効です。詳細は
`docs/competition_mode.md`を参照してください。

`role=drive` の基板が1台だけ見つかる状態なら、以降は `--port COM7` を付けずに起動できます。

```powershell
.\run-pc-controller.cmd --once
.\run-pc-controller.cmd
```

同じ `role=drive` が複数見つかる場合は、誤接続を避けるため自動選択せずに停止します。その場合は `--node-id mcb44_drive_main` か `--port COM7` を指定します。

通常の無期限実行では、起動時に対象nodeがまだ見えない、または明示portをまだopenできない場合も、
PC側を`SAFE`に保ったまま常駐して再試行します。接続後は`DISARM -> HELLO -> CONFIG`を再実行し、
`READY_DISARMED`で待機するためautomatic ARMは行いません。`--once`、`--duration`、
`--no-auto-reconnect`は初回接続失敗をエラーとして終了します。複数node一致は再試行対象にせず、
operatorが対象を明示するまで自動選択しません。詳細は`docs/serial_reconnect.md`を参照してください。

ESP32の自己紹介応答例:

```json
{"v":1,"type":"node_identity","node_id":"mcb44_drive_main","board":"MCB44","role":"drive","firmware":"mcb44_4wis","fw_version":"v29","protocol":"mcb44-json-serial"}
```

まずPCからゲームパッドが見えているか確認します。

```powershell
.\run-pc-controller.cmd --list-controllers
```

`controllers: 0` の場合、PC側のpygameからゲームパッドが見えていません。USB接続、Windows Bluetoothペアリング、Steam Inputなどが入力を横取りしていないかを確認してください。

初回走行では `config/controller_mapping.json` の次の値を低めにしてあります。

```json
"deadzone": 0.12,
"linear_scale": 0.12,
"angular_scale": 0.35
```

`deadzone` はv29で動いたプログラムと同じ0.12です。デッドゾーンの外側は、v29と同じ「線形55% + 3次45%」のカーブで整形します。

`linear_scale` は前進/横移動を内部の速度モデルへ入れる係数です。以前の実装ではこの値が小さいと `open_loop_max_pwm` を上げてもPWMが約123で止まっていましたが、現在のPWM走行では速度上限調整を `open_loop_max_pwm` に一本化し、`open_loop_max_pwm` がスティック全倒し時のPWMとして直接効きます。
`angular_scale` は右スティックだけの超信地旋回速度と、旧ベクトルMIX方式を使う場合の旋回速度に効きます。現在のMIX走行はv29相当の協調4WSへ戻しているため、前進しながら曲がる角度は主に `config/vehicle_config.json` の `coordinated_4ws_max_steer_deg` で決まります。
`translation_deadzone` は斜行/MIX判定の前進成分しきい値です。値が `0.12` のように1.0以下ならスティック比率として扱うため、低速前進中に右スティックを入れても超信地旋回へ落ちにくくなっています。

現在の走行制御はPIDではなくPWMです。

```json
"pid_enabled": false,
"open_loop_max_pwm": 120
```

速度を変えるときは、Arduinoへ再書き込みせずに `config/vehicle_config.json` の `open_loop_max_pwm` を変更してから `.\run-pc-controller.cmd` を起動し直します。例として `open_loop_max_pwm=200` なら全倒し前進の目標PWMは約200、`300` なら約300です。超信地旋回だけ別に弱く/強くしたい場合は `pivot_max_pwm` を変更します。

外注基板が届いてエンコーダ信号が安定するまでは、`pid_enabled=true` に戻さないでください。

ゲームパッドが見えたら、車輪を浮かせた状態で次を実行します。

```powershell
.\run-pc-controller.cmd
```

このコマンドは常駐するので、PowerShellの入力待ちプロンプトへ戻りません。次のような表示が出たあと、PS4/DS4入力を待ち続けるのが正常です。

```text
pc_controller started: serial auto-discovery
controller: PS4 Controller
waiting: hold L1 + R1 + X for about 1 second to ARM. OPTIONS sends SAFE. Stop with Ctrl+C.
```

終了するときは、そのPowerShellで `Ctrl+C` を押します。終了せずに別ターミナルからもう一度起動すると、対象COMが使用中になり `アクセスが拒否されました` と表示されます。

`Ctrl+C` が効かない場合は、別のPowerShellを開いて同じプロジェクトフォルダへ移動し、次を実行します。

```powershell
.\stop-pc-controller.cmd
```

このスクリプトは通常 `.codex_work\pc_controller.pid` に記録されたプロセスを止めます。PIDファイルが消えている場合も、ロボット用Python環境 `C:\robot_venvs\robot_project_kicad\Scripts\python.exe` の残プロセスを確認して停止します。

通常動作を短時間だけ確認したい場合は、停止操作に頼らず `--duration` を付けます。

```powershell
.\run-pc-controller.cmd --duration 10
```

3分程度だけコントローラ操作したい場合は、専用コマンドを使います。

```powershell
.\run-pc-controller-3min.cmd
```

自動発見できない場合だけ、引数でCOM番号を指定します。

```powershell
.\run-pc-controller-3min.cmd COM8
```

このコマンドは内部で次を実行します。

```powershell
.\run-pc-controller.cmd --duration 180 --rpm-monitor
```

3分経つと自動で停止し、終了処理でDISARMを送ります。途中で止める場合はコントローラの `OPTIONS` でSAFEにするか、別PowerShellから `.\stop-pc-controller.cmd` を実行します。
この3分用コマンドは、ダブルクリックで起動すると別のコマンドプロンプトを開きます。その画面は終了後も閉じずに残るため、エラーで止まった場合も `exit=` の数字と直前の表示を確認できます。
この3分用コマンドも内部で `run-pc-controller.cmd` を呼ぶため、同じように `logs\pc-controller-*.log` が作られます。途中でコマンドプロンプトが消えた場合も、最後のログを開けば `serial TX`、`serial RX`、`encoder_count`、`wheel_rpm`、`motor_pwm` を確認できます。

現在のDS4設定では `arm_buttons` が `[9, 10, 0]` なので、L1 + R1 + X相当を約1秒同時押しするとNORMAL ARMします。`safe_button` は `6`、つまりOPTIONSです。ボタン番号はゲームパッドやドライバで変わるため、反応しない場合は `config/controller_mapping.json` を実機のボタン番号に合わせます。

## 2026-08-10 DS4接続確認メモ

USB接続中のコントローラは `VID_054C&PID_09CC` として見えており、Sony DS4 v2系です。Sixaxis Pair Tool の `Current Master` が `30:76:f5:aa:85:5e` の場合、これは今回のESP32 Bluetooth address `30:76:F5:AA:85:5E` と一致しています。

ESP32直結で確認する場合は、モータを使わない次の接続専用スケッチを使います。

```text
02_ソフトウェア_ESP32/ESP32_PS4_Only/ESP32_PS4_Only.ino
```

このスケッチの `PS4_HOST_MAC` は現在 `30:76:f5:aa:85:5e` に更新済みです。シリアルに `PS4.begin OK` と `ESP32 Bluetooth address now = 30:76:F5:AA:85:5E` が出れば、ESP32側の待ち受けは成功しています。

`PS4=waiting` のままの場合、次を順番に確認します。

1. コントローラのUSBをPCから抜く。
2. WindowsのBluetooth設定で `Wireless Controller` が接続中なら切断または削除する。
3. コントローラ背面の小さいリセット穴を3秒ほど押す。
4. もう一度USBでPCへ接続し、Sixaxis Pair Toolで `Current Master` が `30:76:f5:aa:85:5e` であることを確認する。
5. USBを抜く。
6. ESP32の電源を入れた状態で、コントローラのPSボタンを1回押す。

PC側pygameで操作する場合は逆に、コントローラをESP32ではなくWindowsへ通常のゲームパッドとして接続する必要があります。Sixaxis Pair Toolやlibusb-win32ドライバが入っていると、Windowsには見えてもpygameでは `controllers: 0` になることがあります。その場合はDS4WindowsなどでXInput互換デバイスとして見える状態にするか、ESP32直結方式に統一してください。

今回のPC経由走行では、DS4 USB interface が `libusb-win32 devices` として掴まれていたため、pygame/SDLでは `controllers: 0` でした。管理者PowerShellで `oem162.inf` と `oem165.inf` をアンインストールし、Windows標準HIDへ戻したところ、次の状態になりました。

```text
.\run-pc-controller.cmd --list-controllers
controllers: 1
0: PS4 Controller axes=6 buttons=16 hats=0
```

DS4 v2 / SDL標準マッピングでは、右スティックXは `axis_omega=2`、ARMは `L1 + R1 + X = [9, 10, 0]`、SAFEは `OPTIONS = 6` として設定しています。現在の `config/controller_mapping.json` はこの設定です。

## 2026-08-10 超信地旋回のサーボ角修正

実機確認で、右スティック旋回だけのときに4輪サーボが意図しないX字へ見える問題がありました。
一度サーボ0度固定のタンク旋回へ寄せましたが、それでは超信地旋回中に全サーボが初期位置へ戻ってしまうため、v29で動いたPIVOT姿勢へ戻しています。

右スティック旋回だけのとき、PC側の目標は次になります。

```text
v29 PIVOT基本角: FL=-135, FR=+135, RL=-45, RR=+45
初期0度から入る場合の短い表現: FL=+45, FR=-45, RL=-45, RR=+45
旋回方向の反転: サーボ角は保持し、モーター符号だけ反転
```

これにより、超信地旋回中にサーボが全輪0度へ戻ることはありません。直進0度から右スティック旋回へ入ると、表示は `servo=[45.0, -45.0, -45.0, 45.0]` 付近になります。
前後・斜行・旋回を混ぜた入力では、v29で動いた協調4WSを使います。地面で試す前に必ず車輪を浮かせて確認してください。

## 2026-08-10 超信地旋回の加速抑制

純旋回でも通常のステアリング移行制御を通していたため、サーボ整列後に `ACCELERATE` 状態でPWMが0から目標値へ増える挙動がありました。
これが「ただの旋回なのに加速している」ように見える原因です。

現在は純旋回だけ、サーボ整列待ちは残したまま `ACCELERATE` の速度ランプを使わないようにしています。
また、純旋回PWMは通常走行とは別に `motion.pivot_max_pwm` で上限をかけます。現在値は次です。

```json
"pivot_max_pwm": 120
```

右スティック旋回だけの確認では、目安として `servo=[45.0, -45.0, -45.0, 45.0]`、`pwm=[120, -120, 120, -120]` 付近になります。

## 2026-08-10 前進+旋回時のRPM監視

前進しながら旋回するときは、現在はv29相当の協調4WSを使います。

```json
"mixed_steering_mode": "coordinated_4ws",
"coordinated_4ws_max_steer_deg": 45.0,
"coordinated_4ws_inner_outer_speed": true,
"coordinated_4ws_positive_steer_turns_right": true
```

協調4WSでは、左スティックの走行方向を `base`、右スティックXを `steer` として、サーボ目標を次のように作ります。

```text
FL = base + steer
FR = base + steer
RL = base - steer
RR = base - steer
```

直進しながら右スティックを最大まで倒すと、目標はおおよそ次になります。

```text
servo=[45.0, 45.0, -45.0, -45.0]
```

左スティックが斜めの場合は、斜行方向が `base` になり、そこへ前輪側は `+steer`、後輪側は `-steer` を足します。
また、サーボの可動範囲に合わせるため、通常表現と180度反転表現を4輪まとめて選びます。v29と同じ考え方で、各輪が勝手に別々の180度反転を選ばないため、MIX中に左右が不自然なX字へ割れるのを避けます。

速度は、内輪差・外輪差を入れます。
右スティック右を右旋回として扱うため、前進+右旋回では左側が外輪、右側が内輪です。外輪を直進時より加速させるのではなく、外輪を入力速度の上限として、内輪を旋回半径に応じて下げます。

前進しながら右スティック最大付近の場合、ログはおおよそ次の関係になります。

```text
servo=[45.0, 45.0, -45.0, -45.0]
pwm: FL/RL > FR/RR
rpm: FL/RL > FR/RR
```

左旋回では逆に `FR/RR > FL/RL` になります。
もし実機で左右が逆に見える場合は、`coordinated_4ws_positive_steer_turns_right` の前提が逆です。この値を `false` にすると、内外輪速度差の左右だけを反転できます。

現在のR2は`logical_front=REAR`、`mixed_steering_mode=limited_arc`、`mixed_omega_inverted=true`です。実機確認に合わせ、超信地旋回の符号はそのまま、並進中の旋回だけ符号を反転します。この構成では操縦者基準の右旋回時に旧論理名`FR/RR`が内輪、`FL/RL`が外輪になります。`open_loop_static_compensation_enabled=true`では、内輪指令を各輪の`ff_static_pwm_pos / neg`以上へ補償し、計算上は非ゼロでも実機では停止する状態を避けます。

旧ベクトルMIX方式に戻す場合だけ、次の設定が効きます。

```json
"limit_mixed_peak_to_translation": true
```

旧ベクトルMIX方式では、外側に相当する車輪のPWM/RPMが前進だけの時より高くなり、音が加速したように聞こえることがあります。この設定が有効な場合、前進+旋回では車輪間の速度差だけを作り、最大PWMは前進入力相当に制限します。
現在の `coordinated_4ws` では、曲がり方の基本は前後ステア角の差で作り、速度側には内外輪差を入れます。
ただし、スティック入力を一定にしているのに `avg` や `max` が上がり続ける場合は、制御またはPID/エンコーダ方向の問題です。

実測するときは次を使います。

```powershell
.\run-pc-controller.cmd --port COM7 --duration 30 --rpm-monitor
```

表示例:

```text
rpm: in(vx=+0.50 vy=+0.00 om=+0.30) wheel=[12.1, 18.4, 12.0, 18.2] avg=15.2 max=18.4 L/R=12.1/18.3 pwm=[...] servo=[...]
```

## 2026-08-10 特定エンコーダだけ読む

エンコーダ配線や接触不良を切り分けるときは、PC側の通常コントローラを止めてから、指定した1輪だけを表示します。
このコマンドはモータをARMしません。ESP32がUSBシリアルへ出しているテレメトリから、指定した論理輪だけを抜き出します。

```powershell
.\run-encoder-monitor.cmd --port COM7 --wheel FL --duration 20 --hz 10
.\run-encoder-monitor.cmd --port COM7 --wheel FR --duration 20 --hz 10
.\run-encoder-monitor.cmd --port COM7 --wheel RL --duration 20 --hz 10
.\run-encoder-monitor.cmd --port COM7 --wheel RR --duration 20 --hz 10
```

表示例:

```text
   1.245s RL count=    +829265 delta=   +792 rpm= +112.79 pwm=  +89 servo=  +0.00 state=NORMAL armed=1 fault=0
```

見る場所:

```text
count       現在のエンコーダカウント
delta       前回表示からのカウント増減
rpm         ESP32が計算した対象輪のRPM
pwm         対象輪へ実際に出ているPWM
state/armed ESP32の安全状態
fault       ESP32のfault_flags
```

手で対象車輪をゆっくり回して、`count` と `delta` が滑らかに変化するか確認します。
車輪を回しているのに `delta=0` が続く場合は、その輪のエンコーダ信号が読めていません。
何もしていないのに `delta` や `rpm` が大きく跳ねる場合は、A/B線、GND、電源、レベルシフタ、コネクタ接触を疑います。

出力は通常のコントローラとは別に、次の形式で必ずログへ残ります。

```text
logs\encoder-monitor-YYYYMMDD-HHMMSS-fff.log
```

生のシリアルTX/RXも一緒に見たい場合だけ、次のようにします。

```powershell
.\run-encoder-monitor.cmd --port COM7 --wheel RL --duration 20 --hz 10 --trace-serial
```

見るところ:

- `wheel=[FL, FR, RL, RR]` がエンコーダ実測RPM。
- `avg` が4輪平均RPM。スティック一定でここが増え続けるなら異常。
- `max` が一番速い車輪RPM。現在設定では、前進+旋回でも前進だけの最大値を大きく超えないのが正常。
- `L/R` は左側平均と右側平均。旋回時は左右差が出るのが正常。
- `pwm` はPCからESP32へ送った指令ではなく、ESP32側の実出力PWM。

## 現在の制限

- PC側メインアプリは、実機モードでpygameジョイスティック入力を走行ループへ接続済みです。`--once` は設定送信と通信確認だけで終了します。
- ジョイスティックを使わず通信確認だけ続ける場合は `--no-joystick` を付けます。
- `gui.py` は最小表示用です。実機操作UIとしてはまだ未完成です。
- サーボ実角度のフィードバックはありません。現在は指令角と速度制限から推定しています。
- 外部非常停止入力は `external_estop.*` のスタブです。実ピンへ接続する場合は、PC指令より優先してSAFEへ落ちるよう実装を確定してください。
- NORMAL実走行、PID調整、地面に置いた状態の斜行は未検証です。必ず浮かせた状態の低出力確認から進めてください。
