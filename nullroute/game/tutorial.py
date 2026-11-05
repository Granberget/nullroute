"""Guided tutorial. Each step completes when its condition becomes true."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .world import AGENCY, GATEWAY, SANDBOX


@dataclass
class Step:
    title: str
    text: str
    done: Callable[[object], bool]


def _flag(name: str) -> Callable[[object], bool]:
    return lambda g: name in g.state.flags


STEPS: list[Step] = [
    Step("Split the screen (optional)",
         "Keep this guide open while you work. Press  Ctrl+N  to open a second\n"
         "terminal, then type in ONE of them:\n"
         "  tutorial -f\n"
         "That terminal now follows the tutorial and updates by itself. Work in\n"
         "the other one - Alt+←/→ (or F2) switches, Ctrl+C stops the guide.\n"
         "(Rather keep one terminal? Just type  mail  to move on.)",
         lambda g: "tutorial_follow" in g.state.flags or "mail" in g.state.flags),
    Step("Read your mail",
         "Type  mail  to open your inbox. Press q to close it again.",
         _flag("mail")),
    Step("Visit the agency",
         f"Log in to the agency BBS:  ssh {AGENCY}\n"
         "Have a look at the Contracts tab - your training job T0 is already\n"
         "accepted. The Docs tab explains everything in more detail.",
         _flag("bbs")),
    Step("Probe the target",
         f"Scan the training node to see what protects it:\n  probe {SANDBOX}",
         _flag(f"probe:{SANDBOX}")),
    Step("Build a bounce route",
         "Every relay in your route makes you slower to trace.\n"
         "  cat relays.txt          list public relays\n"
         "  route add tallinn.relay\n  route add osaka.relay\n"
         "  route                   show the route",
         lambda g: len(g.state.route) >= 2),
    Step("Breach the node",
         "Run your breach programs against the ICE:\n  breach sandbox\n"
         "The node notices you the moment you start - watch the TRACE meter.",
         _flag(f"breach:{SANDBOX}")),
    Step("Connect",
         "The ICE is down. Log in:\n  ssh sandbox",
         _flag(f"ssh:{SANDBOX}")),
    Step("Copy the payload home",
         "Find training_payload.dat and copy it to your own gateway:\n"
         "  find /data -name '*.dat'\n"
         "  cd <directory it is in>\n"
         "  scp training_payload.dat gateway:~/downloads/",
         lambda g: "contract:T0" in g.state.flags or
         g.world.nodes[GATEWAY].fs.find_tag("sandbox-payload") is not None),
    Step("Scrub your footprint",
         "You left traces on this node. Remove them before you leave:\n  scrub",
         _flag(f"scrub:{SANDBOX}")),
    Step("Disconnect",
         "Type  exit  to drop the connection and return to your gateway.",
         _flag("home_after_scrub")),
    Step("Mail it to Vex",
         "Clients want their files by mail. Attach it with -A:\n"
         "  mail -A ~/downloads/training_payload.dat vex@blackrelay.net\n"
         "Type a line of text if you like, then a single '.' to send.\n"
         "(or pipe the text in:  echo here | mail -A ... vex@blackrelay.net)",
         _flag("contract:T0")),
    Step("Buy your first upgrade",
         "Corp nodes above the easiest tier have CIPHER layers, and you need\n"
         "'decrypt' for those. You just earned enough for it:\n"
         f"  ssh {AGENCY}      then press 2 (Store), pick 'decrypt v1', press b",
         _flag("bought:decrypt")),
    Step("Install it with apt",
         "Software on Linux is installed with a package manager. It changes the\n"
         "system, so it needs root - that's what sudo is for:\n"
         "  sudo apt update            refresh the list of packages\n"
         "  sudo apt install decrypt   install it\n"
         "sudo asks for YOUR password (the one you picked at the start).\n"
         "decrypt is a breach module: you don't run it by hand, 'breach HOST'\n"
         "loads it for every CIPHER layer. Type  decrypt  to check its version.",
         _flag("installed:decrypt")),
]


def current(game) -> Step | None:
    s = game.state
    if s.tutorial_done or s.tutorial_step >= len(STEPS):
        return None
    return STEPS[s.tutorial_step]


COMPLETE = ("TUTORIAL COMPLETE. Real contracts are waiting on the agency board. "
            "Want to sharpen your Linux skills? Type 'learn'.")


def heading(game) -> str:
    """'3/13: Probe the target' for the current step ('' when finished)."""
    step = current(game)
    if step is None:
        return ""
    return f"{game.state.tutorial_step + 1}/{len(STEPS)}: {step.title}"


def step_lines(step: Step) -> list[str]:
    """The step text with prose lines joined into paragraphs, so a narrow
    terminal can wrap them itself. Indented lines (commands) stay as they are."""
    out: list[str] = []
    prose = False
    for line in step.text.splitlines():
        if prose and line and not line.startswith(" "):
            out[-1] += " " + line
        else:
            out.append(line)
        prose = bool(line) and not line.startswith(" ")
    return out


def step_text(step: Step, indent: str = "  ") -> str:
    return "\n".join(indent + line for line in step_lines(step))


def advance(game) -> list[str]:
    """Advance through finished steps. Returns messages to show.

    The first line of each message is a one-line summary (it goes to syslog and
    is all that is shown while a terminal follows the tutorial); the last
    message also carries the full instructions for the step that is now
    current, so nobody has to type 'tutorial' after every step."""
    s = game.state
    msgs: list[str] = []
    while not s.tutorial_done and s.tutorial_step < len(STEPS):
        step = STEPS[s.tutorial_step]
        if not step.done(game):
            break
        s.tutorial_step += 1
        if s.tutorial_step >= len(STEPS):
            s.tutorial_done = True
            msgs.append(COMPLETE)
        else:
            msgs.append(f"Objective done: {step.title}.")
    nxt = current(game)
    if msgs and nxt is not None:
        msgs[-1] += f"  Next {heading(game)}\n" + step_text(nxt)
    return msgs


def render(game) -> list[tuple[str, str | None]]:
    """The follow view ('tutorial -f'): current step in full plus a checklist."""
    s = game.state
    out: list[tuple[str, str | None]] = []
    step = current(game)
    if step is None:
        out.append(("TUTORIAL COMPLETE", "good"))
        out.append(("Real contracts are waiting on the agency BBS (ssh blackrelay.net).", None))
        out.append(("Type 'learn' for short Linux lessons.", None))
    else:
        out.append((f"TUTORIAL {heading(game)}", "title"))
        out.append(("", None))
        for line in step_lines(step):
            out.append(("  " + line, "tutorial"))
    out.append(("", None))
    for i, st in enumerate(STEPS):
        if s.tutorial_done or i < s.tutorial_step:
            out.append((f"  [x] {st.title}", "dim"))
        elif i == s.tutorial_step:
            out.append((f"  [>] {st.title}", "bold"))
        else:
            out.append((f"  [ ] {st.title}", None))
    out.append(("", None))
    out.append(("Updates by itself. Ctrl+C stops it.", "dim"))
    return out
