# 開発者メモ

## プロジェクト構成

- `pc/`: PySide6ダッシュボード本体、Mockセンサ、シリアル通信、ログ保存。
- `pc/widgets/`: 画面部品。状態表示、センサ値、カメラ、マップ、操作パネル。
- `esp32/`: ESP32向けArduinoスケッチ。
- `tools/`: Windows用セットアップ、起動、チェック、Arduino CLI補助ツール。
- `examples/`: UIを起動せずに試せる開発用サンプル。
- `docs/`: 手順、運用、開発メモ。
- `logs/`: CSVログ出力先。

## 変更してよい場所

- 新しい実験コードは `examples/` に置く。
- チーム運用ツールは `tools/` に置く。
- ESP32側の変更は `esp32/drive_controller/` を優先する。
- UI表示部品の小さな変更は `pc/widgets/` を優先する。

## 壊してはいけない場所

- `pc/main_ui.py` の起動処理。
- Mock / Simulation / Real の表示区別。
- 緊急停止ボタンとEscキー処理。
- `pc/config.yaml` の既存キー。
- Mockカメラ、Mockセンサ、ログ表示、タブ構成。

## main_ui.pyを変更する前の注意

`main_ui.py` は起動、タイマー、各ウィジェット接続、シリアル通信、ログ保存をまとめています。
変更する前に、同じ目的を `pc/widgets/`、`tools/`、`examples/`、設定ファイルで実現できないか確認してください。

変更した場合は必ず次を実行します。

```cmd
.venv\Scripts\python.exe -m compileall pc
```

UIを変えた場合は短時間でも起動確認します。

## Mock / Simulation / Real の違い

- Mock: 実機なし。値はダミーデータ。表示では `Mock` と明示する。
- Simulation: 仮想フィールド上の計算値。実センサ値ではない。
- Real: 接続された実センサやESP32からの実データ。

実機未接続の値を、実データのように表示してはいけません。

## ESP32通信コマンド形式

PCからESP32へ送る主な指令:

```text
DRIVE VEL 100 100
DRIVE VEL 0 0
DRIVE VEL -80 80
DRIVE VEL 80 -80
DRIVE STOP
EMERGENCY_STOP
```

互換コマンド:

```text
FWD 100
STOP
TURN_L 80
TURN_R 80
```

## 今後の開発候補

- 実LiDAR、実IMU、光学式オドメトリ、エンコーダ入力の接続。
- ESP32からのステータス受信とUI反映。
- モータドライバの実ピン設定。
- アーム、ツール、ポンプなど作業機構制御。
- ログ再生、試合シーケンス、自己位置推定の改善。
