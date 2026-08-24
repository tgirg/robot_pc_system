# シミュレーション機能

## 目的
シミュレーション機能は、実機ESP32やモータを接続しない状態で、PC中心の走行指令、センサ表示、仮想フィールド上の動きを確認するための機能です。

## 動作の流れ
UIの走行ボタン、または自動走行コントローラから出た指令は、手動操作と同じ経路を通ります。

1. `robot_command` で指令を解釈します。
2. `safety_layer` で速度制限や緊急停止を確認します。
3. `command_sender` に送ります。
4. Simulationモードでは `robot_simulator` が仮想ロボットの位置を更新します。

## DRIVE VEL left right
`DRIVE VEL left right` は左右の車輪速度を表します。

```text
DRIVE VEL 100 100
DRIVE VEL -80 80
DRIVE VEL 80 -80
DRIVE STOP
EMERGENCY_STOP
```

左右が同じ正の値なら前進します。左が負で右が正なら左旋回、左が正で右が負なら右旋回します。

## 初期位置
`pc/config.yaml` の `simulation` で初期位置を設定します。単位は `mm`、角度は `deg` です。

```yaml
simulation:
  start_x_mm: 300
  start_y_mm: 300
  start_theta_deg: 0
```

設定 / 診断タブでは次の操作ができます。

- `シミュレーションリセット`: 位置、速度、エンコーダ、軌跡を初期状態へ戻します。
- `初期位置に戻す`: 速度を止め、位置と向きだけを初期位置へ戻します。
- `軌跡クリア`: マップ上の移動軌跡を消します。

## フィールド境界
フィールドサイズは `field` で設定します。

```yaml
field:
  width_mm: 3000
  height_mm: 2000
  grid_size_mm: 100
```

ロボットがフィールド外へ出ようとした場合、位置は境界内に制限され、状態に `フィールド境界に到達` が表示されます。

## 障害物
矩形障害物は `simulation.obstacles` に設定します。

```yaml
simulation:
  obstacles:
    - id: wall_1
      label: "障害物1"
      x_mm: 1000
      y_mm: 600
      width_mm: 300
      height_mm: 200
```

`x_mm` と `y_mm` は障害物の中心位置です。仮想ロボットが障害物に入ろうとすると、前の安全な位置で停止し、状態に `障害物に接触` が表示されます。

## 仮想LiDAR
Simulationモードでは、フィールド境界と障害物を使って前方、左、右、後方の距離を計算します。

センサ値には次のように表示されます。

```text
前方: シミュレーション 850 mm / 左: シミュレーション 1200 mm / 右: シミュレーション 430 mm
```

## 自動走行
設定 / 診断タブの `自動走行開始` と `自動走行停止` で、ルールベースの簡易自動走行を操作できます。

判断は仮想LiDARを使います。

- 前方が空いている場合: 前進
- 前方が近い場合: 左右で空きが大きい方向へ旋回
- 前方も左右も近い場合: 停止
- LiDARデータがない場合: 停止

自動走行が作る指令も、手動操作と同じ `robot_command`、`safety_layer`、`command_sender`、`robot_simulator` の経路を通ります。緊急停止を押すと自動走行は停止し、速度指令を出しません。

設定は `auto_drive` で変更できます。

```yaml
auto_drive:
  enabled: false
  mode: "rule_based"
  forward_speed: 100
  turn_speed: 80
  front_stop_distance_mm: 400
  side_preference_margin_mm: 100
  command_interval_ms: 300
```

現在の自動走行はシミュレーション専用です。Mockモードや実機モードでは開始できません。

## コマンドラインテスト

```cmd
.venv\Scripts\python.exe examples\test_simulation.py
.venv\Scripts\python.exe examples\test_simulation_reset.py
.venv\Scripts\python.exe examples\test_virtual_lidar.py
.venv\Scripts\python.exe examples\test_auto_controller.py
```

## 今後の拡張候補
- 実機LiDARとの接続
- 障害物回避の高度化
- 経路計画
- 強化学習コントローラ

## F3RC2026フィールドモデルとの関係

シミュレーション位置はテストフィールドタブへ渡され、F3RC2026公式フィールドのmm座標上に表示されます。

- 公式/簡易表示モード
- 500mm/1000mmグリッド
- 倉庫A/B/C、遊歩道、庭、R2スタートゾーン
- ロボット軌跡
- 将来比較用のLiDARレイ

実モータ出力は有効化しません。
