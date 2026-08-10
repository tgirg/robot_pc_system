from __future__ import annotations

import argparse
import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"


def find_latest_log() -> Path | None:
    logs = sorted(LOG_DIR.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def resolve_log_path(value: str | None) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    latest = find_latest_log()
    if latest is None:
        raise FileNotFoundError("logsフォルダにCSVログが見つかりません。")
    return latest


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser(description="CSVログの概要を表示します。")
    parser.add_argument("log_file", nargs="?", help="ログCSV。省略時はlogs内の最新CSVを使用します。")
    args = parser.parse_args()

    try:
        path = resolve_log_path(args.log_file)
        rows = read_rows(path)
    except OSError as exc:
        print(f"エラー: ログを読み込めませんでした: {exc}")
        raise SystemExit(1) from exc

    print(f"ログファイル: {path}")
    print(f"行数: {len(rows)}")
    if not rows:
        print("データ行がありません。")
        return

    first = rows[0]
    last = rows[-1]
    print(f"最初のtimestamp: {first.get('timestamp', '-')}")
    print(f"最後のtimestamp: {last.get('timestamp', '-')}")
    print(
        "最後のロボット位置: "
        f"x={last.get('x', '-')} / y={last.get('y', '-')} / theta={last.get('theta', '-')}"
    )
    print(f"最後の指令: {last.get('current_command', '-')}")


if __name__ == "__main__":
    main()
