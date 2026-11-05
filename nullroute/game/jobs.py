"""The contract watch panel ('contracts -f').

Everything here is worked out from the live game state, so the checklist
ticks itself off while the player works in another terminal.
"""

from __future__ import annotations

import re

from . import clock
from . import contracts as C
from .vfs import File
from .world import GATEWAY

Line = tuple[str, "str | None"]

OK, TODO, NOW, WARN = "[x]", "[ ]", "[>]", "[!]"

# lines in a briefing that are commands the player can copy and run
_CMD = re.compile(r"^\s+(scp|mail|echo|grep|nano|find|cat|ls|ssh|breach|probe)\b")


def _bar(frac: float, width: int) -> str:
    full = int(max(0.0, min(1.0, frac)) * width)
    return "[" + "█" * full + "░" * (width - full) + "]"


def active(game) -> list[C.Contract]:
    return [c for c in game.state.contracts if c.status == "accepted"]


def _online(game, hostname: str) -> bool:
    return any(c.target == hostname and c.kind == "shell" for c in game.conns)


def _node_lines(game, hostname: str, inside: bool = False) -> list[tuple[bool, str]]:
    """Breach / log in steps for one node: (done, text). 'inside' means the
    player is already further in, so this hop is done whatever its ICE does."""
    world = game.world
    node = world.nodes[hostname]
    ref = world.ref(node)
    online = inside or _online(game, hostname)
    out: list[tuple[bool, str]] = []
    if node.needs_breach:
        if node.is_open(game.now):
            left = clock.fmt_duration(node.breached_until - game.now)
            out.append((True, f"ICE down on {ref}  (open {left} more)"))
        elif online:
            out.append((True, f"ICE down on {ref}"))
        else:
            out.append((False, f"Break the ICE:  breach {ref}"))
    out.append((online, f"Logged in on {ref}" if online else f"Log in:  ssh {ref}"))
    return out


def file_name(game, c: C.Contract) -> str:
    if c.path:
        return c.path.rsplit("/", 1)[-1]
    node = game.world.nodes.get(c.target)
    f = node.fs.find_tag(c.tag) if node and node.fs and c.tag else None
    return f.name if f else "the file"


def _goal_lines(game, c: C.Contract) -> list[tuple[bool, str]]:
    """The job itself, then the report."""
    world = game.world
    fname = file_name(game, c)
    met = C.objective_met(c, world)
    if c.kind in ("retrieve", "training"):
        home = world.nodes[GATEWAY].fs.find_tag(c.tag) is not None
        return [(home or met, f"Copy {fname} to your gateway (scp, on the node)"),
                (met, f"Mail it as an attachment to {c.client_addr}")]
    if c.kind == "wipe":
        return [(met, f"Delete {fname} - and every copy of it on the node"),
                (False, f"Confirm by mail to {c.client_addr}")]
    if c.kind == "modify":
        text = f"Set {c.field} of {c.row} to '{c.value}'"
        if not met and f"ssh:{c.target}" in game.state.flags:
            # once you have been there, the panel can tell you what it says now
            now_val = C.registry_value(world.nodes[c.target], c.row, c.field)
            if now_val is not None:
                text += f"  (now: '{now_val}')"
        return [(met, text), (False, f"Confirm by mail to {c.client_addr}")]
    if c.kind == "plant":
        return [(met, f"Upload {fname} to {c.path.rsplit('/', 1)[0]}/")]
    if c.kind == "find":
        tries = f"  ({3 - c.attempts} of 3 tries left)" if c.attempts else ""
        return [(False, "Find the passphrase - it looks like word-word-NN"),
                (False, f"Mail it to {c.client_addr}{tries}")]
    return []


def checklist(game, c: C.Contract) -> list[tuple[str, str]]:
    """(mark, text) rows. The first unfinished row is marked as the next step."""
    world = game.world
    node = world.nodes[c.target]
    rows: list[tuple[bool, str]] = []
    goal = _goal_lines(game, c)
    goal_done = bool(goal) and goal[0][0]
    if not goal_done:
        # the way in only matters until the job itself is done
        inside = _online(game, c.target)
        if node.parent:
            rows += _node_lines(game, node.parent, inside)
        rows += _node_lines(game, c.target)
    rows += goal
    out: list[tuple[str, str]] = []
    nxt = True
    for done, text in rows:
        if done:
            out.append((OK, text))
        elif nxt:
            out.append((NOW, text))
            nxt = False
        else:
            out.append((TODO, text))
    # footprints are never "done" by themselves - warn while there is one
    for host in filter(None, [node.parent, c.target]):
        n = world.nodes[host]
        if n.footprint > 0:
            out.append((WARN, f"Footprint {n.footprint:.0f}% on {world.ref(n)} - "
                              "scrub before you exit"))
    return out


def commands(c: C.Contract) -> list[str]:
    """Copyable command lines from the briefing."""
    out = []
    for line in c.brief.splitlines():
        if line[:1].strip() and not line.startswith("Tip:"):
            continue        # 'Goal: ...', 'Steps: ...' - prose, not commands
        # briefings put commands in chunks separated by 2+ spaces, next to
        # notes like '(on the node)' or 'Tip: ... then ...'
        for chunk in re.split(r"\s{2,}", line.removeprefix("Tip:").strip()):
            if _CMD.match(" " + chunk) and chunk not in out:
                out.append(chunk)
    return out


def _deadline(game, c: C.Contract) -> tuple[str, str | None]:
    left = c.deadline - game.now
    if c.kind == "training":
        return "no deadline", "dim"
    style = "error" if left < 6 * 60 else "warn" if left < 24 * 60 else None
    return f"{clock.fmt_duration(left)} left", style


def render(game, only: str | None = None, finished: list[C.Contract] | None = None,
           width: int = 60) -> list[Line]:
    """The whole watch panel."""
    out: list[Line] = []
    trace = game.active_trace()
    if trace:
        # show no more than the player's tracemon can tell (like the status bar)
        n, conn = trace
        lvl = game.state.sw.get("tracemon", 1)
        text = f"TRACE running on {game.world.ref(n)}"
        if lvl >= 2:
            text += f"  {_bar(n.trace_progress, 20)} {n.trace_progress * 100:3.0f}%"
        if lvl >= 3:
            left = (1 - n.trace_progress) * game.trace_seconds(n, conn.path)
            text += f"  {left:4.1f}s"
        if lvl >= 2 and n.trace_progress > 0.5:
            text += "  - get out!"
        out.append((text, "alert"))
        out.append(("", None))

    mine = active(game)
    if only:
        mine = [c for c in mine if c.id.lower() == only.lower()]
    for c in finished or []:
        if only and c.id.lower() != only.lower():
            continue
        if c.status == "done":
            out.append((f"{c.id}  DONE - ¢{c.pay:,} paid.  {c.title}", "good"))
        else:
            out.append((f"{c.id}  FAILED.  {c.title}", "error"))
    if finished:
        out.append(("", None))

    if not mine:
        if only:
            out.append((f"Contract {only} is not active.", "dim"))
        else:
            out.append(("No active contracts.", "title"))
            out.append(("Take a job on the agency board:  ssh blackrelay.net", None))
            out.append(("This panel picks it up by itself.", "dim"))
        out.append(("", None))
        out.append(("Updates by itself. Ctrl+C stops it.", "dim"))
        return out

    for c in mine:
        dl, dl_style = _deadline(game, c)
        out.append((f"{c.id}  {c.label.upper()}  ¢{c.pay:,}", "title"))
        out.append((f"  {c.title}", None))
        out.append((f"  Target: {c.target}   Deadline: {dl}", dl_style))
        if c.path and c.kind != "find":
            out.append((f"  File:   {c.path}", None))
        if c.kind == "modify":
            out.append((f"  Change: {c.field} of {c.row} -> '{c.value}'", None))
        out.append(("", None))
        for mark, text in checklist(game, c):
            style = {OK: "dim", NOW: "bold", WARN: "warn"}.get(mark)
            out.append((f"  {mark} {text}", style))
        cmds = commands(c)
        if cmds:
            out.append(("", None))
            out.append(("  Commands (select, Ctrl+Shift+C, right-click to paste):", "dim"))
            for cmd in cmds:
                out.append((f"    {cmd}", "info"))
        out.append(("", None))
        out.append(("─" * min(width, 60), "dim"))

    out.append((f"Full briefing: contracts {mine[0].id}" if len(mine) == 1
                else "Full briefing: contracts <id>", "dim"))
    out.append(("Updates by itself. Ctrl+C stops it.", "dim"))
    return out
