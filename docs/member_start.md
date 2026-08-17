# メンバー向けスタートガイド

この資料は、`robot_pc_system` を初めて見るメンバー向けの入口です。
Codexで開く場合も、まずこのファイルとREADMEを読ませると全体像を掴みやすくなります。

## まず見るファイル

1. `README.md`
2. `docs/member_start.md`
3. `docs/feature_summary.md`
4. `docs/sensor_flow.md`
5. `docs/esp32_sketches.md`
6. `docs/codex_workflow.md`

## このプロジェクトの目的

F3RC / FC用のR2制御・確認アプリです。
Windows 11のPCで、ESP32、9軸IMU、SparkFun Qwiic OTOS光学式オドメトリ、フィールド表示、自己位置推定を確認します。

PCはUI、ログ、センサ受信、自己位置推定、フィールド表示を担当します。
ESP32はセンサ読み取り、シリアル送信、将来の低レベルI/Oを担当します。

## 起動方法

初回セットアップ:

```cmd
tools\setup_windows.bat
```

開発用ダッシュボード:

```cmd
tools\run_dashboard.bat
```

本番用FC Run:

```cmd
run_fc.bat
```

手動起動:

```cmd
.venv\Scripts\python.exe pc\main_ui.py
```

## 重要な注意

- `.venv` と `logs` は共有しません。
- COMポートはPCごとに違います。
- Arduino IDEのシリアルモニタを開いたままだと、アプリ側で同じCOMを使えません。
- ESP32への自動書き込みはしません。
- 実モータ出力は安全のため有効化しません。
- センサ未接続時は、実値欄を0として扱います。

## メンバーが作業するとき

作業前に最新版を取得します。

```cmd
git pull
```

作業用ブランチを作ります。

```cmd
git checkout -b feature/作業名
```

変更後は、何を変えたかDiscordへ共有してください。

```text
【更新報告】
追加した機能:
- 

変更した場所:
- 

確認したこと:
- 

注意点:
- 
```

