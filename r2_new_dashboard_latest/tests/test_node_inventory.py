from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pc_controller.app import print_node_list
from pc_controller.node_inventory import (
    NodeRequirement,
    evaluate_node_inventory,
    format_node_inventory,
    load_node_manifest,
)
from pc_controller.serial_discovery import SerialProbe


def _probe(port: str, node_id: str, role: str) -> SerialProbe:
    return SerialProbe(
        port=port,
        identity={"v": 1, "type": "node_identity", "node_id": node_id, "role": role},
    )


def _write_manifest(path: Path, nodes: list[dict[str, Any]]) -> Path:
    path.write_text(
        json.dumps({"schema_version": 1, "nodes": nodes}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_repository_node_manifest_matches_confirmed_drive_identity() -> None:
    requirements = load_node_manifest(Path("config") / "node_manifest.json")

    assert requirements == (NodeRequirement("mcb44_drive_main", "drive", True),)


def test_required_and_optional_nodes_can_both_be_present() -> None:
    requirements = (
        NodeRequirement("drive_main", "drive", True),
        NodeRequirement("sensor_front", "sensor", False),
    )
    report = evaluate_node_inventory(
        requirements,
        [_probe("COM7", "sensor_front", "sensor"), _probe("COM8", "drive_main", "drive")],
    )

    assert report.ready is True
    assert report.errors == ()
    assert report.warnings == ()


def test_missing_optional_node_warns_without_blocking_readiness() -> None:
    report = evaluate_node_inventory(
        (
            NodeRequirement("drive_main", "drive", True),
            NodeRequirement("sensor_front", "sensor", False),
        ),
        [_probe("COM8", "drive_main", "drive")],
    )

    assert report.ready is True
    assert [issue.code for issue in report.warnings] == ["missing_optional_node"]


def test_missing_required_node_blocks_readiness() -> None:
    report = evaluate_node_inventory(
        (NodeRequirement("drive_main", "drive", True),),
        [_probe("COM7", "sensor_front", "sensor")],
    )

    assert report.ready is False
    assert [issue.code for issue in report.errors] == ["missing_required_node"]
    assert [issue.code for issue in report.warnings] == ["unexpected_node"]


def test_duplicate_node_id_on_two_ports_blocks_readiness() -> None:
    report = evaluate_node_inventory(
        (NodeRequirement("drive_main", "drive", True),),
        [_probe("COM7", "drive_main", "drive"), _probe("COM8", "drive_main", "drive")],
    )

    assert report.ready is False
    assert [issue.code for issue in report.errors] == ["duplicate_node_id"]
    assert "COM7, COM8" in report.errors[0].message


def test_wrong_role_for_known_node_blocks_readiness() -> None:
    report = evaluate_node_inventory(
        (NodeRequirement("drive_main", "drive", True),),
        [_probe("COM7", "drive_main", "sensor")],
    )

    assert report.ready is False
    assert [issue.code for issue in report.errors] == ["wrong_role"]


def test_incomplete_identity_is_an_error_not_an_unexpected_node() -> None:
    report = evaluate_node_inventory(
        (),
        [SerialProbe(port="COM7", identity={"v": 1, "type": "node_identity", "node_id": "drive_main"})],
    )

    assert report.ready is False
    assert [issue.code for issue in report.errors] == ["invalid_identity"]
    assert report.warnings == ()


def test_unexpected_complete_node_is_visible_but_not_required() -> None:
    report = evaluate_node_inventory((), [_probe("COM9", "diagnostics", "debug")])

    assert report.ready is True
    assert [issue.code for issue in report.warnings] == ["unexpected_node"]


def test_manifest_rejects_duplicate_ids_and_non_boolean_required(tmp_path: Path) -> None:
    duplicate = _write_manifest(
        tmp_path / "duplicate.json",
        [
            {"node_id": "drive_main", "role": "drive", "required": True},
            {"node_id": "drive_main", "role": "drive", "required": False},
        ],
    )
    invalid_required = _write_manifest(
        tmp_path / "invalid-required.json",
        [{"node_id": "drive_main", "role": "drive", "required": 1}],
    )

    with pytest.raises(ValueError, match="duplicate node_id"):
        load_node_manifest(duplicate)
    with pytest.raises(ValueError, match="required must be boolean"):
        load_node_manifest(invalid_required)


def test_manifest_rejects_boolean_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "schema.json"
    path.write_text('{"schema_version": true, "nodes": []}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version must be 1"):
        load_node_manifest(path)


def test_inventory_format_is_stable_and_operator_readable() -> None:
    report = evaluate_node_inventory(
        (
            NodeRequirement("drive_main", "drive", True),
            NodeRequirement("sensor_front", "sensor", False),
        ),
        [_probe("COM8", "drive_main", "drive")],
    )

    text = format_node_inventory(report)

    assert text.splitlines()[0] == "node inventory: READY"
    assert "required node_id=drive_main role=drive status=PRESENT ports=COM8" in text
    assert "optional node_id=sensor_front role=sensor status=MISSING ports=-" in text
    assert "WARNING missing_optional_node:" in text


def test_list_nodes_manifest_blocks_when_required_node_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _write_manifest(
        tmp_path / "nodes.json",
        [{"node_id": "drive_main", "role": "drive", "required": True}],
    )
    monkeypatch.setattr("pc_controller.app.discover_serial_nodes", lambda timeout: [])

    with pytest.raises(RuntimeError, match="inventory is BLOCKED"):
        print_node_list(0.1, str(manifest))

    output = capsys.readouterr().out
    assert "serial nodes: 0" in output
    assert "node inventory: BLOCKED" in output
    assert "ERROR missing_required_node:" in output


def test_list_nodes_manifest_reports_ready_without_opening_control_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _write_manifest(
        tmp_path / "nodes.json",
        [{"node_id": "drive_main", "role": "drive", "required": True}],
    )
    monkeypatch.setattr(
        "pc_controller.app.discover_serial_nodes",
        lambda timeout: [_probe("COM8", "drive_main", "drive")],
    )

    print_node_list(0.1, str(manifest))

    output = capsys.readouterr().out
    assert "serial nodes: 1" in output
    assert "node inventory: READY" in output
    assert "required node_id=drive_main role=drive status=PRESENT ports=COM8" in output


def test_list_nodes_invalid_manifest_is_operator_facing_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "nodes.json"
    manifest.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("pc_controller.app.discover_serial_nodes", lambda timeout: [])

    with pytest.raises(RuntimeError, match="schema_version must be 1"):
        print_node_list(0.1, str(manifest))
