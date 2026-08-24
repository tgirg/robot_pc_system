"""Serial node discovery for multi-ESP32 setups."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .protocol import ProtocolError, decode_line, encode_message, hello_message, who_are_you_message
from .serial_link import SerialLink


@dataclass
class SerialProbe:
    """Result of probing one serial port."""

    port: str
    identity: dict[str, Any] | None = None
    error: str | None = None
    link: SerialLink | None = None

    @property
    def node_id(self) -> str:
        return str((self.identity or {}).get("node_id", ""))

    @property
    def role(self) -> str:
        return str((self.identity or {}).get("role", ""))


SerialLinkFactory = Callable[..., SerialLink]


class SerialDiscoveryError(RuntimeError):
    """Base error for a serial discovery result that cannot be selected."""


class NoMatchingSerialNodeError(SerialDiscoveryError):
    """No discovered node matched the requested identity."""


class AmbiguousSerialNodeError(SerialDiscoveryError):
    """More than one discovered node matched the requested identity."""


def normalize_identity(message: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalized identity object for known discovery replies."""
    message_type = str(message.get("type", ""))
    if message_type == "node_identity":
        return dict(message)

    if message_type in {"hello", "hello_ack"} and ("node_id" in message or "role" in message):
        identity = dict(message)
        identity["type"] = "node_identity"
        return identity

    # Legacy MCB44 firmware only returned hello_ack. Treat it as the drive board
    # so old flashed firmware can still be found, then let config/ARM checks decide.
    if message_type == "hello_ack" and str(message.get("firmware", "")) == "mcb44_4wis":
        identity = dict(message)
        identity.update(
            {
                "type": "node_identity",
                "node_id": "legacy_mcb44_drive",
                "board": "MCB44",
                "role": "drive",
                "protocol": "mcb44-json-serial",
            }
        )
        return identity

    return None


def discover_serial_nodes(
    ports: Iterable[str] | None = None,
    *,
    timeout: float = 1.2,
    link_factory: SerialLinkFactory = SerialLink,
    keep_links: bool = False,
    trace: bool | None = None,
) -> list[SerialProbe]:
    """Probe serial ports and return identity responses from robot nodes."""
    resolved_ports = list(ports) if ports is not None else SerialLink.available_ports()
    probes: list[SerialProbe] = []
    for port in resolved_ports:
        probe = _probe_port(port, timeout=timeout, link_factory=link_factory, keep_link=keep_links, trace=trace)
        probes.append(probe)
    return probes


def open_discovered_serial_link(
    *,
    role: str = "drive",
    node_id: str | None = None,
    ports: Iterable[str] | None = None,
    timeout: float = 1.2,
    link_factory: SerialLinkFactory = SerialLink,
    trace: bool | None = None,
) -> SerialProbe:
    """Open the one serial node matching role or node_id."""
    probes = discover_serial_nodes(
        ports,
        timeout=timeout,
        link_factory=link_factory,
        keep_links=True,
        trace=trace,
    )
    matches = [probe for probe in probes if _probe_matches(probe, role=role, node_id=node_id)]
    nonmatches = [probe for probe in probes if probe not in matches]

    if len(matches) == 1:
        for probe in nonmatches:
            _close_probe_link(probe)
        return matches[0]

    for probe in probes:
        _close_probe_link(probe)

    target = f"node_id={node_id}" if node_id else f"role={role}"
    summary = format_probe_summary(probes)
    if not matches:
        raise NoMatchingSerialNodeError(f"no serial node matched {target}. Probed nodes:\n{summary}")
    raise AmbiguousSerialNodeError(
        f"multiple serial nodes matched {target}. Use --node-id or --port. Probed nodes:\n{summary}"
    )


def format_probe_summary(probes: Iterable[SerialProbe]) -> str:
    """Format probe results for logs and error messages."""
    lines: list[str] = []
    for probe in probes:
        if probe.identity:
            identity = probe.identity
            lines.append(
                f"{probe.port}: node_id={identity.get('node_id', '?')} "
                f"role={identity.get('role', '?')} board={identity.get('board', '?')} "
                f"firmware={identity.get('firmware', '?')}"
            )
        elif probe.error:
            lines.append(f"{probe.port}: error={probe.error}")
        else:
            lines.append(f"{probe.port}: no robot identity")
    return "\n".join(lines) if lines else "no serial ports found"


def _probe_port(
    port: str,
    *,
    timeout: float,
    link_factory: SerialLinkFactory,
    keep_link: bool,
    trace: bool | None,
) -> SerialProbe:
    try:
        link = link_factory(port, timeout=0.02, open_settle_seconds=1.5, trace=trace)
    except Exception as exc:
        return SerialProbe(port=port, error=str(exc))

    try:
        for request in (who_are_you_message(), hello_message()):
            link.write(encode_message(request))
            identity = _read_identity(link, timeout)
            if identity is not None:
                return SerialProbe(port=port, identity=identity, link=link if keep_link else None)
        return SerialProbe(port=port, link=link if keep_link else None)
    finally:
        if not keep_link:
            link.close()


def _read_identity(link: SerialLink, timeout: float) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(0.05, timeout)
    while time.monotonic() < deadline:
        for line in link.read_lines():
            try:
                message = decode_line(line)
            except ProtocolError:
                continue
            identity = normalize_identity(message)
            if identity is not None:
                return identity
        time.sleep(0.02)
    return None


def _probe_matches(probe: SerialProbe, *, role: str, node_id: str | None) -> bool:
    if not probe.identity:
        return False
    if node_id:
        return probe.node_id == node_id and probe.role == role
    return probe.role == role


def _close_probe_link(probe: SerialProbe) -> None:
    if probe.link is None:
        return
    probe.link.close()
    probe.link = None
