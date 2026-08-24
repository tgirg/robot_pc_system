from __future__ import annotations

import json
from typing import Any

import pytest

from pc_controller.node_inventory import NodeRequirement, evaluate_node_inventory
from pc_controller.serial_discovery import (
    AmbiguousSerialNodeError,
    NoMatchingSerialNodeError,
    discover_serial_nodes,
    normalize_identity,
    open_discovered_serial_link,
)


class FakeSerialLink:
    responses: dict[str, dict[str, list[dict[str, Any]]]] = {}
    instances: dict[str, "FakeSerialLink"] = {}

    def __init__(self, port: str, **_: object) -> None:
        self.port = port
        self.closed = False
        self.pending: list[bytes] = []
        self.writes: list[dict[str, Any]] = []
        FakeSerialLink.instances[port] = self

    def write(self, payload: bytes) -> None:
        message = json.loads(payload.decode("utf-8"))
        self.writes.append(message)
        for response in FakeSerialLink.responses.get(self.port, {}).get(message["type"], []):
            self.pending.append((json.dumps(response) + "\n").encode("utf-8"))

    def read_lines(self) -> list[bytes]:
        lines = self.pending
        self.pending = []
        return lines

    def close(self) -> None:
        self.closed = True


def setup_function() -> None:
    FakeSerialLink.responses = {}
    FakeSerialLink.instances = {}


def test_normalize_identity_accepts_new_node_identity() -> None:
    identity = normalize_identity({"v": 1, "type": "node_identity", "node_id": "drive", "role": "drive"})
    assert identity == {"v": 1, "type": "node_identity", "node_id": "drive", "role": "drive"}


def test_normalize_identity_accepts_legacy_mcb44_hello_ack() -> None:
    identity = normalize_identity({"v": 1, "type": "hello_ack", "firmware": "mcb44_4wis"})
    assert identity is not None
    assert identity["node_id"] == "legacy_mcb44_drive"
    assert identity["role"] == "drive"


def test_open_discovered_serial_link_selects_unique_drive_node() -> None:
    FakeSerialLink.responses = {
        "COM7": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "sensor_front", "role": "sensor", "board": "SENSOR"}
            ]
        },
        "COM8": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "mcb44_drive_main", "role": "drive", "board": "MCB44"}
            ]
        },
    }

    probe = open_discovered_serial_link(ports=["COM7", "COM8"], link_factory=FakeSerialLink)

    assert probe.port == "COM8"
    assert probe.identity is not None
    assert probe.identity["node_id"] == "mcb44_drive_main"
    assert not FakeSerialLink.instances["COM8"].closed
    assert FakeSerialLink.instances["COM7"].closed


def test_open_discovered_serial_link_rejects_ambiguous_role() -> None:
    FakeSerialLink.responses = {
        "COM7": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "drive_a", "role": "drive", "board": "MCB44"}
            ]
        },
        "COM8": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "drive_b", "role": "drive", "board": "MCB44"}
            ]
        },
    }

    with pytest.raises(AmbiguousSerialNodeError, match="multiple serial nodes matched role=drive"):
        open_discovered_serial_link(ports=["COM7", "COM8"], link_factory=FakeSerialLink)

    assert FakeSerialLink.instances["COM7"].closed
    assert FakeSerialLink.instances["COM8"].closed


def test_open_discovered_serial_link_selects_exact_id_and_role() -> None:
    FakeSerialLink.responses = {
        "COM7": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "drive_a", "role": "drive"}
            ]
        },
        "COM8": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "drive_b", "role": "drive"}
            ]
        },
    }

    probe = open_discovered_serial_link(
        role="drive",
        node_id="drive_b",
        ports=["COM7", "COM8"],
        link_factory=FakeSerialLink,
    )

    assert probe.port == "COM8"
    assert FakeSerialLink.instances["COM7"].closed
    assert not FakeSerialLink.instances["COM8"].closed


def test_open_discovered_serial_link_rejects_exact_id_with_wrong_role() -> None:
    FakeSerialLink.responses = {
        "COM7": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "drive_main", "role": "sensor"}
            ]
        }
    }

    with pytest.raises(NoMatchingSerialNodeError, match="no serial node matched node_id=drive_main"):
        open_discovered_serial_link(
            role="drive",
            node_id="drive_main",
            ports=["COM7"],
            link_factory=FakeSerialLink,
        )

    assert FakeSerialLink.instances["COM7"].closed


def test_open_discovered_serial_link_rejects_duplicate_node_id() -> None:
    identity = {"v": 1, "type": "node_identity", "node_id": "drive_main", "role": "drive"}
    FakeSerialLink.responses = {
        "COM7": {"who_are_you": [identity]},
        "COM8": {"who_are_you": [identity]},
    }

    with pytest.raises(AmbiguousSerialNodeError, match="multiple serial nodes matched node_id=drive_main"):
        open_discovered_serial_link(
            role="drive",
            node_id="drive_main",
            ports=["COM7", "COM8"],
            link_factory=FakeSerialLink,
        )

    assert FakeSerialLink.instances["COM7"].closed
    assert FakeSerialLink.instances["COM8"].closed


def test_discovery_falls_back_to_hello_for_legacy_firmware() -> None:
    FakeSerialLink.responses = {
        "COM7": {
            "who_are_you": [{"v": 1, "type": "fault", "reason": "unknown type"}],
            "hello": [{"v": 1, "type": "hello_ack", "firmware": "mcb44_4wis"}],
        }
    }

    probes = discover_serial_nodes(ports=["COM7"], link_factory=FakeSerialLink)

    assert probes[0].identity is not None
    assert probes[0].identity["role"] == "drive"
    assert [write["type"] for write in FakeSerialLink.instances["COM7"].writes] == ["who_are_you", "hello"]


def test_multi_port_discovery_to_required_optional_inventory_e2e() -> None:
    FakeSerialLink.responses = {
        "COM7": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "sensor_front", "role": "sensor"}
            ]
        },
        "COM8": {
            "who_are_you": [
                {"v": 1, "type": "node_identity", "node_id": "mcb44_drive_main", "role": "drive"}
            ]
        },
        "COM9": {},
    }

    probes = discover_serial_nodes(
        ports=["COM7", "COM8", "COM9"],
        link_factory=FakeSerialLink,
    )
    report = evaluate_node_inventory(
        (
            NodeRequirement("mcb44_drive_main", "drive", True),
            NodeRequirement("sensor_front", "sensor", False),
        ),
        probes,
    )

    assert report.ready is True
    assert report.errors == ()
    assert [issue.code for issue in report.warnings] == ["unidentified_port"]
    assert all(instance.closed for instance in FakeSerialLink.instances.values())
