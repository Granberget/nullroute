"""Persistent game state and save/load."""

from __future__ import annotations

import gzip
import os
import pickle
import random
from dataclasses import dataclass, field
from pathlib import Path

from .world import AGENCY, DROP, GATEWAY, SANDBOX, World, build_world

SAVE_VERSION = 2

RATING_TITLES = [(0, "Script Kiddie"), (10, "Novice"), (30, "Runner"),
                 (70, "Specialist"), (140, "Netwalker"), (250, "Ghost"),
                 (400, "Legend")]


@dataclass
class Mail:
    id: int
    sender: str
    subject: str
    body: str
    time: float
    read: bool = False


@dataclass
class SentMail:
    to: list[str]
    subject: str
    body: str
    attachments: list[tuple[str, str, int]]     # (name, tag, size)
    time: float


@dataclass
class News:
    time: float
    headline: str
    body: str


@dataclass
class GameState:
    handle: str
    world: World
    minutes: float = 0.0
    money: int = 1000
    rating: int = 0
    strikes: int = 0
    hw: dict[str, int] = field(default_factory=lambda: {"cpu": 1, "nic": 1, "disk": 1})
    sw: dict[str, int] = field(default_factory=lambda: {
        "probe": 1, "bypass": 1, "decrypt": 0, "spoof": 0, "scrub": 1, "tracemon": 1})
    route: list[str] = field(default_factory=list)
    known: set[str] = field(default_factory=set)
    mail: list[Mail] = field(default_factory=list)
    news: list[News] = field(default_factory=list)
    contracts: list = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    tutorial_step: int = 0
    tutorial_done: bool = False
    next_contract_at: float = 0.0
    counter: int = 0
    game_over: str = ""
    seed: int = 0
    version: int = SAVE_VERSION
    rng: random.Random = field(default_factory=random.Random)
    # gateway administration
    password: str = ""                                   # your sudo password
    pkgs_owned: dict[str, int] = field(default_factory=dict)   # store licences
    apt_index: dict[str, int] = field(default_factory=dict)    # as of 'apt update'
    extra_pkgs: set[str] = field(default_factory=set)          # free packages
    # learning
    achievements: dict[str, float] = field(default_factory=dict)
    tips_seen: set[str] = field(default_factory=set)
    tips_enabled: bool = True
    lessons_done: set[int] = field(default_factory=set)
    lesson_current: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    sent: list = field(default_factory=list)                   # SentMail

    def next_id(self) -> int:
        self.counter += 1
        return self.counter

    @property
    def rating_level(self) -> int:
        level = 0
        for i, (pts, _) in enumerate(RATING_TITLES):
            if self.rating >= pts:
                level = i
        return level

    @property
    def rating_title(self) -> str:
        return RATING_TITLES[self.rating_level][1]

    @property
    def unread(self) -> int:
        return sum(1 for m in self.mail if not m.read)

    @property
    def home(self) -> str:
        return f"/home/{self.handle}"


def new_state(handle: str, seed: int | None = None, password: str = "") -> GameState:
    world = build_world(handle, seed)
    s = GameState(handle=handle, world=world, seed=world.seed)
    s.rng = random.Random(world.seed + 1)
    s.known = {GATEWAY, AGENCY, DROP, SANDBOX} | set(world.relays)
    s.password = password
    migrate(s)
    return s


_DEFAULTS = {
    "password": "", "extra_pkgs": set, "achievements": dict, "tips_seen": set,
    "tips_enabled": True, "lessons_done": set, "lesson_current": 0, "counters": dict,
    "sent": list,
}


def migrate(s: GameState) -> GameState:
    """Bring older saves up to date and make sure the gateway is set up."""
    for name, default in _DEFAULTS.items():
        if not hasattr(s, name):
            setattr(s, name, default() if callable(default) else default)
    if not hasattr(s, "pkgs_owned") or not s.pkgs_owned:
        s.pkgs_owned = {k: v for k, v in s.sw.items() if v > 0}
    if not hasattr(s, "apt_index") or not s.apt_index:
        s.apt_index = dict(s.pkgs_owned)
    from .world import prepare_gateway
    prepare_gateway(s)
    return s


# ---------------------------------------------------------------- save / load
def save_dir() -> Path:
    base = os.environ.get("NULLROUTE_HOME")
    path = Path(base) if base else Path.home() / ".nullroute"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_path(handle: str) -> Path:
    safe = "".join(c for c in handle if c.isalnum() or c in "-_") or "runner"
    return save_dir() / f"{safe}.sav"


def save(state: GameState) -> Path:
    path = save_path(state.handle)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wb") as fh:
        pickle.dump(state, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    return path


def load(handle: str) -> GameState:
    with gzip.open(save_path(handle), "rb") as fh:
        state = pickle.load(fh)
    if getattr(state, "version", 0) != SAVE_VERSION:
        raise ValueError("save file is from an incompatible version")
    return migrate(state)


def list_saves() -> list[str]:
    return sorted(p.stem for p in save_dir().glob("*.sav"))


def delete_save(handle: str) -> None:
    p = save_path(handle)
    if p.exists():
        p.unlink()
