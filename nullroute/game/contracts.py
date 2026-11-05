"""Contracts offered on the agency board, and how they are checked.

Most jobs are reported back by mail, like in the old days:
  retrieve  copy a file home and mail it to the client as an attachment
  wipe      delete a file (and its backups), then mail the client to confirm
  modify    change a value in a data file, then mail the client to confirm
  plant     upload a file the client gave you (checked automatically)
  find      find a passphrase and send it (mail or the BBS)
"""

from __future__ import annotations

from dataclasses import dataclass

from . import names as N
from .vfs import File
from .world import DROP, SANDBOX

PAY = {1: 1200, 2: 2400, 3: 4800, 4: 8500, 5: 15000}
MIN_RATING = {1: 0, 2: 0, 3: 1, 4: 2, 5: 3}
POINTS = {1: 4, 2: 7, 3: 12, 4: 20, 5: 32}

KIND_LABEL = {"retrieve": "Retrieve", "wipe": "Wipe", "plant": "Plant", "modify": "Modify",
              "find": "Find", "training": "Training"}

CLIENTS = ["an anonymous client", "a rival corporation", "a journalist collective",
           "a hedge fund", "a former employee", "an insurance syndicate"]
MAIL_DOMAINS = ["quietmail.net", "nullpost.org", "veilmail.io", "darkletter.net"]
REGISTRY = "/data/registry/projects.csv"
REG_HEADER = ["id", "project", "lead", "status", "launch", "budget"]


@dataclass
class Contract:
    id: str
    kind: str
    corp: str
    corp_name: str
    target: str
    title: str
    brief: str
    pay: int
    difficulty: int
    deadline: float
    min_rating: int
    tag: str = ""
    path: str = ""
    answer: str = ""
    status: str = "open"           # open, accepted, done, failed, expired
    accepted_at: float = 0.0
    attempts: int = 0
    client: str = ""
    client_addr: str = ""
    row: str = ""                  # modify: row id
    field: str = ""                # modify: column name
    value: str = ""                # modify: wanted value

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def drop_dir(self) -> str:
        return f"/drop/{self.id}"


def training_contract(now: float) -> Contract:
    return Contract(
        id="T0", kind="training", corp="blackrelay.net", corp_name="Blackrelay",
        target=SANDBOX, title="Training: lift the payload",
        brief=(
            f"Target:  {SANDBOX}\n"
            "Goal:    find training_payload.dat somewhere under /data, copy it\n"
            "         home to your gateway and mail it to Vex:\n"
            "           scp training_payload.dat gateway:~/downloads/     (on the node)\n"
            "           mail -A ~/downloads/training_payload.dat vex@blackrelay.net\n"
            "                                                    (back on your gateway)\n\n"
            "Steps:   probe the node, set up a route through a couple of\n"
            "         relays, breach it, ssh in, find the file, copy it home,\n"
            "         scrub your footprint, exit, then send the mail.\n\n"
            "Type 'tutorial' at any time for the next step\n"
            "(or 'tutorial -f' in a second terminal to keep it on screen)."),
        pay=1500, difficulty=1, deadline=now + 60 * 24 * 30, min_rating=0,
        tag="sandbox-payload", status="accepted", accepted_at=now,
        client="Vex", client_addr="vex@blackrelay.net")


def _confirm_text(c: Contract) -> str:
    return (f"When it's done, confirm by mail:\n"
            f"  echo done | mail {c.client_addr}")


def ensure_registry(node, rng, corp, now: float) -> File:
    """A small CSV project register on the node (created on first use)."""
    f = node.fs.get(REGISTRY)
    if isinstance(f, File):
        return f
    rows = [",".join(REG_HEADER)]
    for i, proj in enumerate(rng.sample(N.PROJECTS, 8)):
        lead = rng.choice(corp.staff)
        rows.append(f"P-{101 + i},{proj},{lead},"
                    f"{rng.choice(['active', 'active', 'on hold', 'phase II', 'review'])},"
                    f"2031-{rng.randint(4, 12):02d}-{rng.randint(1, 28):02d},"
                    f"{rng.randint(5, 90) * 100000}")
    return node.fs.put(REGISTRY, "\n".join(rows) + "\n", mtime=now - rng.randint(500, 20000))


def registry_value(node, row_id: str, field: str) -> str | None:
    f = node.fs.get(REGISTRY) if node.fs else None
    if not isinstance(f, File):
        return None
    lines = [l for l in f.content.splitlines() if l.strip()]
    if not lines:
        return None
    header = [h.strip() for h in lines[0].split(",")]
    if field not in header:
        return None
    col = header.index(field)
    for line in lines[1:]:
        cells = [c.strip() for c in line.split(",")]
        if cells and cells[0] == row_id:
            return cells[col] if col < len(cells) else None
    return None


def generate(state, now: float) -> Contract | None:
    rng = state.rng
    world = state.world
    corps = list(world.corps.values())
    busy = {c.target for c in state.contracts if c.status in ("open", "accepted")}
    for _ in range(30):
        corp = rng.choice(corps)
        node = world.nodes[corp.nodes[1] if rng.random() < 0.75 else corp.nodes[0]]
        if node.hostname in busy or node.fs is None:
            continue
        cid = f"C{state.next_id():03d}"
        diff = node.sec
        pay = int(PAY[diff] * rng.uniform(0.85, 1.3) / 50) * 50
        deadline = now + rng.choice([1, 2, 2, 3]) * 1440
        client = rng.choice(CLIENTS)
        addr = f"{rng.choice(N.PROJECTS).lower()}{rng.randint(10, 99)}@{rng.choice(MAIL_DOMAINS)}"
        kind = rng.choice(["retrieve", "retrieve", "wipe", "modify", "modify", "plant", "find"])
        c = Contract(id=cid, kind=kind, corp=corp.id, corp_name=corp.name,
                     target=node.hostname, title="", brief="", pay=pay,
                     difficulty=diff, deadline=deadline, min_rating=MIN_RATING[diff],
                     client=client, client_addr=addr)
        head = f"Client:  {client} <{addr}>\nTarget:  {node.hostname}\n"
        if kind in ("retrieve", "wipe"):
            files = [f for f in node.fs.walk() if isinstance(f, File)
                     and f.name.endswith(".dat") and not f.tag]
            if not files:
                continue
            f = rng.choice(files)
            f.tag = cid
            c.tag = cid
            c.path = f.path()
            if kind == "retrieve":
                c.title = f"Retrieve {f.name} from {corp.name}"
                c.brief = (head + f"File:    {f.name}  (somewhere under /data)\n\n"
                           "Copy the file to your gateway, then mail it to the client\n"
                           "as an attachment:\n"
                           f"  scp {f.name} gateway:~/downloads/          (on the node)\n"
                           f"  mail -A ~/downloads/{f.name} {addr}\n"
                           "                                           (on your gateway)")
            else:
                c.title = f"Wipe {f.name} at {corp.name}"
                c.brief = (head + f"File:    {f.path()}\n\n"
                           "Delete the file from the node. Make sure no copy is left\n"
                           "anywhere on that node (check /data/archive too).\n\n"
                           + _confirm_text(c))
                if rng.random() < 0.5:
                    node.fs.put(f"/data/archive/{f.name}.bak", "encrypted blob\n",
                                size=f.size, binary=True, tag=cid, mtime=f.mtime)
                c.pay = int(pay * 1.15)
        elif kind == "modify":
            ensure_registry(node, rng, corp, now)
            reg = node.fs.get(REGISTRY).content.splitlines()[1:]
            row = rng.choice(reg).split(",")
            c.row, proj = row[0], row[1]
            choice = rng.choice(["status", "launch", "budget"])
            c.field = choice
            if choice == "status":
                c.value = rng.choice(["cancelled", "on hold", "terminated"])
                if row[3] == c.value:
                    c.value = "cancelled" if c.value != "cancelled" else "on hold"
                what = f"set the status of project {proj} ({c.row}) to '{c.value}'"
            elif choice == "launch":
                c.value = f"2032-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
                what = f"move the launch date of project {proj} ({c.row}) to {c.value}"
            else:
                c.value = "0"
                what = f"set the budget of project {proj} ({c.row}) to 0"
            c.path = REGISTRY
            c.title = f"Alter the project register at {corp.name}"
            c.brief = (head + f"File:    {REGISTRY}\n\n"
                       f"The client wants you to {what}.\n"
                       "Change only that one value - the file is a CSV, one project per\n"
                       "line, columns separated by commas.\n\n"
                       f"Tip: grep -n {c.row} {REGISTRY}   then   nano +LINE {REGISTRY}\n\n"
                       + _confirm_text(c))
            c.pay = int(pay * 1.1)
        elif kind == "plant":
            c.tag = cid
            proj_dirs = [d for d in node.fs.walk() if d.is_dir
                         and d.path().startswith("/data/") and d.path() != "/data"]
            target_dir = rng.choice(proj_dirs).path() if proj_dirs else "/data"
            fname = f"{rng.choice(N.PROJECTS).lower()}_update.dat"
            c.path = f"{target_dir}/{fname}"
            c.title = f"Plant a file at {corp.name}"
            c.brief = (head + "\n"
                       f"We have placed {fname} on your gateway in\n"
                       f"  ~/contracts/{cid}/{fname}\n"
                       "Upload it to the target into this exact directory:\n"
                       f"  {target_dir}/\n\n"
                       f"Tip: on the node run  scp gateway:~/contracts/{cid}/{fname} {target_dir}/\n"
                       "We notice by ourselves when it's in place.")
        else:
            words = rng.sample(N.PASSPHRASE_WORDS, 2)
            phrase = f"{words[0]}-{words[1]}-{rng.randint(10, 99)}"
            c.answer = phrase
            homes = [d for d in node.fs.walk() if d.is_dir and d.path().startswith("/home/")
                     and d.path().count("/") == 2]
            base = rng.choice(homes).path() if homes else "/home"
            hidden = f"{base}/.{rng.choice(['notes', 'stash', 'todo', 'misc'])}.txt"
            node.fs.put(hidden, "Things I must not forget:\n- dentist thursday\n"
                                f"- vault passphrase: {phrase}\n- buy milk\n",
                        mtime=now - rng.randint(500, 9000))
            c.path = hidden
            c.title = f"Find the vault passphrase at {corp.name}"
            c.brief = (head + "\n"
                       "Somebody on that node wrote down the vault passphrase.\n"
                       "It looks like:  word-word-NN\n"
                       "Send it to the client by mail (or submit it on this board):\n"
                       f"  echo PASSPHRASE | mail {addr}\n\n"
                       "Tip: hidden files start with a dot (ls -a), and\n"
                       "     grep -r passphrase /home  searches everything.")
        return c
    return None


def objective_met(c: Contract, world) -> bool:
    """Is the job itself done on the target (regardless of reporting)?"""
    if c.kind in ("retrieve", "training"):
        drop = world.nodes[DROP].fs
        d = drop.get(f"/drop/{c.id}")
        return d is not None and d.is_dir and any(
            isinstance(f, File) and f.tag == c.tag for f in drop.walk(d))
    node = world.nodes.get(c.target)
    if node is None or node.fs is None:
        return False
    if c.kind == "wipe":
        return node.fs.find_tag(c.tag) is None
    if c.kind == "plant":
        f = node.fs.get(c.path)
        return isinstance(f, File) and f.tag == c.tag
    if c.kind == "modify":
        return registry_value(node, c.row, c.field) == c.value
    return False


def is_complete(c: Contract, world) -> bool:
    """Checked every second: jobs that complete without a report.
    (Old drop-box deliveries still count, so older saves keep working.)"""
    if c.kind in ("plant", "retrieve", "training"):
        return objective_met(c, world)
    return False
