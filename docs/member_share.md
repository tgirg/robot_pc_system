# メンバー共有手順

このプロジェクトはGitHubなどのGitリポジトリで共有します。メンバーはリポジトリを取得して、CodexまたはVS Codeで開けば同じ構成で開発できます。

現在の共有先:

```text
https://github.com/tgirg/robot_pc_system.git
```

中身を知りたいメンバーは、まず次の順番で読んでください。

1. `README.md`
2. `docs/member_start.md`
3. `docs/feature_summary.md`
4. `docs/sensor_flow.md`
5. `docs/esp32_sketches.md`
6. `docs/team_collaboration.md`
7. `docs/codex_workflow.md`

## 相手の最新版に追加する流れ

作業を始める前に、最新版から作業ブランチを作ります。

```cmd
tools\team_start_feature.bat feature/作業名
```

作業後、変更をGitHubへ送ります。

```cmd
tools\team_publish_feature.bat "変更内容"
```

詳しくは `docs/team_collaboration.md` を参照してください。

## 共有する側

1. GitHubで新しいリポジトリを作成します。
2. この `robot_pc_system` フォルダをGit管理します。
3. `.gitignore` により、ログ、仮想環境、ビルドキャッシュ、ローカル設定は共有対象から外します。

初回だけ実行する例:

```cmd
git init
git add .
git commit -m "Initial robot PC dashboard"
git branch -M main
git remote add origin https://github.com/USER_OR_TEAM/robot_pc_system.git
git push -u origin main
```

## メンバー側

任意の作業フォルダで取得します。

```cmd
git clone https://github.com/USER_OR_TEAM/robot_pc_system.git
cd robot_pc_system
tools\setup_windows.bat
tools\run_dashboard.bat
```

手動で環境を作る場合:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python pc\main_ui.py
```

## Codexで開く場合

1. メンバーのPCでリポジトリをcloneします。
2. Codexで `robot_pc_system` フォルダを開きます。
3. 依頼するときは、対象を具体的に書きます。

例:

```text
テストフィールドのR2表示を調整して
optical_odometry_test.ino の読み取り処理を確認して
書き込みタブのUIを整理して
```

## 各PCで変更するもの

COMポートやカメラ番号はPCごとに違うため、各メンバーの環境に合わせて変更します。

- `pc/config.yaml`
- `config/optical_odometry.yaml`
- `config/hardware_profile.yaml`

`config/local_settings.json` はローカル専用なのでGitには入れません。

## Arduino / ESP32

ESP32関連の準備:

```cmd
tools\setup_arduino_cli.bat
tools\check_arduino_cli.bat
tools\list_ports.bat
```

COMポートは接続するPCごとに変わります。`COM10` とは限りません。

## 注意

- 実モータ出力は有効化しないでください。
- 自動アップロードは使いません。
- Arduino IDEのシリアルモニタとアプリのシリアルモニタは同じCOMポートを同時に使えません。
- ログやビルドキャッシュは共有しません。
- センサ未接続時の値は0表示を基本にします。
