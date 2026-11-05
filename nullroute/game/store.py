"""Hardware and software for sale on the agency store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Item:
    key: str          # hw/sw key in GameState
    level: int
    name: str
    price: int
    kind: str         # "hardware" or "software"
    desc: str


CATALOG: list[Item] = [
    # hardware
    Item("cpu", 2, "CPU: Quad-core 4.2 GHz", 3000, "hardware", "Breach programs run 1.8x faster."),
    Item("cpu", 3, "CPU: Octa-core 5.0 GHz", 9000, "hardware", "Breach programs run 3x faster."),
    Item("cpu", 4, "CPU: Quantum co-processor", 24000, "hardware", "Breach programs run 5x faster."),
    Item("nic", 2, "Network: 10 Gbit fibre", 2500, "hardware", "Transfers run 3x faster."),
    Item("nic", 3, "Network: Optical backbone tap", 8000, "hardware", "Transfers run 8x faster."),
    Item("disk", 2, "Storage: 1 TB", 1500, "hardware", "Gateway storage 200 MB -> 1 GB."),
    Item("disk", 3, "Storage: 10 TB array", 5000, "hardware", "Gateway storage -> 10 GB."),
    # software
    Item("bypass", 2, "bypass v2", 3500, "software", "Breaks FIREWALL layers up to strength 4."),
    Item("bypass", 3, "bypass v3", 11000, "software", "Breaks any FIREWALL layer."),
    Item("decrypt", 1, "decrypt v1", 2000, "software", "Breaks CIPHER layers up to strength 2."),
    Item("decrypt", 2, "decrypt v2", 6000, "software", "Breaks CIPHER layers up to strength 4."),
    Item("decrypt", 3, "decrypt v3", 14000, "software", "Breaks any CIPHER layer."),
    Item("spoof", 1, "spoof v1", 3000, "software", "Breaks GATEKEEPER layers up to strength 2."),
    Item("spoof", 2, "spoof v2", 8000, "software", "Breaks GATEKEEPER layers up to strength 4."),
    Item("spoof", 3, "spoof v3", 18000, "software", "Breaks any GATEKEEPER layer."),
    Item("scrub", 2, "scrub v2", 4000, "software", "Removes your footprint twice as fast."),
    Item("tracemon", 2, "tracemon v2", 1500, "software", "Shows trace progress as a percentage."),
    Item("tracemon", 3, "tracemon v3", 5000, "software", "Shows seconds left until the trace completes."),
    Item("probe", 2, "probe v2", 2000, "software", "Probe also shows the node's security rating and trace speed."),
]

CPU_SPEED = {1: 1.0, 2: 1.8, 3: 3.0, 4: 5.0}
NIC_SPEED = {1: 1.0, 2: 3.0, 3: 8.0}          # MB per real second
DISK_SIZE = {1: 200_000_000, 2: 1_000_000_000, 3: 10_000_000_000}


def max_strength(version: int) -> int:
    """Highest ICE strength a program version can break."""
    return {0: 0, 1: 2, 2: 4, 3: 5}.get(version, 5)


def available(state) -> list[Item]:
    """Items that are the next upgrade for their key."""
    return [i for i in CATALOG if i.level == _current(state, i) + 1]


def _current(state, item: Item) -> int:
    if item.kind == "hardware":
        return state.hw.get(item.key, 1)
    return state.pkgs_owned.get(item.key, 0)      # licence level, installed via apt


def owned(state, item: Item) -> bool:
    return _current(state, item) >= item.level


def buy(state, item: Item) -> str:
    if owned(state, item):
        return "You already own that."
    if item.level != _current(state, item) + 1:
        return "Buy the previous version first."
    if state.money < item.price:
        return f"Not enough credits (need ¢{item.price:,})."
    state.money -= item.price
    if item.kind == "hardware":
        state.hw[item.key] = item.level
        return f"Purchased {item.name}. It is installed in your gateway already."
    state.pkgs_owned[item.key] = item.level
    return (f"Purchased {item.name}. Install it on your gateway: "
            f"sudo apt update && sudo apt install {item.key}")
