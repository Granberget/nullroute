"""Nodes (servers), their ICE layers and the corporations that own them."""

from __future__ import annotations

from dataclasses import dataclass, field

from .vfs import VFS

# ICE layer type -> program that breaks it
LAYER_PROGRAM = {"firewall": "bypass", "cipher": "decrypt", "gatekeeper": "spoof"}
LAYER_DESC = {
    "firewall": "FIREWALL   - blocks foreign connections",
    "cipher": "CIPHER     - encrypted session layer",
    "gatekeeper": "GATEKEEPER - identity verification",
}


@dataclass
class Layer:
    kind: str          # firewall, cipher, gatekeeper
    strength: int      # 1..5

    @property
    def program(self) -> str:
        return LAYER_PROGRAM[self.kind]


@dataclass
class Corp:
    id: str
    name: str
    domain: str
    sec: int
    city: str
    nodes: list[str] = field(default_factory=list)
    staff: list[str] = field(default_factory=list)


KIND_LABEL = {
    "gateway": "Your gateway",
    "relay": "Public relay",
    "agency": "Agency BBS",
    "drop": "Agency drop",
    "sandbox": "Training node",
    "front": "Corporate front node",
    "core": "Corporate core node",
}


class Node:
    def __init__(self, hostname: str, ip: str, kind: str, sec: int = 0,
                 corp: str | None = None, title: str = "",
                 loc: tuple[int, int] = (0, 0)):
        self.hostname = hostname
        self.ip = ip
        self.kind = kind
        self.sec = sec
        self.corp = corp
        self.title = title
        self.loc = loc
        self.layers: list[Layer] = []
        self.parent: str | None = None     # core nodes: only reachable from this node
        self.public = False                # relays: anyone may route through
        self.motd = ""
        self.fs: VFS | None = None
        # runtime state
        self.breached_until = 0.0
        self.trace_active = False
        self.trace_progress = 0.0
        self.alarm_until = 0.0
        self.footprint = 0.0              # 0..100, evidence you were here
        self.footprint_hops = 0           # route length when footprint was left
        self.check_at = 0.0               # when the owner reviews the node

    @property
    def short(self) -> str:
        return self.hostname.split(".")[0]

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def needs_breach(self) -> bool:
        return bool(self.layers)

    def is_open(self, now: float) -> bool:
        return not self.layers or now < self.breached_until
