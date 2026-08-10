# Codex作業ルール

## 基本方針

Codexに依頼するときは、1回の指示で変更する範囲を小さくします。
動いているUIを守るため、目的、変更してよい場所、変更してはいけない場所、検証方法を明確に書きます。

## 変更範囲を小さくする

良い例:

```text
main_ui.pyは変更せず、examplesにシリアル送信サンプルを追加してください。
```

悪い例:

```text
全部いい感じに直して。
```

## 変更後の検証

Pythonコードを変更したら次を実行します。

```cmd
.venv\Scripts\python.exe -m compileall pc examples tools
```

UIを変更した場合は、短時間でも起動確認します。

```cmd
tools\run_dashboard.bat
```

## 本体を壊さないための注意

- `pc/main_ui.py` は必要な場合だけ変更する。
- 既存の `pc/config.yaml` を勝手に置き換えない。
- Mockモードで起動できる状態を維持する。
- 緊急停止ボタンとEscキーを壊さない。
- 実機未接続でもアプリが落ちないようにする。

## 良い指示例

```text
toolsにログ確認用スクリプトを追加してください。UI本体は変更しないでください。
検証は .venv\Scripts\python.exe -m compileall pc examples tools でお願いします。
```

```text
ESP32のdrive_controller.inoに新しいコマンドを追加してください。
既存のDRIVE VELとEMERGENCY_STOPは維持してください。
```

```text
センサ値パネルの表示文言だけ変更してください。main_ui.pyは変更しないでください。
```

## 悪い指示例

```text
UIも通信もESP32も全部まとめて作り直して。
```

```text
config.yamlを実機用に全部置き換えて。
```

```text
Mockモードはいらないので消して。
```

## Codexに伝えるとよい情報

- 実機が接続されているか。
- COMポート番号。
- Mock / Simulation / Real のどれで確認したいか。
- UI変更なのか、ESP32変更なのか、ツール追加なのか。
- 実行してほしい検証コマンド。
