from __future__ import annotations

import time

import serial

from .connection_result import ConnectionResult, ConnectionStatus


class SerialConnection:
    def __init__(self, timeout: float = 0.05, reconnect_interval_s: float = 2.0, write_timeout: float = 1.0) -> None:
        self.timeout = float(timeout)
        self.write_timeout = max(float(write_timeout), self.timeout)
        self.reconnect_interval_s = float(reconnect_interval_s)
        self.port = ""
        self.baudrate = 0
        self.conn: serial.Serial | None = None
        self.last_error = "未接続"
        self.last_connect_attempt = 0.0
        self.last_received_line = ""
        self.last_received_time = 0.0
        self.received_line_count = 0

    def connect(self, port: str, baudrate: int) -> ConnectionResult:
        self.disconnect()
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.last_connect_attempt = time.monotonic()
        try:
            self.conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout, write_timeout=self.write_timeout)
            self.last_error = ""
            return ConnectionResult(True, f"接続しました: {self.port}", self.port, self.baudrate)
        except serial.SerialException as exc:
            self.conn = None
            self.last_error = self._friendly_error(exc)
            return ConnectionResult(False, self.last_error, self.port, self.baudrate, str(exc))

    def reconnect(self) -> ConnectionResult:
        if not self.port or not self.baudrate:
            return ConnectionResult(False, "再接続先のCOMポートが未設定です", self.port, self.baudrate)
        now = time.monotonic()
        if now - self.last_connect_attempt < self.reconnect_interval_s:
            return ConnectionResult(False, "再接続間隔の待機中です", self.port, self.baudrate)
        return self.connect(self.port, self.baudrate)

    def disconnect(self) -> ConnectionResult:
        if self.conn is not None:
            try:
                self.conn.close()
            except serial.SerialException as exc:
                self.last_error = self._friendly_error(exc)
                self.conn = None
                return ConnectionResult(False, self.last_error, self.port, self.baudrate, str(exc))
            finally:
                self.conn = None
        self.last_error = "切断済み"
        return ConnectionResult(True, "切断しました", self.port, self.baudrate)

    def is_connected(self) -> bool:
        return bool(self.conn and self.conn.is_open)

    def send_line(self, text: str) -> ConnectionResult:
        if not self.is_connected() or self.conn is None:
            return ConnectionResult(False, "COMポートを開けていません。Arduino IDEのシリアルモニタを閉じてください。", self.port, self.baudrate)
        clean = text.strip()
        try:
            self.conn.write((clean + "\n").encode("utf-8"))
            self.conn.flush()
            return ConnectionResult(True, f"送信しました: {clean}", self.port, self.baudrate)
        except serial.SerialException as exc:
            self.last_error = self._friendly_error(exc)
            self.disconnect()
            return ConnectionResult(False, self.last_error, self.port, self.baudrate, str(exc))

    def read_lines(self, max_lines: int = 50) -> list[str]:
        if not self.is_connected() or self.conn is None:
            return []
        lines: list[str] = []
        for _ in range(max(0, int(max_lines))):
            try:
                if self.conn.in_waiting <= 0:
                    break
                raw = self.conn.readline()
            except (OSError, serial.SerialException) as exc:
                self.last_error = self._friendly_error(exc)
                self.disconnect()
                break
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self.last_received_line = line
                self.last_received_time = time.time()
                self.received_line_count += 1
                lines.append(line)
        return lines

    def get_status(self) -> ConnectionStatus:
        return ConnectionStatus(
            connected=self.is_connected(),
            message="接続中" if self.is_connected() else self.last_error,
            port=self.port,
            baudrate=self.baudrate,
            last_received_line=self.last_received_line,
            last_received_time=self.last_received_time,
            received_line_count=self.received_line_count,
            error="" if self.is_connected() else self.last_error,
        )

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        lower = text.lower()
        if "access is denied" in lower or "permission" in lower:
            return "COMポートを開けません。Arduino IDEのシリアルモニタを閉じてください。"
        if "timeout" in lower:
            return "シリアル送信がタイムアウトしました。USB接続とCOM競合を確認してください。"
        if "cannot find" in lower or "file not found" in lower or "system cannot find" in lower:
            return "COMポートが見つかりません。USBケーブルを確認してください。"
        return f"シリアル通信エラー: {text}"
