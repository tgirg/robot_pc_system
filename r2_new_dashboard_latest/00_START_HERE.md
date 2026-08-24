# まず見るファイル

このプロジェクトで迷ったら、まずこのファイルを見てください。
実機を動かす起動ファイルはルート直下に残しています。フォルダ移動すると手順が壊れやすいので、起動スクリプトは動かさない方針です。

## よく使う入口

| やりたいこと | 使うもの |
| --- | --- |
| 現在の4輪独立ステアリング実機制御 | `run-pc-controller.cmd` |
| PC側の友人ダッシュボードを開く | `run-robot-dashboard.cmd` |
| 実機なしの共有Dashboard / Drive / Mechanism / Sensor / Calibration / Direction / Parameter / Fault History / Autonomy / Logs / Replay / Servo Zero/Angle local draftを開く | `run-fake-robot-dashboard.cmd --robot R1` または `--robot R2`。local Competition logとoffline Replayを表示する場合だけ `--competition-log <local.jsonl>` を追加 |
| ダッシュボード依存関係の初回セットアップ | `setup-robot-dashboard.cmd` |
| エンコーダ確認 | `run-encoder-monitor.cmd` |
| 実機なしのFake Robot試験 | `python -m pc_controller.fake_robot_demo` |
| ESP32ファームウェア | `esp32_firmware/` |
| 車体・サーボ・モータ設定 | `config/` |
| 詳細な手順 | `README.md` |
| フォルダの詳しい置き場ルール | `docs/project-map.md` |

## トップ階層の見方

| 場所 | 中身 |
| --- | --- |
| `pc_controller/` | 現行の実機制御PCアプリ。JSONプロトコルでESP32へ送る本命ルート |
| `esp32_firmware/` | 現行ESP32ファームウェア |
| `config/` | 現行v29車体設定とコントローラ設定 |
| `apps/robot_pc_system/` | 友人作成のPySide6ダッシュボード。現状はMock/Simulation/診断用 |
| `docs/` | 説明、引き継ぎ、調査メモ |
| `docs/reports/` | ピンマップなどの単体レポート |
| `bom/` | 部品表とチャットログ由来の部品キャッシュ |
| `基板/` | KiCadなど基板関連 |
| `06_3Dモデル/` | ルート直下に散らばっていた単体STLの置き場 |
| `パンタグラフアーム/` | パンタグラフ機構のSTL |
| `収納/` | 収納・ケース系の3Dモデルと設計メモ |
| `drivers/` | 外部ドライバや参考ドライバ |
| `analysis/` | 解析用の中間データ |
| `outputs/` | 生成物・納品物・発注用出力 |
| `logs/` | 実行ログ |
| `tests/` | Pythonテスト |
| `01_F3RC2026_ロボコン/` から `05_GoogleDrive/` | 初期の分類フォルダ。過去資料として残す |
| `99_作業用/` | 一時作業・実験・古い作業出力 |

## 開かなくてよいもの

| 場所 | 理由 |
| --- | --- |
| `.codex_work/` | Codex作業用の一時clone、検証生成物、キャッシュ |
| `.pytest_cache/` | pytestのキャッシュ |
| `.venv/`, `.venv_win/` | 既存のローカル仮想環境。現在の実機起動は `C:\robot_venvs\robot_project_kicad` を使う |
| `.agents/`, `.codex/` | Codex用メタ情報 |

## 実機操作の注意

実機走行は `run-pc-controller.cmd` を使います。
友人ダッシュボードは元々 `DRIVE VEL 100 100` 形式の2輪風コマンドを送る設計で、現行v29のJSONプロトコルとは違います。
そのため、ダッシュボードは今のところMock/Simulation、診断、センサ表示、シリアル確認用として扱ってください。

実機確認は車輪を浮かせ、低出力で、モータ電源とサーボ電源を分けて確認してください。
