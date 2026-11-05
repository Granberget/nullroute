"""The game world: nodes, corporations and procedural generation."""

from __future__ import annotations

import random

from . import names as N
from .hosts import Corp, Layer, Node
from .vfs import VFS

AGENCY = "blackrelay.net"
DROP = "drop.blackrelay.net"
SANDBOX = "sandbox.blackrelay.net"
GATEWAY = "gateway"


class World:
    def __init__(self, seed: int | None = None):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.nodes: dict[str, Node] = {}
        self.corps: dict[str, Corp] = {}
        self.relays: list[str] = []
        self._used_ips: set[str] = set()

    # ------------------------------------------------------------ lookup
    def add(self, node: Node) -> Node:
        self.nodes[node.hostname] = node
        return node

    def resolve(self, name: str) -> Node | None:
        name = name.strip().lower().rstrip(".")
        if "@" in name:
            name = name.split("@", 1)[1]
        if name in self.nodes:
            return self.nodes[name]
        for n in self.nodes.values():
            if n.ip == name:
                return n
        matches = [n for n in self.nodes.values() if n.short == name]
        if len(matches) == 1:
            return matches[0]
        return None

    def new_ip(self) -> str:
        while True:
            ip = ".".join(str(x) for x in (
                self.rng.choice([31, 45, 62, 77, 88, 91, 104, 128, 141, 152,
                                 176, 185, 193, 203, 212]),
                self.rng.randint(1, 254), self.rng.randint(0, 254),
                self.rng.randint(2, 254)))
            if ip not in self._used_ips:
                self._used_ips.add(ip)
                return ip

    def loc(self, city: str) -> tuple[int, int]:
        x, y = N.CITIES[city]
        return x + self.rng.randint(-1, 1), y

    def person(self) -> str:
        return f"{self.rng.choice(N.FIRST)} {self.rng.choice(N.LAST)}"


def base_fs(node: Node, now: float) -> VFS:
    fs = VFS()
    for d in ("/bin", "/etc", "/home", "/tmp", "/var", "/data"):
        fs.mkdir_p(d, mtime=now - 40000)
    fs.put("/etc/hostname", node.hostname + "\n", mtime=now - 90000)
    if node.motd:
        fs.put("/etc/motd", node.motd, mtime=now - 90000)
    return fs


# ====================================================================== build
def build_world(handle: str, seed: int | None = None, now: float = 0.0) -> World:
    w = World(seed)
    _gateway(w, handle, now)
    _relays(w)
    _agency(w, now)
    _sandbox(w, now)
    secs = [1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 5, 5]
    used: set[str] = set()
    for i, sec in enumerate(secs):
        corp = _corp(w, sec, N.CORP_CITIES[i % len(N.CORP_CITIES)], now, used)
        w.corps[corp.id] = corp
    return w


def _gateway(w: World, handle: str, now: float) -> None:
    g = w.add(Node(GATEWAY, w.new_ip(), "gateway", 0, title="Your gateway",
                   loc=w.loc("Oslo")))
    g.fs = base_fs(g, now)
    home = f"/home/{handle}"
    g.fs.mkdir_p(home + "/contracts")
    g.fs.mkdir_p(home + "/downloads")
    g.fs.put(home + "/README.txt", (
        f"Welcome to your gateway, {handle}.\n\n"
        "This machine is yours. Everything you download lands here.\n\n"
        "  mail              read your inbox\n"
        "  tutorial          show the current tutorial objective\n"
        f"  ssh {AGENCY}  log in to the agency (contracts, store, docs)\n"
        "  route             show your bounce route\n"
        "  help              list all commands, 'man <cmd>' for details\n"))
    g.fs.put(home + "/relays.txt",
             "Public relays (free to route through):\n\n" +
             "\n".join(f"  {c.lower().replace(' ', '')}.relay" for c in N.RELAY_CITIES) + "\n")


def prepare_gateway(state) -> None:
    """Make the gateway look like a real little Debian box. Idempotent, so
    it also upgrades gateways from older saves."""
    from .packages import PACKAGES, is_installed
    handle = state.handle
    g = state.world.nodes[GATEWAY]
    fs = g.fs
    now = state.minutes
    home = f"/home/{handle}"
    # users and groups
    fs.put("/etc/passwd",
           "root:x:0:0:root:/root:/bin/bash\n"
           "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
           "syslog:x:104:110::/home/syslog:/usr/sbin/nologin\n"
           f"{handle}:x:1000:1000:{handle},,,:{home}:/bin/bash\n", mtime=now - 90000)
    fs.put("/etc/group",
           f"root:x:0:\nadm:x:4:syslog,{handle}\nsudo:x:27:{handle}\n"
           f"{handle}:x:1000:\n", mtime=now - 90000)
    fs.put("/etc/sudoers", "# Members of group sudo may execute any command\n"
                           "%sudo   ALL=(ALL:ALL) ALL\n", mode=0o440, mtime=now - 90000)
    fs.put("/etc/hosts", f"127.0.0.1\tlocalhost\n{g.ip}\tgateway\n", mtime=now - 90000)
    fs.put("/etc/os-release", 'PRETTY_NAME="NullrouteOS 2.1 (Debian based)"\n'
                              'NAME="NullrouteOS"\nVERSION_ID="2.1"\nID=nullroute\nID_LIKE=debian\n',
           mtime=now - 90000)
    fs.put("/etc/apt/sources.list",
           "# Blackrelay licensed tools + the usual free stuff\n"
           "deb https://repo.blackrelay.net/debian stable main\n", mtime=now - 90000)
    # system directories with the usual permissions
    for d in ("/usr/bin", "/usr/share", "/var/lib/dpkg", "/var/log/apt", "/opt", "/srv"):
        fs.mkdir_p(d, mtime=now - 90000)
    root = fs.mkdir_p("/root")
    root.mode = 0o700
    tmp = fs.mkdir_p("/tmp")
    tmp.mode = 0o1777
    for path, mode in (("/var/log/syslog", 0o640), ("/var/log/auth.log", 0o640)):
        node = fs.get(path)
        if node is None:
            node = fs.put(path, "", mtime=now)
        node.owner, node.group, node.mode = "syslog" if "syslog" in path else "root", "adm", mode
    if fs.get("/var/log/mail.log") is None:
        ml = fs.put("/var/log/mail.log", "", mtime=now)
        ml.owner, ml.group, ml.mode = "syslog", "adm", 0o640
    for path in ("/var/log/apt/history.log", "/var/log/dpkg.log"):
        if fs.get(path) is None:
            fs.put(path, "", mtime=now)
    # your home belongs to you
    h = fs.mkdir_p(home)
    if h.owner != handle:
        for node in fs.walk(h):
            node.owner = node.group = handle
            if node.is_dir:
                node.mode = 0o755
        h.mode = 0o750
    for sub in ("contracts", "downloads"):
        d = fs.get(f"{home}/{sub}")
        if d is None:
            d = fs.mkdir_p(f"{home}/{sub}")
            d.owner = d.group = handle
    if fs.get(f"{home}/.bashrc") is None:
        rc = fs.put(f"{home}/.bashrc", "# ~/.bashrc\nalias ll='ls -la'\n", mtime=now)
        rc.owner = rc.group = handle
    # installed packages have a binary in /usr/bin
    for name, pkg in PACKAGES.items():
        path = f"/usr/bin/{name}"
        if is_installed(state, name) and fs.get(path) is None:
            fs.put(path, "\x7fELF", size=pkg.size_kb * 1024, binary=True, mode=0o755, mtime=now)
        elif not is_installed(state, name) and fs.get(path) is not None:
            del fs.get("/usr/bin").children[name]
    if is_installed(state, "hydra"):
        from . import creds
        creds.provision(fs, now)


def _relays(w: World) -> None:
    for city in N.RELAY_CITIES:
        name = city.lower().replace(" ", "") + ".relay"
        n = w.add(Node(name, w.new_ip(), "relay", 0, title=f"Public relay - {city}",
                       loc=w.loc(city)))
        n.public = True
        w.relays.append(name)


def _agency(w: World, now: float) -> None:
    w.add(Node(AGENCY, w.new_ip(), "agency", 0, title="Blackrelay agency BBS",
               loc=w.loc("Zurich")))
    d = w.add(Node(DROP, w.new_ip(), "drop", 0, title="Blackrelay drop box",
                   loc=w.loc("Zurich")))
    d.motd = "Blackrelay drop box. Upload deliveries to /drop/<contract-id>/\n"
    d.fs = base_fs(d, now)
    d.fs.mkdir_p("/drop")


def _sandbox(w: World, now: float) -> None:
    n = w.add(Node(SANDBOX, w.new_ip(), "sandbox", 1, title="Blackrelay training node",
                   loc=w.loc("Berlin")))
    n.layers = [Layer("firewall", 1)]
    n.motd = ("*** Blackrelay training node ***\n"
              "Behaves like a real target: it traces you and remembers you.\n")
    fs = base_fs(n, now)
    n.fs = fs
    fs.put("/home/trainer/welcome.txt",
           "Hi runner.\n\nThe file you want is somewhere under /data.\n"
           "Try: ls /data   or   find /data -name '*.dat'\n", mtime=now - 3000)
    fs.put("/data/vault/training_payload.dat", "BLACKRELAY TRAINING PAYLOAD\n",
           size=1_250_000, binary=True, tag="sandbox-payload", mtime=now - 7000)
    fs.put("/data/vault/decoy.dat", "nothing to see here\n", size=80_000,
           binary=True, mtime=now - 7000)
    fs.put("/data/notes.txt", "Remember: scrub before you leave.\n")


def _ice(sec: int, core: bool) -> list[Layer]:
    layers = [Layer("firewall", min(5, sec))]
    if sec >= 2 and core or sec >= 3:
        layers.append(Layer("cipher", max(1, sec - 1)))
    if sec >= 3 and core or sec >= 5:
        layers.append(Layer("gatekeeper", max(1, sec - 1)))
    return layers


def _corp(w: World, sec: int, city: str, now: float, used: set[str]) -> Corp:
    rng = w.rng
    for _ in range(200):
        a, b = rng.choice(N.CORP_A), rng.choice(N.CORP_B)
        name = f"{a} {b}"
        if name not in used and a not in {u.split()[0] for u in used}:
            used.add(name)
            break
    domain = f"{a}{b}.corp".lower()
    corp = Corp(id=domain, name=name, domain=domain, sec=sec, city=city)
    corp.staff = [w.person() for _ in range(5)]
    loc = w.loc(city)

    front = w.add(Node(f"www.{domain}", w.new_ip(), "front", max(1, sec - 1),
                       domain, f"{name} front node", loc))
    front.layers = _ice(front.sec, core=False)
    front.motd = f"{name} - public node. Unauthorised access is monitored.\n"
    core = w.add(Node(f"core.{domain}", w.new_ip(), "core", sec, domain,
                      f"{name} core node", loc))
    core.layers = _ice(sec, core=True)
    core.parent = front.hostname
    core.motd = f"{name} CORE. Internal systems. All sessions are recorded.\n"
    corp.nodes = [front.hostname, core.hostname]

    # front node: public-ish content and a pointer to the core
    fs = base_fs(front, now)
    front.fs = fs
    fs.put("/var/www/index.html",
           f"<html><h1>{name}</h1><p>Building tomorrow, today.</p></html>\n")
    fs.put("/etc/hosts", f"{front.ip}\t{front.hostname}\n"
                         f"{core.ip}\t{core.hostname}   # core - reachable from this node only\n")
    for i in range(3):
        _memo(w, fs, corp, f"/home/memos/memo_{i + 1:02d}.txt", now)

    # core node: projects and staff memos
    fs = base_fs(core, now)
    core.fs = fs
    for proj in rng.sample(N.PROJECTS, 3):
        pdir = f"/data/projects/{proj.lower()}"
        fs.put(f"{pdir}/README.txt",
               f"Project {proj}\nLead: {rng.choice(corp.staff)}\nStatus: "
               f"{rng.choice(['active', 'on hold', 'phase II', 'classified'])}\n",
               mtime=now - rng.randint(500, 50000))
        for _ in range(rng.randint(2, 3)):
            kind = rng.choice(N.DATA_KINDS)
            fname = f"{proj.lower()}_{kind}_v{rng.randint(1, 9)}.dat"
            fs.put(f"{pdir}/{fname}", "encrypted blob\n",
                   size=rng.randint(200_000, 12_000_000), binary=True,
                   mtime=now - rng.randint(500, 50000))
    for i in range(4):
        person = corp.staff[i % len(corp.staff)]
        user = person.split()[0].lower()
        _memo(w, fs, corp, f"/home/{user}/memo_{i + 1:02d}.txt", now)
    fs.mkdir_p("/data/archive")
    return corp


def _memo(w: World, fs: VFS, corp: Corp, path: str, now: float) -> None:
    rng = w.rng
    sender = rng.choice(corp.staff)
    subject = rng.choice(N.MEMO_SUBJECTS)
    fs.put(path, f"From: {sender}\nTo: all staff\nSubject: {subject}\n\n"
                 f"Please read and follow up by end of week.\n-- {corp.name}\n",
           mtime=now - rng.randint(300, 30000))
