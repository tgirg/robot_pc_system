# チーム開発の流れ

相手が追加した最新版の上に、自分の変更をすぐ追加するための手順です。

## 基本ルール

- `main` は全員の共有最新版です。
- 自分の作業は `feature/...` ブランチで行います。
- 相手の変更を取り込んでから、自分の変更を始めます。
- `main` へ直接pushしません。
- 変更したら、Discordで内容を共有します。

## 1. 最新版を取得するだけ

作業前に、GitHubの最新版を取り込みます。

```cmd
tools\team_update.bat
```

このコマンドは、未コミット変更がある場合は止まります。
作業中の変更を消さないためです。

## 2. 最新版から作業を始める

相手の最新版を取り込んでから、新しい作業ブランチを作ります。

```cmd
tools\team_start_feature.bat feature/作業名
```

例:

```cmd
tools\team_start_feature.bat feature/otos-calibration-ui
```

この状態でCodexに作業を頼めば、相手の最新版に自分の変更を足せます。

## 3. 変更をGitHubへ送る

作業が終わったら、変更をコミットしてpushします。

```cmd
tools\team_publish_feature.bat "変更内容"
```

例:

```cmd
tools\team_publish_feature.bat "Add OTOS calibration UI"
```

push後、GitHubでPull Requestを作成します。

## 4. Discord報告テンプレ

```text
【更新報告】
ブランチ:
feature/

追加した機能:
-

変更した場所:
-

確認したこと:
-

Pull Request:
URLを貼る
```

## 5. Codexに頼むときの例

```text
相手の最新版に追加する前提で、テストフィールドのR2表示を修正してください。
既存のセンサ受信とFC Runは壊さないでください。
変更後にcompileallと関連テストを実行してください。
```

## 6. 競合したとき

`git pull` や `team_update.bat` が失敗した場合は、同じファイルを複数人が変更している可能性があります。

その場合は、無理に進めずにDiscordで次を共有します。

```text
【競合】
どのブランチ:

何を変更した:

止まったコマンド:

表示されたエラー:
```

