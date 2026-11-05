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
         "  mail -s T0 -A ~/downloads/training_payload.dat vex@blackrelay.net\n"
         "Type a line of text if you like, then a single '.' to send.\n"
         "(or pipe the text in:  echo here | mail -s T0 -A ... vex@blackrelay.net)",
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
         "sudo asks for YOUR password (the one you picked at the start).",
         _flag("installed:decrypt")),
]


def current(game) -> Step | None:
    s = game.state
    if s.tutorial_done or s.tutorial_step >= len(STEPS):
        return None
    return STEPS[s.tutorial_step]


def advance(game) -> list[str]:
    """Advance through finished steps. Returns messages to show."""
    s = game.state
    msgs: list[str] = []
    while not s.tutorial_done and s.tutorial_step < len(STEPS):
        step = STEPS[s.tutorial_step]
        if not step.done(game):
            break
        s.tutorial_step += 1
        if s.tutorial_step >= len(STEPS):
            s.tutorial_done = True
            msgs.append("TUTORIAL COMPLETE. Real contracts are waiting on the agency board. "
                        "Want to sharpen your Linux skills? Type 'learn'.")
        else:
            nxt = STEPS[s.tutorial_step]
            msgs.append(f"Objective done: {step.title}.  Next: {nxt.title}  (type 'tutorial')")
    return msgs
