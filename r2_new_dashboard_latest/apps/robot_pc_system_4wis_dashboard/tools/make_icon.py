from __future__ import annotations

from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    png_path = project_root / "assets" / "app_icon.png"
    ico_path = project_root / "assets" / "app_icon.ico"

    if not png_path.exists():
        print("assets\\app_icon.png が見つかりません。PNGを置いてから実行してください。")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("Pillow が見つかりません。必要な場合は pip install pillow を実行してください。")
        return 1

    image = Image.open(png_path).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (32, 32)]
    image.save(ico_path, format="ICO", sizes=sizes)
    print(f"アイコンを作成しました: {ico_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
