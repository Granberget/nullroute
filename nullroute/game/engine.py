"""Game logic: clock, trace, footprints, contracts, mail and news."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import contracts as C
from . import store, tutorial
from .clock import fmt_log, fmt_short, to_dt
from .hosts import Node
from .state import GameState, Mail, News
from .vfs import File
from .world import AGENCY, DROP, GATEWAY, SANDBOX

TRACE_BASE = 15.0       # seconds for a direct connection at security 3
TRACE_PER_HOP = 9.0
SEC_FACTOR = {0: 2.0, 1: 1.5, 2: 1.25, 3: 1.0, 4: 0.85, 5: 0.7}
ALARM_MEMORY = 30.0     # game minutes a node remembers an interrupted trace
MAX_STRIKES = 3


@dataclass
class Conn:
    """A live connection from the gateway to a node."""
    target: str
    path: list[str] = field(default_factory=list)   # gateway ... target
    kind: str = "shell"                             # shell, breach, transfer

    @property
    def hops(self) -> int:
        return max(0, len(self.path) - 2)


class Game:
    def __init__(self, state: GameState):
        self.state = state
        self.conns: list[Conn] = []
        self.listeners: list[Callable[[str, str], None]] = []
        self.on_caught: Callable[[str], None] | None = None
        self._acc = 0.0

    # ------------------------------------------------------------ helpers
    @property
    def world(self):
        return self.state.world

    @property
    def now(self) -> float:
        return self.state.minutes

    def node(self, name: str) -> Node | None:
        return self.world.resolve(name)

    def notify(self, text: str, style: str = "info") -> None:
        daemon = {"mail": "mail", "alert": "tracewatch", "tutorial": "tutorial",
                  "good": "blackrelay", "achievement": "achievements"}.get(style, "nullroute")
        self.syslog(daemon, text)
        for cb in self.listeners:
            cb(text, style)

    def syslog(self, daemon: str, text: str, path: str = "/var/log/syslog",
               node: str = GATEWAY) -> None:
        """Append a line to a log file, the way rsyslog would."""
        n = self.world.nodes.get(node)
        if n is None or n.fs is None:
            return
        f = n.fs.get(path)
        if f is None or f.is_dir:
            return
        pid = 300 + sum(map(ord, daemon)) * 7 % 4000
        f.content += f"{fmt_log(self.now)} {n.short} {daemon}[{pid}]: {text}\n"

    def flag(self, name: str) -> None:
        self.state.flags.add(name)
        for msg in tutorial.advance(self):
            self.notify(msg, "tutorial")

    def award(self, key: str) -> None:
        from . import learning
        learning.award(self, key)

    # ------------------------------------------------------------ outgoing mail
    KNOWN_ADDRS = {"vex@blackrelay.net", "board@blackrelay.net", "store@blackrelay.net"}

    def send_mail(self, to: list[str], subject: str, body: str, attachments: list) -> None:
        """Deliver a mail sent from the gateway and let clients react to it."""
        from .state import SentMail
        s = self.state
        att = [(f.name, f.tag or "", f.size) for f in attachments]
        s.sent.append(SentMail(list(to), subject, body, att, self.now))
        s.sent = s.sent[-100:]
        if att:
            self.award("mail_attach")
        size = len(body) + sum(a[2] for a in att)
        for addr in to:
            self.syslog("postfix/smtp", f"to=<{addr}>, relay=mx.{addr.split('@')[-1]}[25], "
                                        f"size={size}, status=sent (250 2.0.0 Ok: queued)",
                        path="/var/log/mail.log")
        for addr in to:
            a = addr.lower().strip()
            mine = [c for c in s.contracts if c.client_addr and c.client_addr.lower() == a]
            if not mine and a not in self.KNOWN_ADDRS:
                self.syslog("postfix/smtp", f"to=<{addr}>, status=bounced (host not found)",
                            path="/var/log/mail.log")
                self.mail("MAILER-DAEMON <postmaster@gateway>", "Undelivered Mail Returned to Sender",
                          f"This is the mail system at host gateway.\n\n"
                          f"I'm sorry to have to inform you that your message could not\n"
                          f"be delivered to one or more recipients.\n\n"
                          f"<{addr}>: Host or domain name not found.\n\n"
                          f"Subject: {subject}\n\n(Check the address in the contract briefing.)")
                continue
            active = [c for c in mine if c.status == "accepted"]
            for c in active:
                self._report(c, subject, body, att)
            if mine and not active:
                self.mail(f"{mine[0].client.title()} <{addr}>", f"Re: {subject}",
                          "We have no open business with you. Don't write again.")
            if a == "vex@blackrelay.net" and not any(c.kind == "training" for c in active):
                self.mail("Vex <vex@blackrelay.net>", f"Re: {subject}",
                          "Got your message. If it's about a job, mail the client listed\n"
                          "in the contract, not me.\n\n-- Vex")

    def _report(self, c, subject: str, body: str, att: list) -> None:
        sender = f"{c.client.title() if c.client else 'Client'} <{c.client_addr}>"
        text = f"{subject}\n{body}".lower()
        if c.kind in ("retrieve", "training"):
            if any(tag == c.tag for _, tag, _ in att):
                self.complete(c)
            elif att:
                self.mail(sender, f"Re: {subject}",
                          f"That's not the file we asked for ({', '.join(a[0] for a in att)}).\n"
                          "Read the briefing again.")
            else:
                self.mail(sender, f"Re: {subject}",
                          "There was no attachment. Attach the file with -A:\n"
                          f"  mail -s '{c.id}' -A ~/downloads/FILE {c.client_addr}")
            return
        if c.kind == "find":
            if c.answer.lower() in text:
                self.complete(c)
            else:
                self.mail(sender, f"Re: {subject}", self._wrong_answer(c))
            return
        if C.objective_met(c, self.world):
            self.complete(c)
            return
        if c.kind == "modify":
            node = self.world.nodes.get(c.target)
            now_val = C.registry_value(node, c.row, c.field) if node else None
            self.mail(sender, f"Re: {subject}",
                      f"Our contact checked {c.path}: the {c.field} of {c.row} is still\n"
                      f"'{now_val}'. We want '{c.value}'. Not paying for that.")
        elif c.kind == "wipe":
            self.mail(sender, f"Re: {subject}",
                      "Our contact says the file is still there (or a copy of it is).\n"
                      "Check /data/archive too. find / -name ... helps.")
        else:
            self.mail(sender, f"Re: {subject}", "Not done yet, as far as we can tell.")

    def _wrong_answer(self, c) -> str:
        c.attempts += 1
        if c.attempts >= 3:
            c.status = "failed"
            return "Wrong again. We're done here - contract cancelled."
        return f"That's not the passphrase. {3 - c.attempts} attempt(s) left."

    def buy(self, item) -> str:
        msg = store.buy(self.state, item)
        if msg.startswith("Purchased"):
            self.flag(f"bought:{item.key}")
            if item.kind == "software":
                self.mail("Blackrelay Store <store@blackrelay.net>",
                          f"Licence activated: {item.name}", (
                              f"Thanks for your purchase. Your licence for {item.name} is active\n"
                              "in the Blackrelay package repository.\n\n"
                              "Install it on your gateway:\n\n"
                              "  sudo apt update              refresh the package lists\n"
                              f"  sudo apt install {item.key}\n\n"
                              "Already have an older version? 'sudo apt upgrade' does the lot.\n"
                              "apt needs root, which is what sudo is for. It asks for YOUR\n"
                              "password (the one you chose when you started)."))
        return msg

    def mail(self, sender: str, subject: str, body: str) -> Mail:
        m = Mail(self.state.next_id(), sender, subject, body, self.now)
        self.state.mail.append(m)
        self.notify(f"New mail from {sender}: {subject}", "mail")
        return m

    def news(self, headline: str, body: str = "") -> None:
        self.state.news.append(News(self.now, headline, body))
        self.state.news = self.state.news[-60:]

    # ------------------------------------------------------------ setup
    def start_new(self) -> None:
        s = self.state
        s.contracts.append(C.training_contract(self.now))
        self.mail("Vex <vex@blackrelay.net>", "Welcome to Blackrelay", (
            f"Hey {s.handle},\n\n"
            "Welcome aboard. I'm Vex, I look after new runners here.\n\n"
            "How it works: corps hide their data behind ICE. You probe a node to\n"
            "see its layers, run breach programs to crack them, then ssh in and\n"
            "do the job with ordinary commands - ls, cd, cat, grep, find, cp,\n"
            "rm, scp. The moment you start a breach the node starts tracing you.\n"
            "If the trace completes, you're burned. Three strikes and you're out.\n\n"
            "Bounce through public relays to slow the trace down, and always\n"
            "scrub your footprint before you leave a node.\n\n"
            "I've set up a training job for you (contract T0). Type 'tutorial'\n"
            "whenever you want to know what to do next.\n\n"
            f"The agency BBS is at {AGENCY} - contracts, store and docs.\n\n"
            "New to Linux? Your gateway runs a real-ish shell. 'learn' has ten\n"
            "short lessons, 'man <command>' has examples for everything, and\n"
            "'achievements' shows what you've picked up so far.\n\n"
            "-- Vex"))
        for _ in range(5):
            self.spawn_contract()
        s.next_contract_at = self.now + 90
        self.news("Blackrelay welcomes new runners", "Recruitment is up this quarter.")

    def spawn_contract(self) -> None:
        c = C.generate(self.state, self.now)
        if c:
            self.state.contracts.append(c)

    # ------------------------------------------------------------ trace
    def trace_seconds(self, node: Node, path: list[str]) -> float:
        hops = max(0, len(path) - 2)
        total = (TRACE_BASE + TRACE_PER_HOP * hops) * SEC_FACTOR.get(node.sec, 1.0)
        if node.kind == "sandbox":
            total *= 2
        return total

    def start_trace(self, node: Node, reason: str) -> None:
        if node.kind in ("relay", "agency", "drop", "gateway"):
            return
        node.alarm_until = self.now + ALARM_MEMORY
        if not node.trace_active:
            node.trace_active = True
            self.notify(f"TRACE INITIATED by {node.hostname} ({reason})", "alert")

    def active_trace(self) -> tuple[Node, Conn] | None:
        """The trace that will complete first, if any."""
        best = None
        for c in self.conns:
            n = self.world.nodes.get(c.target)
            if n and n.trace_active:
                left = (1 - n.trace_progress) * self.trace_seconds(n, c.path)
                if best is None or left < best[0]:
                    best = (left, n, c)
        return (best[1], best[2]) if best else None

    def trace_left(self) -> float | None:
        t = self.active_trace()
        if not t:
            return None
        n, c = t
        return (1 - n.trace_progress) * self.trace_seconds(n, c.path)

    def open_conn(self, conn: Conn) -> Conn:
        self.conns.append(conn)
        return conn

    def close_conn(self, conn: Conn) -> None:
        if conn in self.conns:
            self.conns.remove(conn)
        node = self.world.nodes.get(conn.target)
        if node is None:
            return
        if not any(c.target == node.hostname for c in self.conns):
            if node.trace_active:
                node.alarm_until = self.now + ALARM_MEMORY
            if node.footprint > 0 and not node.check_at:
                node.check_at = self.now + self.state.rng.randint(120, 360)

    # ------------------------------------------------------------ breach
    def breach_plan(self, node: Node) -> list[tuple[str, int, int, float]]:
        """For each layer: (kind, strength, program version, seconds or -1)."""
        cpu = store.CPU_SPEED[self.state.hw["cpu"]]
        plan = []
        for layer in node.layers:
            ver = self.state.sw.get(layer.program, 0)
            if ver <= 0 or layer.strength > store.max_strength(ver):
                plan.append((layer.kind, layer.strength, ver, -1.0))
            else:
                plan.append((layer.kind, layer.strength, ver,
                             3.0 + layer.strength * 4.0 / cpu))
        return plan

    def breached(self, node: Node, hops: int) -> None:
        node.breached_until = self.now + 120
        node.footprint = min(100.0, node.footprint + 30 + 10 * node.sec)
        node.footprint_hops = hops
        node.check_at = 0.0
        self.flag(f"breach:{node.hostname}")

    def node_credentials(self, node: Node) -> tuple[str, str]:
        """The one valid (login, password) pair hydra can recover for a node."""
        from . import creds
        return creds.credentials_for(self.world, node)

    def brute_noise(self, node: Node, hops: int) -> None:
        """A brute-force is loud: it leaves a heavier footprint than a breach."""
        node.footprint = min(100.0, node.footprint + 35 + 10 * node.sec)
        node.footprint_hops = hops

    def scrub_seconds(self, node: Node) -> float:
        return max(2.0, node.footprint / 10.0 / (1 if self.state.sw["scrub"] < 2 else 2))

    # ------------------------------------------------------------ contracts
    def accept(self, c: C.Contract) -> str:
        s = self.state
        if c.status != "open":
            return "That contract is no longer available."
        if s.rating_level < c.min_rating:
            return "Your rating is too low for this contract."
        active = [x for x in s.contracts if x.status == "accepted" and x.kind != "training"]
        if len(active) >= 3:
            return "You already have 3 active contracts."
        c.status = "accepted"
        c.accepted_at = self.now
        node = self.world.nodes[c.target]
        brief = c.brief
        if node.parent:
            brief += (f"\n\nNote: {node.hostname} only accepts connections from\n"
                      f"{node.parent}. Breach and ssh into that node first, then\n"
                      "breach and ssh onward from there.")
            s.known.add(node.parent)
        s.known.add(node.hostname)
        gw = self.world.nodes[GATEWAY].fs
        gw.put(f"{s.home}/contracts/{c.id}.txt",
               f"CONTRACT {c.id} - {c.title}\nPay: ¢{c.pay:,}   Deadline: "
               f"{fmt_short(c.deadline)}\n\n{brief}\n")
        if c.kind == "plant":
            fname = c.path.rsplit("/", 1)[1]
            gw.put(f"{s.home}/contracts/{c.id}/{fname}", "client payload\n",
                   size=s.rng.randint(50_000, 900_000), binary=True, tag=c.tag)
        self.mail("Blackrelay Contracts <board@blackrelay.net>",
                  f"Contract {c.id} accepted", f"{c.title}\n\n{brief}\n\n"
                  f"Deadline: {fmt_short(c.deadline)}\nPay: ¢{c.pay:,}\n"
                  f"(A copy is in ~/contracts/{c.id}.txt)")
        return f"Contract {c.id} accepted. Briefing saved to ~/contracts/{c.id}.txt"

    def abandon(self, c: C.Contract) -> str:
        if c.status != "accepted" or c.kind == "training":
            return "You can't abandon that contract."
        c.status = "failed"
        self.state.rating = max(0, self.state.rating - 2)
        return f"Contract {c.id} abandoned. (-2 rating)"

    def submit_answer(self, c: C.Contract, text: str) -> str:
        if c.status != "accepted" or c.kind != "find":
            return "Nothing to submit for that contract."
        if text.strip().lower() == c.answer.lower():
            self.complete(c)
            return "Correct. Payment is on its way."
        c.attempts += 1
        if c.attempts >= 3:
            c.status = "failed"
            self.mail("Blackrelay Contracts <board@blackrelay.net>",
                      f"Contract {c.id} failed", "Three wrong answers. The client walked.")
            return "Wrong again - the client cancelled the contract."
        return f"That's not it. {3 - c.attempts} attempt(s) left."

    def complete(self, c: C.Contract) -> None:
        s = self.state
        c.status = "done"
        s.money += c.pay
        s.rating += C.POINTS.get(c.difficulty, 4) if c.kind != "training" else 5
        self.mail("Blackrelay Contracts <board@blackrelay.net>",
                  f"Payment for {c.id}: ¢{c.pay:,}",
                  f"{c.title}\n\nClient confirmed. ¢{c.pay:,} has been transferred.\n"
                  f"Rating is now {s.rating} ({s.rating_title}).")
        self.notify(f"Contract {c.id} complete: +¢{c.pay:,}", "good")
        if c.kind != "training":
            self.news(f"{c.corp_name} reports a security incident",
                      "A spokesperson declined to comment.")
        self.flag(f"contract:{c.id}")
        if c.kind != "training":
            self.award("first_contract")
            if len(s.route) >= 4:
                self.award("untraceable")

    # ------------------------------------------------------------ caught
    def caught(self, node: Node, how: str) -> None:
        s = self.state
        s.strikes += 1
        fine = int(s.money * 0.3)
        s.money -= fine
        node.trace_active = False
        node.trace_progress = 0.0
        node.footprint = 0.0
        node.check_at = 0.0
        if s.strikes >= MAX_STRIKES:
            s.game_over = (f"{how}\n\nThat was your third strike. Blackrelay has cut all ties,\n"
                           "and your gateway has been seized. Game over.")
        else:
            self.mail("Vex <vex@blackrelay.net>", "You got burned", (
                f"{how}\n\nWe paid off the right people, but it cost you ¢{fine:,}.\n"
                f"Strikes: {s.strikes}/{MAX_STRIKES}. Use longer routes and scrub\n"
                "your footprint before you leave a node.\n\n-- Vex"))
        self.news(f"{node.title}: intruder identified", how)
        if self.on_caught:
            self.on_caught(how)

    # ------------------------------------------------------------ tick
    def tick(self, dt: float) -> None:
        """Advance the game by dt real seconds."""
        s = self.state
        if s.game_over:
            return
        s.minutes += dt
        # traces
        for node in list(self.world.nodes.values()):
            if not node.trace_active:
                continue
            conns = [c for c in self.conns if c.target == node.hostname]
            if conns:
                total = min(self.trace_seconds(node, c.path) for c in conns)
                node.trace_progress += dt / total
                node.alarm_until = self.now + ALARM_MEMORY
                if node.trace_progress >= 1.0:
                    self.caught(node, f"Trace completed by {node.hostname}.")
                    return
            elif self.now > node.alarm_until:
                node.trace_active = False
                node.trace_progress = 0.0
        self._acc += dt
        if self._acc >= 1.0:
            self._acc = 0.0
            self._slow_tick()

    def _live_logs(self, connected: set[str]) -> None:
        """Background noise in log files so 'tail -f' has something to show."""
        rng = self.state.rng
        if rng.random() < 0.08:
            self.syslog("CRON", "(root) CMD (cd / && run-parts --report /etc/cron.hourly)")
        if rng.random() < 0.03:
            self.syslog("systemd", "Started gatewayd.service - Gateway uplink monitor.")
        for name in connected:
            node = self.world.nodes.get(name)
            if node is None or node.fs is None or rng.random() > 0.45:
                continue
            ip = f"{rng.randint(11, 220)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(2, 254)}"
            if node.kind == "front":
                page = rng.choice(["/", "/index.html", "/about", "/careers", "/press",
                                   "/products", "/favicon.ico", "/login", "/robots.txt"])
                code = rng.choice([200, 200, 200, 200, 304, 404, 301])
                ts = to_dt(self.now).strftime("%d/%b/%Y:%H:%M:%S +0000")
                line = (f'{ip} - - [{ts}] "GET {page} HTTP/1.1" {code} '
                        f'{rng.randint(200, 48000)} "-" "Mozilla/5.0"\n')
                log = node.fs.get("/var/log/nginx/access.log")
                if log is None:
                    log = node.fs.put("/var/log/nginx/access.log", "", group="adm", mode=0o640)
                log.content += line
            else:
                if node.fs.get("/var/log/syslog") is None:
                    node.fs.put("/var/log/syslog", "", group="adm", mode=0o640)
                msg = rng.choice([
                    "CRON[{p}]: (root) CMD (/usr/local/bin/backup.sh)",
                    "postgres[{p}]: LOG:  checkpoint complete: wrote 42 buffers",
                    "rsyncd[{p}]: sent 1048576 bytes  received 412 bytes",
                    "systemd[1]: Started session-{p}.scope - Session {p} of user staff.",
                    "kernel: [UFW BLOCK] IN=eth0 SRC=" + ip + " DST=" + node.ip + " PROTO=TCP DPT=22",
                ]).format(p=rng.randint(1000, 9999))
                node.fs.get("/var/log/syslog").content += f"{fmt_log(self.now)} {node.short} {msg}\n"

    def _slow_tick(self) -> None:
        s = self.state
        # footprint reviews
        connected = {c.target for c in self.conns}
        self._live_logs(connected)
        for node in self.world.nodes.values():
            if node.check_at and self.now >= node.check_at and node.hostname not in connected:
                self._review(node)
        # contracts
        for c in s.contracts:
            if c.status == "accepted" and c.kind != "find" and C.is_complete(c, self.world):
                self.complete(c)
            elif c.status == "accepted" and self.now > c.deadline:
                c.status = "failed"
                s.rating = max(0, s.rating - 3)
                self.mail("Blackrelay Contracts <board@blackrelay.net>",
                          f"Contract {c.id} failed", "The deadline passed. (-3 rating)")
            elif c.status == "open" and self.now > c.deadline:
                c.status = "expired"
        s.contracts = [c for c in s.contracts if c.status != "expired"]
        open_count = sum(1 for c in s.contracts if c.status == "open")
        if self.now >= s.next_contract_at:
            if open_count < 8:
                self.spawn_contract()
            s.next_contract_at = self.now + s.rng.randint(60, 180)
        if s.tutorial_step >= 0:
            for msg in tutorial.advance(self):
                self.notify(msg, "tutorial")

    def _review(self, node: Node) -> None:
        s = self.state
        node.check_at = 0.0
        if node.footprint <= 0:
            return
        hop_cover = max(0.15, 1.0 - 0.2 * node.footprint_hops)
        chance = node.footprint / 100.0 * hop_cover
        if node.kind == "sandbox":
            chance = 0.0
        if s.rng.random() < chance:
            self.caught(node, f"{node.title} reviewed its records and followed your "
                              f"footprint back to your gateway.")
        else:
            self.news(f"{node.title} investigates suspicious activity",
                      "Investigators say the trail went cold.")
        node.footprint = 0.0
