"""Network diagnostics: ping, traceroute, host, nslookup, dig, ip, ifconfig."""

from __future__ import annotations

import asyncio
import math
import random

from ..game import clock
from ..game.world import GATEWAY
from .commands import cmd
from .core import Ctx

DNS_SERVER = "10.53.0.1"


def _latency(a, b, rng: random.Random) -> float:
    (x1, y1), (x2, y2) = a.loc, b.loc
    dist = math.hypot(x1 - x2, (y1 - y2) * 2.2)
    return 2.0 + dist * 3.1 + rng.uniform(0, 4.0)


def _here(ctx: Ctx):
    return ctx.game.world.nodes[ctx.frame.node]


def _filtered(node, now: float) -> bool:
    """Nodes with live ICE drop ICMP and UDP probes, like a real firewall."""
    return bool(node.layers) and not node.is_open(now)


@cmd("ping", "check whether a host answers", "ping [-c COUNT] HOST",
     "Sends ICMP echo requests once a second and prints the replies.\n"
     "Runs until you press Ctrl+C unless you give -c COUNT.\n"
     "No reply doesn't always mean the host is down: firewalls (and ICE) often\n"
     "drop ping packets on purpose.", group="network")
async def c_ping(ctx: Ctx) -> int:
    args = list(ctx.args)
    count = None
    if "-c" in args:
        i = args.index("-c")
        try:
            count = max(1, int(args[i + 1]))
        except (IndexError, ValueError):
            ctx.err("invalid argument for -c")
            return 2
        del args[i:i + 2]
    hosts = [a for a in args if not a.startswith("-")]
    if not hosts:
        ctx.err("usage error: Destination address required")
        return 2
    node = ctx.game.node(hosts[0])
    if node is None:
        ctx.err(f"{hosts[0]}: Name or service not known")
        return 2
    ctx.game.award("ping")
    here = _here(ctx)
    rng = random.Random()
    name = node.hostname
    ctx.write(f"PING {name} ({node.ip}) 56(84) bytes of data.")
    sent = recv = 0
    times: list[float] = []
    drop = _filtered(node, ctx.game.now)
    try:
        while count is None or sent < count:
            if sent:
                await asyncio.sleep(1.0)
            sent += 1
            if drop:
                continue
            t = 0.04 if node is here else _latency(here, node, rng)
            recv += 1
            times.append(t)
            ttl = 64 if node is here else 64 - rng.randint(6, 14)
            ctx.write(f"64 bytes from {name} ({node.ip}): icmp_seq={sent} ttl={ttl} time={t:.1f} ms")
        if drop:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        _ping_stats(ctx, name, sent, recv, times)
        raise
    _ping_stats(ctx, name, sent, recv, times)
    return 0 if recv else 1


def _ping_stats(ctx: Ctx, name: str, sent: int, recv: int, times: list[float]) -> None:
    loss = 0 if not sent else int(round((sent - recv) * 100 / sent))
    ctx.write("")
    ctx.write(f"--- {name} ping statistics ---")
    ctx.write(f"{sent} packets transmitted, {recv} received, {loss}% packet loss, time {max(0, sent - 1) * 1001}ms")
    if times:
        avg = sum(times) / len(times)
        mdev = math.sqrt(sum((t - avg) ** 2 for t in times) / len(times))
        ctx.write(f"rtt min/avg/max/mdev = {min(times):.3f}/{avg:.3f}/{max(times):.3f}/{mdev:.3f} ms")
    elif sent:
        ctx.write("(no replies - the host is down, or a firewall drops ping)", "dim")


@cmd("traceroute", "show the hops on the way to a host", "traceroute HOST",
     "Lists every hop a connection from here passes through, with three\n"
     "round-trip times per hop. From your gateway it follows your bounce route,\n"
     "so it's a quick way to see what 'route' actually does.\n"
     "* * * means that hop didn't answer (often a firewall).", group="network")
async def c_traceroute(ctx: Ctx) -> int:
    hosts = [a for a in ctx.args if not a.startswith("-")]
    if not hosts:
        ctx.write("Usage: traceroute HOST")
        return 2
    node = ctx.game.node(hosts[0])
    if node is None:
        ctx.write(f"{hosts[0]}: Name or service not known", "error")
        ctx.write(f"Cannot handle \"host\" cmdline arg `{hosts[0]}' on position 1 (argc 1)", "error")
        return 2
    world = ctx.game.world
    here = _here(ctx)
    if ctx.at_gateway:
        hops = [h for h in ctx.game.state.route if h != node.hostname]
    else:
        hops = []
    path = [world.nodes[h] for h in hops] + [node]
    rng = random.Random()
    ctx.write(f"traceroute to {node.hostname} ({node.ip}), 30 hops max, 60 byte packets")
    n = 1
    if here.kind == "gateway":
        ctx.write(f" {n}  _gateway (192.168.1.1)  0.412 ms  0.388 ms  0.371 ms")
        n += 1
    prev = here
    acc = 0.5
    for hop in path:
        await asyncio.sleep(0.35)
        if hop is node and _filtered(node, ctx.game.now):
            ctx.write(f"{n:>2}  * * *")
            ctx.write(f"{n + 1:>2}  * * *")
            ctx.write("     (the target's ICE drops traceroute probes)", "dim")
            break
        acc += _latency(prev, hop, rng)
        t = [acc + rng.uniform(-1, 2) for _ in range(3)]
        ctx.write(f"{n:>2}  {hop.hostname} ({hop.ip})  {t[0]:.3f} ms  {t[1]:.3f} ms  {t[2]:.3f} ms")
        prev = hop
        n += 1
    ctx.game.award("traceroute")
    return 0


def _lookup(ctx: Ctx, name: str):
    """Resolve a name or an IP (reverse lookup)."""
    world = ctx.game.world
    name = name.rstrip(".").lower()
    for n in world.nodes.values():
        if n.hostname == name or n.ip == name:
            return n
    return None


def _is_ip(text: str) -> bool:
    parts = text.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


@cmd("host", "look up a host name (DNS)", "host NAME|IP",
     "Turns a name into an IP address, or an IP address back into a name.", group="network")
async def c_host(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.write("Usage: host [-v] NAME [SERVER]")
        return 1
    q = ctx.args[-1] if len(ctx.args) == 1 else ctx.args[0]
    node = _lookup(ctx, q)
    await asyncio.sleep(0.2)
    if node is None:
        ctx.write(f"Host {q} not found: 3(NXDOMAIN)")
        return 1
    if _is_ip(q):
        rev = ".".join(reversed(q.split(".")))
        ctx.write(f"{rev}.in-addr.arpa domain name pointer {node.hostname}.")
    else:
        ctx.write(f"{node.hostname} has address {node.ip}")
        if node.kind == "front":
            ctx.write(f"{node.hostname} mail is handled by 10 mx.{node.corp}.")
    return 0


@cmd("nslookup", "query DNS for a name", "nslookup NAME", group="network")
async def c_nslookup(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.write("Usage: nslookup NAME")
        return 1
    q = ctx.args[0]
    node = _lookup(ctx, q)
    await asyncio.sleep(0.2)
    ctx.write(f"Server:\t\t{DNS_SERVER}\nAddress:\t{DNS_SERVER}#53\n")
    if node is None:
        ctx.write(f"** server can't find {q}: NXDOMAIN")
        return 1
    if _is_ip(q):
        rev = ".".join(reversed(q.split(".")))
        ctx.write(f"{rev}.in-addr.arpa\tname = {node.hostname}.")
    else:
        ctx.write("Non-authoritative answer:")
        ctx.write(f"Name:\t{node.hostname}\nAddress: {node.ip}")
    return 0


@cmd("dig", "detailed DNS lookup", "dig NAME [+short]", group="network")
async def c_dig(ctx: Ctx) -> int:
    args = [a for a in ctx.args if not a.startswith("+")]
    short = "+short" in ctx.args
    if not args:
        ctx.write("Usage: dig NAME [+short]")
        return 1
    q = args[0]
    node = _lookup(ctx, q)
    await asyncio.sleep(0.25)
    if short:
        if node:
            ctx.write(node.ip)
        return 0
    status = "NOERROR" if node else "NXDOMAIN"
    ctx.write(f"\n; <<>> DiG 9.18.24 <<>> {q}")
    ctx.write(";; global options: +cmd\n;; Got answer:")
    ctx.write(f";; ->>HEADER<<- opcode: QUERY, status: {status}, id: {random.randint(1000, 65000)}")
    ctx.write(f";; flags: qr rd ra; QUERY: 1, ANSWER: {1 if node else 0}, AUTHORITY: 0, ADDITIONAL: 1\n")
    ctx.write(";; QUESTION SECTION:")
    ctx.write(f";{q}.\t\t\tIN\tA\n")
    if node:
        ctx.write(";; ANSWER SECTION:")
        ctx.write(f"{node.hostname}.\t300\tIN\tA\t{node.ip}\n")
    ctx.write(f";; Query time: {random.randint(8, 60)} msec")
    ctx.write(f";; SERVER: {DNS_SERVER}#53({DNS_SERVER}) (UDP)")
    ctx.write(";; MSG SIZE  rcvd: 56\n")
    return 0 if node else 1


# ====================================================================== nmap
SERVICES = {
    "gateway": [(22, "ssh", "OpenSSH 9.6p1 Debian 4 (protocol 2.0)")],
    "relay": [(22, "ssh", "relayd 2.4 (open jump host)")],
    "agency": [(22, "ssh", "Blackrelay BBS 3.1"), (443, "https", "nginx 1.24.0")],
    "drop": [(22, "ssh", "OpenSSH 9.6p1 (sftp-only)")],
    "sandbox": [(22, "ssh", "OpenSSH 9.6p1 Debian 4"), (80, "http", "nginx 1.24.0")],
    "front": [(22, "ssh", "OpenSSH 9.2p1 Debian 2"), (80, "http", "nginx 1.22.1"),
              (443, "https", "nginx 1.22.1")],
    "core": [(22, "ssh", "OpenSSH 9.2p1 Debian 2"), (873, "rsync", "(protocol version 31)"),
             (5432, "postgresql", "PostgreSQL DB 16.2")],
}


def _parse_ports(spec: str) -> set[int] | None:
    if spec in ("-", "1-65535"):
        return None
    out: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


@cmd("nmap", "network scanner: which ports and services are open", "nmap [-sV] [-p PORTS] [-sn] [-Pn] HOST...",
     "Scans a host for open TCP ports and the services behind them.\n"
     "  -sV        detect service versions\n"
     "  -p 22,80   only these ports (-p- = all)\n"
     "  -F         fast: the 100 most common ports\n"
     "  -sn        only check whether the host is up (no port scan)\n"
     "  -Pn        skip the 'is it up?' check (for hosts that drop ping)\n"
     "Ports behind live ICE show as 'filtered': a firewall drops the probes,\n"
     "so nmap can't tell what is there. 'probe' shows the ICE itself.", group="network")
async def c_nmap(ctx: Ctx) -> int:
    args = list(ctx.args)
    version = any(a in ("-sV", "-A") for a in args)
    ping_only = "-sn" in args
    no_ping = "-Pn" in args
    ports = None
    if "-p" in args:
        i = args.index("-p")
        try:
            ports = _parse_ports(args[i + 1])
        except (IndexError, ValueError):
            ctx.write("Error #487: Your port specifications are illegal.", "error")
            return 1
        del args[i:i + 2]
    for a in list(args):
        if a.startswith("-p") and len(a) > 2:
            try:
                ports = _parse_ports(a[2:])
            except ValueError:
                ctx.write("Error #487: Your port specifications are illegal.", "error")
                return 1
            args.remove(a)
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        ctx.write("Nmap 7.94 ( https://nmap.org )\nUsage: nmap [Scan Type(s)] [Options] {target specification}\n"
                  "  e.g. nmap -sV osaka.relay     (see: man nmap)")
        return 0
    stamp = clock.to_dt(ctx.game.now).strftime("%Y-%m-%d %H:%M UTC")
    ctx.write(f"Starting Nmap 7.94 ( https://nmap.org ) at {stamp}")
    here = _here(ctx)
    rng = random.Random()
    up = 0
    total_time = 0.0
    for t in targets:
        node = ctx.game.node(t)
        if node is None:
            ctx.write(f"Failed to resolve \"{t}\".", "error")
            continue
        unreachable = bool(node.parent) and ctx.frame.node != node.parent
        filtered = _filtered(node, ctx.game.now) or unreachable
        secs = 0.4 if ping_only else (1.2 + (0.8 if version else 0) + (1.5 if filtered else 0))
        await ctx.sleep(secs, f"Scanning {node.hostname}")
        total_time += secs
        lat = _latency(here, node, rng) / 1000
        if filtered and not no_ping:
            ctx.write("Note: Host seems down. If it is really up, but blocking our ping probes, try -Pn")
            continue
        up += 1
        ctx.write(f"Nmap scan report for {node.hostname} ({node.ip})")
        ctx.write(f"Host is up ({lat:.3f}s latency).")
        if ping_only:
            continue
        svcs = [s for s in SERVICES.get(node.kind, SERVICES["front"]) if ports is None or s[0] in ports]
        scanned = len(ports) if ports is not None else 1000
        if filtered:
            ctx.write(f"All {scanned} scanned ports on {node.hostname} ({node.ip}) are in ignored states.")
            ctx.write(f"Not shown: {scanned} filtered tcp ports (no-response)")
            ctx.write("(something - a firewall, or ICE - drops every probe. Try: probe "
                      f"{node.short})", "dim")
            continue
        closed = scanned - len(svcs)
        if closed > 0:
            ctx.write(f"Not shown: {closed} closed tcp ports (reset)")
        if not svcs:
            continue
        ctx.write(f"{'PORT':<9} {'STATE':<6} {'SERVICE':<11}" + (" VERSION" if version else ""))
        for port, name, ver in svcs:
            line = f"{f'{port}/tcp':<9} {'open':<6} {name:<11}"
            if version:
                line += " " + ver
            ctx.write(line.rstrip())
        if version:
            ctx.write("Service detection performed. Please report any incorrect results at https://nmap.org/submit/ .")
        ctx.game.state.known.add(node.hostname)
    n = len(targets)
    ctx.write(f"\nNmap done: {n} IP address{'es' if n != 1 else ''} ({up} host{'s' if up != 1 else ''} up) "
              f"scanned in {total_time + 0.07:.2f} seconds")
    ctx.game.award("port_scan")
    return 0


def _ifaces(ctx: Ctx) -> tuple[str, str]:
    node = _here(ctx)
    if node.hostname == GATEWAY:
        return "192.168.1.23", node.ip
    return node.ip, node.ip


@cmd("ip", "show network interfaces and routes", "ip a | ip addr | ip route", group="network")
async def c_ip(ctx: Ctx) -> int:
    sub = ctx.args[0] if ctx.args else ""
    local, public = _ifaces(ctx)
    if sub in ("a", "addr", "address"):
        ctx.write("1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000")
        ctx.write("    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00")
        ctx.write("    inet 127.0.0.1/8 scope host lo")
        ctx.write("2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000")
        ctx.write("    link/ether 52:54:00:3a:9c:1e brd ff:ff:ff:ff:ff:ff")
        ctx.write(f"    inet {local}/24 brd {local.rsplit('.', 1)[0]}.255 scope global eth0")
        if local != public:
            ctx.write(f"    (public address seen by the net: {public} - see 'curl ifconfig.me' on a real box)", "dim")
        return 0
    if sub in ("r", "route"):
        gw = local.rsplit(".", 1)[0] + ".1"
        ctx.write(f"default via {gw} dev eth0 proto dhcp metric 100")
        ctx.write(f"{local.rsplit('.', 1)[0]}.0/24 dev eth0 proto kernel scope link src {local}")
        return 0
    ctx.write("Usage: ip [ OPTIONS ] OBJECT { COMMAND | help }\n"
              "where  OBJECT := { address | route | link }\n   try: ip a   or   ip route")
    return 0 if not sub else 1


@cmd("ifconfig", "show network interfaces (older tool)", "ifconfig", group="network")
async def c_ifconfig(ctx: Ctx) -> int:
    local, _ = _ifaces(ctx)
    ctx.write("eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500")
    ctx.write(f"        inet {local}  netmask 255.255.255.0  broadcast {local.rsplit('.', 1)[0]}.255")
    ctx.write("        ether 52:54:00:3a:9c:1e  txqueuelen 1000  (Ethernet)\n")
    ctx.write("lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536")
    ctx.write("        inet 127.0.0.1  netmask 255.0.0.0")
    ctx.write("(ifconfig is old - the modern command is 'ip a')", "dim")
    return 0
