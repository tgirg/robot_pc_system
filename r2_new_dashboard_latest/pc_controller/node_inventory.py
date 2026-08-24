"""Fail-closed inventory checks for multiple serial robot nodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .serial_discovery import SerialProbe


@dataclass(frozen=True)
class NodeRequirement:
    """One expected robot node and whether it is required for readiness."""

    node_id: str
    role: str
    required: bool = True


@dataclass(frozen=True)
class NodeInventoryIssue:
    """One deterministic inventory validation result."""

    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class NodeInventoryReport:
    """Validated snapshot of expected and discovered serial nodes."""

    requirements: tuple[NodeRequirement, ...]
    probes: tuple[SerialProbe, ...]
    issues: tuple[NodeInventoryIssue, ...]

    @property
    def errors(self) -> tuple[NodeInventoryIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[NodeInventoryIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def ready(self) -> bool:
        return not self.errors


def load_node_manifest(path: str | Path) -> tuple[NodeRequirement, ...]:
    """Load and strictly validate a versioned node manifest."""
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read node manifest {manifest_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("node manifest root must be an object")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("node manifest schema_version must be 1")
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("node manifest nodes must be a list")

    requirements: list[NodeRequirement] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ValueError(f"node manifest nodes[{index}] must be an object")
        node_id = raw.get("node_id")
        role = raw.get("role")
        required = raw.get("required", True)
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError(f"node manifest nodes[{index}].node_id must be a non-empty string")
        if not isinstance(role, str) or not role.strip():
            raise ValueError(f"node manifest nodes[{index}].role must be a non-empty string")
        if not isinstance(required, bool):
            raise ValueError(f"node manifest nodes[{index}].required must be boolean")
        normalized_id = node_id.strip()
        normalized_role = role.strip()
        if normalized_id in seen_ids:
            raise ValueError(f"duplicate node_id in manifest: {normalized_id}")
        seen_ids.add(normalized_id)
        requirements.append(NodeRequirement(normalized_id, normalized_role, required))

    return tuple(requirements)


def evaluate_node_inventory(
    requirements: Iterable[NodeRequirement],
    probes: Iterable[SerialProbe],
) -> NodeInventoryReport:
    """Compare discovered identities with required/optional node policy."""
    requirement_items = tuple(requirements)
    probe_items = tuple(probes)
    _validate_requirements(requirement_items)

    issues: list[NodeInventoryIssue] = []
    by_node_id: dict[str, list[SerialProbe]] = {}
    for probe in probe_items:
        identity = probe.identity
        if identity is None:
            if probe.error:
                issues.append(
                    NodeInventoryIssue(
                        "warning",
                        "probe_error",
                        f"{probe.port}: serial probe error: {probe.error}",
                    )
                )
            else:
                issues.append(
                    NodeInventoryIssue(
                        "warning",
                        "unidentified_port",
                        f"{probe.port}: no robot identity",
                    )
                )
            continue
        node_id = identity.get("node_id")
        role = identity.get("role")
        if not isinstance(node_id, str) or not node_id.strip() or not isinstance(role, str) or not role.strip():
            issues.append(
                NodeInventoryIssue(
                    "error",
                    "invalid_identity",
                    f"{probe.port}: identity must contain non-empty node_id and role",
                )
            )
            continue
        by_node_id.setdefault(node_id.strip(), []).append(probe)

    for node_id, matches in sorted(by_node_id.items()):
        if len(matches) > 1:
            ports = ", ".join(sorted(probe.port for probe in matches))
            issues.append(
                NodeInventoryIssue(
                    "error",
                    "duplicate_node_id",
                    f"node_id={node_id} appeared on multiple ports: {ports}",
                )
            )

    requirement_by_id = {item.node_id: item for item in requirement_items}
    for requirement in sorted(requirement_items, key=lambda item: item.node_id):
        matches = by_node_id.get(requirement.node_id, [])
        if not matches:
            severity = "error" if requirement.required else "warning"
            code = "missing_required_node" if requirement.required else "missing_optional_node"
            kind = "required" if requirement.required else "optional"
            issues.append(
                NodeInventoryIssue(
                    severity,
                    code,
                    f"{kind} node missing: node_id={requirement.node_id} role={requirement.role}",
                )
            )
            continue
        observed_roles = sorted(
            {
                str((probe.identity or {}).get("role", "")).strip()
                for probe in matches
                if str((probe.identity or {}).get("role", "")).strip()
            }
        )
        wrong_roles = [role for role in observed_roles if role != requirement.role]
        if wrong_roles:
            issues.append(
                NodeInventoryIssue(
                    "error",
                    "wrong_role",
                    f"node_id={requirement.node_id} expected role={requirement.role}, "
                    f"observed role={','.join(wrong_roles)}",
                )
            )

    for node_id, matches in sorted(by_node_id.items()):
        if node_id in requirement_by_id:
            continue
        roles = sorted({str((probe.identity or {}).get("role", "")) for probe in matches})
        ports = ", ".join(sorted(probe.port for probe in matches))
        issues.append(
            NodeInventoryIssue(
                "warning",
                "unexpected_node",
                f"unexpected node: node_id={node_id} role={','.join(roles)} ports={ports}",
            )
        )

    severity_order = {"error": 0, "warning": 1}
    issues.sort(key=lambda issue: (severity_order[issue.severity], issue.code, issue.message))
    return NodeInventoryReport(requirement_items, probe_items, tuple(issues))


def format_node_inventory(report: NodeInventoryReport) -> str:
    """Render one stable operator-facing inventory summary."""
    lines = [f"node inventory: {'READY' if report.ready else 'BLOCKED'}"]
    discovered_by_id: dict[str, list[SerialProbe]] = {}
    for probe in report.probes:
        if probe.identity and isinstance(probe.identity.get("node_id"), str):
            discovered_by_id.setdefault(str(probe.identity["node_id"]), []).append(probe)

    for requirement in sorted(report.requirements, key=lambda item: item.node_id):
        matches = discovered_by_id.get(requirement.node_id, [])
        kind = "required" if requirement.required else "optional"
        if not matches:
            status = "MISSING"
            locations = "ports=-"
        else:
            roles = {str((probe.identity or {}).get("role", "")) for probe in matches}
            if len(matches) > 1:
                status = "DUPLICATE"
            elif roles != {requirement.role}:
                status = "WRONG_ROLE"
            else:
                status = "PRESENT"
            locations = f"ports={','.join(sorted(probe.port for probe in matches))}"
        lines.append(
            f"{kind} node_id={requirement.node_id} role={requirement.role} "
            f"status={status} {locations}"
        )

    for issue in report.issues:
        lines.append(f"{issue.severity.upper()} {issue.code}: {issue.message}")
    return "\n".join(lines)


def _validate_requirements(requirements: tuple[NodeRequirement, ...]) -> None:
    seen_ids: set[str] = set()
    for requirement in requirements:
        if not requirement.node_id or not requirement.role:
            raise ValueError("node requirements need non-empty node_id and role")
        if not isinstance(requirement.required, bool):
            raise ValueError("node requirement required must be boolean")
        if requirement.node_id in seen_ids:
            raise ValueError(f"duplicate node_id in requirements: {requirement.node_id}")
        seen_ids.add(requirement.node_id)
