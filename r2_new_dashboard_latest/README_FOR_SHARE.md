# 4WIS Dashboard Share Package

作成日時: 2026-08-24 12:25:31
学籍番号: 126R024

## 安全な確認方法（実機なし）

1. ZIPを展開します。
2. setup-robot-dashboard-4wis.cmd を実行します。
3. un-fake-robot-dashboard.cmd --robot R1 または --robot R2 を実行します。

Fake共有画面は自動ARMせず、Serial/COM探索や実機出力を行いません。

## その他の起動方法

- 既存4WISダッシュボード: un-robot-dashboard-4wis.cmd
- 新R2 GUI（標準ではmotion無効）: un-r2-new-dashboard.cmd --port COM番号

実機接続、ARM、モータ/サーボ動作、ファームウェア書き込みを行う場合は、COM所有権、車輪浮かせ、低出力、停止後SAFE/PWMゼロを確認してください。

## 主な内容

- pps/robot_pc_system_4wis_dashboard: 4WISダッシュボード本体
- config: R1/R2車体、ノード、コントローラ設定
- pc_controller: v29 NDJSON制御とFake/共有GUIロジック
- sp32_firmware: ESP32実機ファームウェアのソース
- 	ests: 共有後のソフトウェア確認用テスト
- docs: GUI、安全、Fake、Competition関連資料

## 除外したもの

仮想環境、キャッシュ、ローカルログ、ビルド生成物、local_settings.json、ローカル絶対パスとCOM7で実機動作を有効にする個人用ランチャーは含めていません。