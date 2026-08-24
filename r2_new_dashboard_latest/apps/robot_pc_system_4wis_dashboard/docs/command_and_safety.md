# コマンドと安全レイヤー

## PC中心制御の考え方

このプロジェクトでは、PCアプリが高レベル制御を担当します。
UI、ログ、センサ統合、自己位置表示、将来の自律制御はPC側で扱います。

ESP32は低レベルI/O担当です。
モータドライバ出力、エンコーダ読み取り、将来のアームやツール制御、フェイルセーフ停止を担当します。

## コマンドの流れ

UIの走行ボタンを押すと、次の順番で処理されます。

```text
UIボタン
  -> robot_command.py で解析
  -> safety_layer.py で安全確認
  -> command_sender.py で送信
  -> command_history.py に履歴保存
  -> ESP32
```

## DRIVE VEL left right

`DRIVE VEL left right` は左右の走行速度を指定する指令です。

例:

```text
DRIVE VEL 100 100
DRIVE VEL 0 0
DRIVE VEL -80 80
DRIVE VEL 80 -80
```

- 左右が正の値: 前進
- 左右が0: 停止
- 左が負、右が正: 左旋回
- 左が正、右が負: 右旋回

## Safety Layerの役割

Safety LayerはESP32へ送信する前に指令を確認します。

主な役割:

- 左右速度を安全な上限内に制限する
- 緊急停止中の走行指令をブロックする
- 不正な指令を安全な停止指令に変換する
- 将来の指令タイムアウト検出に備える
- 日本語の安全理由を返す

表示される例:

```text
安全制限: 速度上限を超えたため制限しました
安全制限: 不正な指令のため停止指令に変換しました
安全制限: 緊急停止中のため指令を送信しません
```

## 緊急停止の流れ

`EMERGENCY_STOP` はSafety Layerを通ってESP32へ送られます。
送信後、Safety Layerは緊急停止中として扱い、通常の走行指令をブロックします。

停止指令 `DRIVE STOP` を通すと、緊急停止状態を解除するための構造にしています。
実機運用では、解除手順をチームで決めてから使ってください。

## 互換コマンド

既存の簡易指令も解析できます。

```text
FWD 100
STOP
TURN_L 80
TURN_R 80
```

内部では `DRIVE VEL` または `DRIVE STOP` に変換されます。

## 将来アーム / ツールへ拡張する方法

`robot_command.py` は次のカテゴリを想定しています。

- `DRIVE`
- `ARM`
- `TOOL`
- `SYSTEM`

将来は次のような指令を追加できます。

```text
ARM UP 50
ARM DOWN 50
ARM STOP
TOOL OPEN
TOOL CLOSE
TOOL PUMP_ON
TOOL PUMP_OFF
```

追加時は、まず `robot_command.py` で解析し、次に `safety_layer.py` で安全条件を決めます。
ESP32側の実装は `esp32/drive_controller/drive_controller.ino` または新しい専用コントローラに追加します。
