# 接続基盤ライブラリ

## 目的
`pc/connection` は、ESP32とのシリアル接続を共通化するための基盤です。現在は走行用ESP32を対象にしていますが、将来は `drive`、`arm`、`tool`、`sensor` の複数コントローラへ拡張する前提です。

## 構成
- `connection_result.py`: 接続結果、接続状態、COMポート情報のデータ構造。
- `serial_connection.py`: pyserialを安全に包む低レベル接続クラス。
- `port_detector.py`: COMポートを検出し、ESP32候補を判定します。
- `connection_manager.py`: `drive` などの名前付き接続を管理します。

## COMポート検出
`port_detector` はCOMポートの説明文やHWIDを確認し、次の文字列を含む場合に `ESP32候補` として扱います。

- Silicon Labs CP210x
- CH340
- USB Serial
- USB to UART
- UART Bridge

例:

```text
COM10 - Silicon Labs CP210x USB to UART Bridge（ESP32候補）
```

## UIでの使い方
`設定 / 診断` タブの `ESP32接続` セクションを使います。

1. `COMポート更新` を押します。
2. 必要なら `ESP32候補を自動選択` を押します。
3. `ESP32接続` を押します。
4. `接続テスト` を押して `STATUS,OK` が受信できるか確認します。
5. 切断するときは `ESP32切断` を押します。

## よくある接続失敗
- Arduino IDEやシリアルモニタがCOMポートを開いている。
- USBケーブルが充電専用で通信できない。
- COMポート番号が変わっている。
- ESP32にスケッチが書き込まれていない。
- ボードのリセット直後でまだ起動していない。

## Simulation / Mock / Realの送信先
- Simulationモード: 走行指令はシミュレータへ送ります。ESP32が接続されていても実モータへは送信しません。
- Mockモード: Mock通信として扱います。
- Realモード: 接続済みESP32へ送信します。

このルールにより、シミュレーション確認中に実機モータへ誤って走行指令を送らないようにしています。

## コマンドライン確認

```cmd
.venv\Scripts\python.exe examples\test_port_detector.py
.venv\Scripts\python.exe examples\test_serial_connection.py COM10
```
