"""In-memory NDJSON serial transport backed by :class:`SimulatedEsp32`."""

from __future__ import annotations

import json
import time
from typing import Callable

from .protocol import ProtocolError, decode_line, encode_message
from .simulator import SimulatedEsp32


def _utc_now_ms() -> int:
    return int(time.monotonic() * 1000)


class VirtualSerialLink:
    """Drop-in serial-link stand-in that exercises the real protocol codec."""

    def __init__(
        self,
        device: SimulatedEsp32 | None = None,
        *,
        trace: bool = False,
        now_ms: Callable[[], int] | None = None,
        reconnect: bool = False,
    ) -> None:
        self.device = device or SimulatedEsp32()
        self.port = f"SIM://{self.device.node_id}"
        self.trace = trace
        self.reconnect = reconnect
        self.closed = False
        self._pending: list[tuple[int, bytes]] = []
        self.writes: list[dict[str, object]] = []
        self._now_ms = now_ms or _utc_now_ms
        self.event_log: list[dict[str, object]] = []

    def write(self, payload: bytes) -> None:
        if self.closed:
            raise RuntimeError("virtual serial link is closed")
        now_ms = self._now_ms()
        for raw_line in payload.splitlines():
            if not raw_line.strip():
                continue
            self._record_event("tx", raw_line, now_ms)
            try:
                message = decode_line(raw_line)
            except ProtocolError as exc:
                response = self.device.fault(str(exc))
                self._schedule_response(response, now_ms)
                continue
            self.writes.append(dict(message))
            reboot_count_before = self.device.reboot_count
            try:
                responses = self.device.handle_message(message, now_ms=now_ms)
            except RuntimeError as exc:
                self._pending = []
                self._record_event(
                    "disconnect",
                    {"type": str(message.get("type", "?")), "reason": str(exc)},
                    now_ms,
                )
                raise
            if self.device.reboot_count > reboot_count_before:
                self._pending = []
                self._record_event("reboot", {"type": "transport"}, now_ms)
            for response in responses:
                self._schedule_response(response, now_ms)

    def read_lines(self) -> list[bytes]:
        if self.closed:
            return []
        now_ms = self._now_ms()
        try:
            device_event = self.device.poll(now_ms)
        except RuntimeError as exc:
            self._pending = []
            self._record_event("disconnect", {"type": "transport", "reason": str(exc)}, now_ms)
            raise
        if device_event == "reboot":
            self._pending = []
            self._record_event("reboot", {"type": "transport"}, now_ms)
            return []
        ready = [raw for due_ms, raw in self._pending if due_ms <= now_ms]
        self._pending = [(due_ms, raw) for due_ms, raw in self._pending if due_ms > now_ms]
        for raw in ready:
            self._record_event("rx", raw, now_ms)
        return ready

    def close(self) -> None:
        if not self.closed:
            self._record_event("close", {"type": "transport"}, self._now_ms())
        self.closed = True
        self._pending = []

    def _schedule_response(self, response: dict[str, object] | bytes, now_ms: int) -> None:
        if self.should_drop():
            self._record_event("drop", response, now_ms)
            return
        if isinstance(response, bytes):
            raw = response
            if not raw.endswith(b"\n"):
                raw = raw + b"\n"
        else:
            raw = encode_message(response)
        delay_ms = max(0, self.device.response_delay_ms())
        due_ms = now_ms + delay_ms
        self._pending.append((due_ms, raw))
        self._record_event("schedule", response, now_ms)

    def should_drop(self) -> bool:
        try:
            return self.device.should_drop_response()
        except AttributeError:
            return False

    def _record_event(self, event: str, payload: bytes | dict[str, object], now_ms: int) -> None:
        payload_obj: dict[str, object] = {}
        if isinstance(payload, bytes):
            text = payload.decode("utf-8", errors="backslashreplace")
            try:
                payload_obj = json.loads(text)
            except json.JSONDecodeError:
                payload_obj = {"raw": text}
        else:
            payload_obj = dict(payload)
        message_type = str(payload_obj.get("type", "?"))
        command_seq = (
            payload_obj.get("seq")
            if message_type != "telemetry" and isinstance(payload_obj.get("seq"), int)
            else None
        )
        telemetry_seq = payload_obj.get("telemetry_seq")
        if message_type == "telemetry":
            telemetry_seq = payload_obj.get("seq", None)
        event_record = {
            "timestamp": int(now_ms),
            "node_id": self.device.node_id,
            "state": self.device.state,
            "armed": self.device.armed,
            "event": event,
            "type": message_type,
            "command_seq": command_seq,
            "telemetry_seq": telemetry_seq,
            "fault": payload_obj.get("reason"),
            "reconnect": self.reconnect,
        }
        self.event_log.append(event_record)
        if not self.trace:
            return
        print(
            "virtual serial "
            f"{event} "
            f"node_id={event_record['node_id']} "
            f"state={event_record['state']} "
            f"armed={event_record['armed']} "
            f"event={event_record['event']} "
            f"command_seq={event_record['command_seq']} "
            f"telemetry_seq={event_record['telemetry_seq']} "
            f"fault={event_record['fault']} "
            f"reconnect={event_record['reconnect']} "
            f"payload={json.dumps(payload_obj, ensure_ascii=False)}",
            flush=True,
        )
