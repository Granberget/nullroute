"""The apt package repository.

Runner tools (probe, bypass, ...) are licensed in the agency store and then
installed with apt. A few classic fun packages are free for everyone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Pkg:
    name: str
    summary: str
    tool: bool = False          # licensed runner tool (version = store level)
    version: str = "1.0"        # fixed version for free packages
    size_kb: int = 400
    section: str = "games"


PACKAGES: dict[str, Pkg] = {
    "probe": Pkg("probe", "node scanner - shows ICE layers and breach estimates", True, size_kb=820, section="net"),
    "bypass": Pkg("bypass", "breach module for FIREWALL layers", True, size_kb=1400, section="net"),
    "decrypt": Pkg("decrypt", "breach module for CIPHER layers", True, size_kb=1900, section="net"),
    "spoof": Pkg("spoof", "breach module for GATEKEEPER layers", True, size_kb=2100, section="net"),
    "scrub": Pkg("scrub", "removes your footprint from a node", True, size_kb=640, section="net"),
    "tracemon": Pkg("tracemon", "status bar trace monitor", True, size_kb=310, section="net"),
    "cowsay": Pkg("cowsay", "configurable talking cow", version="3.03+dfsg2-8", size_kb=93),
    "fortune": Pkg("fortune", "provides fortune cookies on demand", version="1:1.99.1-7.3", size_kb=88),
    "figlet": Pkg("figlet", "make large character ASCII banners out of ordinary text", version="2.2.5-3", size_kb=240),
    "sl": Pkg("sl", "correct you if you type `sl' by mistake", version="5.02-1", size_kb=26),
    "htop": Pkg("htop", "interactive processes viewer", version="3.3.0-4", size_kb=420, section="utils"),
    "nmap": Pkg("nmap", "the Network Mapper - port scanner", version="7.94+git20230807-3",
                size_kb=4600, section="net"),
}

# commands that only exist once their package is installed
COMMAND_PKG = {"probe": "probe", "scrub": "scrub", "cowsay": "cowsay", "nmap": "nmap",
               "fortune": "fortune", "figlet": "figlet", "sl": "sl", "htop": "htop"}

REPO = "https://repo.blackrelay.net/debian"


def is_installed(state, name: str) -> bool:
    pkg = PACKAGES.get(name)
    if pkg is None:
        return False
    if pkg.tool:
        return state.sw.get(name, 0) > 0
    return name in state.extra_pkgs


def installed_version(state, name: str) -> str | None:
    pkg = PACKAGES[name]
    if not is_installed(state, name):
        return None
    return f"{state.sw[name]}.0" if pkg.tool else pkg.version


def repo_version(state, name: str) -> str | None:
    """Version apt knows about (as of the last 'apt update')."""
    pkg = PACKAGES[name]
    if not pkg.tool:
        return pkg.version
    level = state.apt_index.get(name, 0)
    return f"{level}.0" if level else None


def upgradable(state) -> list[str]:
    out = []
    for name, pkg in PACKAGES.items():
        if pkg.tool and is_installed(state, name) and state.apt_index.get(name, 0) > state.sw.get(name, 0):
            out.append(name)
    return out


def pending_update(state) -> int:
    """Licences bought since the last 'apt update'."""
    return sum(1 for k, v in state.pkgs_owned.items() if v > state.apt_index.get(k, 0))


def install(state, name: str) -> None:
    pkg = PACKAGES[name]
    if pkg.tool:
        state.sw[name] = state.apt_index.get(name, 0)
    else:
        state.extra_pkgs.add(name)


def remove(state, name: str) -> None:
    pkg = PACKAGES[name]
    if pkg.tool:
        state.sw[name] = 0
    else:
        state.extra_pkgs.discard(name)
