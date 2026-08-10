from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CommandHistoryEntry:
    timestamp: str
    command_text: str
    source: str
    success: bool
    safety_message: str = ""


class CommandHistory:
    def __init__(self, max_entries: int = 200) -> None:
        self.entries: deque[CommandHistoryEntry] = deque(maxlen=max_entries)

    def add(self, command_text: str, source: str, success: bool, safety_message: str = "") -> None:
        self.entries.append(
            CommandHistoryEntry(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                command_text=command_text,
                source=source,
                success=success,
                safety_message=safety_message,
            )
        )

    def get_recent(self, limit: int = 20) -> list[CommandHistoryEntry]:
        return list(self.entries)[-limit:]

    def clear(self) -> None:
        self.entries.clear()
