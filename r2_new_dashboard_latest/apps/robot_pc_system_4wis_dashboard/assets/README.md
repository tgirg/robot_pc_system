# アプリアイコン

`assets\app_icon.ico` を置くと、デスクトップショートカットとダッシュボードのウィンドウアイコンに使われます。

`app_icon.ico` が無くても、ダッシュボードの起動には問題ありません。その場合はWindowsの既定アイコンが使われます。

推奨サイズ:

- 256x256
- 128x128
- 64x64
- 32x32

PNGからICOを作る場合は、任意ツールとして `tools\make_icon.py` を使えます。

```cmd
.venv\Scripts\python.exe tools\make_icon.py
```

このツールは `assets\app_icon.png` から `assets\app_icon.ico` を作ります。Pillow が必要です。Pillow が無い場合でも、通常のダッシュボード起動には影響しません。
