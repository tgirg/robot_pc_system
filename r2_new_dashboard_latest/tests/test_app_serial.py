from __future__ import annotations

from pc_controller.safety import SafetyMonitor, SafetyState
from pc_controller.app import ControllerApp
from pc_controller.protocol import decode_line
from pc_controller.serial_link import SerialLink


class DummySerial:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines
        self.written: list[bytes] = []

    def read_lines(self) -> list[bytes]:
        return self._lines

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    def close(self) -> None:
        pass


def test_read_serial_messages_skips_partial_line() -> None:
    app = ControllerApp.__new__(ControllerApp)
    app.serial = DummySerial(
        [
            b'mmand_age_ms":123}\n',
            b'{"v":1,"type":"telemetry","seq":1,"state":"SAFE"}\n',
        ]
    )
    app.last_telemetry = None
    app.safety = SafetyMonitor()
    app.last_fault_text = None
    app.last_serial_error_text = None
    app.transition = type("Transition", (), {"reset": lambda self, now_ms: None})()
    app._now_ms = lambda: 100  # type: ignore[method-assign]

    ControllerApp._read_serial_messages(app)

    assert app.last_telemetry == {"v": 1, "type": "telemetry", "seq": 1, "state": "SAFE"}
    assert app.safety.fault == "malformed serial JSON"
    assert decode_line(app.serial.written[0])["type"] == "disarm"


def test_fault_message_forces_pc_safe() -> None:
    app = ControllerApp.__new__(ControllerApp)
    app.serial = DummySerial([b'{"v":1,"type":"fault","fault_flags":2,"reason":"pca"}\n'])
    app.last_telemetry = None
    app.safety = SafetyMonitor()
    app.safety.arm(0)
    app.last_fault_text = None
    app.last_serial_error_text = None
    app.transition = type("Transition", (), {"reset": lambda self, now_ms: None})()
    app._now_ms = lambda: 100  # type: ignore[method-assign]

    ControllerApp._read_serial_messages(app)

    assert app.safety.state == SafetyState.SAFE
    assert app.safety.fault == "pca"
    assert decode_line(app.serial.written[0])["type"] == "disarm"


class ChunkSerial:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size: int) -> bytes:
        del size
        return self.chunks.pop(0)


def test_serial_link_buffers_partial_ndjson_frames() -> None:
    link = SerialLink.__new__(SerialLink)
    link._serial = ChunkSerial([b'{"v":1,"type":"tele', b'metry","seq":1}\n'])
    link._rx_buffer = bytearray()
    link.trace = False

    assert list(SerialLink.read_lines(link)) == []
    assert list(SerialLink.read_lines(link)) == [b'{"v":1,"type":"telemetry","seq":1}']
