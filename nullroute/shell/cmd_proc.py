"""Processes and job control: ps, top, kill, jobs, fg, journalctl, uptime, free."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from ..game import clock, store
from ..game.world import GATEWAY
from .commands import cmd, c_tail
from .core import Ctx

SIGNALS = {"HUP": 1, "INT": 2, "QUIT": 3, "KILL": 9, "TERM": 15, "STOP": 19, "CONT": 18}


@dataclass
class Proc:
    pid: int
    user: str
    cmd: str
    tty: str = "?"
    cpu: float = 0.0
    mem: float = 0.1
    start: str = "Mar13"
    stat: str = "Ss"
    job: object = None           # shell Job for background jobs
    shell: bool = False          # your own bash


def processes(ctx: Ctx, node_name: str | None = None) -> list[Proc]:
    """The process table of a node: system services plus your shells and jobs."""
    shell = ctx.shell
    node = ctx.game.world.nodes[node_name or ctx.frame.node]
    rng = random.Random(node.hostname)
    live = random.Random()
    base = [(1, "root", "/sbin/init"), (2, "root", "[kthreadd]"),
            (231, "root", "/lib/systemd/systemd-journald"),
            (512, "syslog", "/usr/sbin/rsyslogd -n -iNONE"),
            (540, "root", "/usr/sbin/cron -f"),
            (602, "root", "sshd: /usr/sbin/sshd -D [listener] 0 of 10-100 startups")]
    if node.kind == "gateway":
        base += [(811, "root", "/usr/sbin/gatewayd --uplink eth0"),
                 (830, "root", "/usr/lib/nullroute/tracewatch --daemon")]
    elif node.kind == "front":
        base += [(rng.randint(700, 900), "root", "nginx: master process /usr/sbin/nginx"),
                 (rng.randint(901, 990), "www-data", "nginx: worker process"),
                 (rng.randint(991, 1100), "www-data", "php-fpm: pool www"),
                 (rng.randint(1101, 1200), "root", f"/opt/ice/iced --layers {len(node.layers)}")]
    elif node.kind == "core":
        base += [(rng.randint(700, 900), "postgres", "/usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql"),
                 (rng.randint(901, 990), "root", "/usr/bin/rsync --daemon --no-detach"),
                 (rng.randint(991, 1100), "root", f"/opt/ice/iced --layers {len(node.layers)}")]
    else:
        base += [(rng.randint(700, 900), "root", "/usr/sbin/nginx -g daemon off;")]
    procs = [Proc(pid, user, c, cpu=round(live.uniform(0, 1.5), 1), mem=round(rng.uniform(0.1, 3.0), 1))
             for pid, user, c in base]
    # your shells
    for f in shell.frames:
        if f.node == node.hostname:
            pid = 3000 + (abs(hash((f.node, f.user))) % 900)
            procs.append(Proc(pid, f.user, "-bash", tty="pts/0", cpu=0.0, mem=0.2,
                              start=clock.to_dt(ctx.game.now).strftime("%H:%M"), stat="Ss",
                              shell=True))
    for j in shell.jobs:
        if j.node == node.hostname:
            procs.append(Proc(j.pid, shell.frame.user if j.node != GATEWAY else shell.handle,
                              j.text, tty="pts/0", cpu=round(live.uniform(0, 4), 1), mem=0.3,
                              start=clock.to_dt(ctx.game.now).strftime("%H:%M"), stat="S", job=j))
    return sorted(procs, key=lambda p: p.pid)


@cmd("ps", "list running processes", "ps [aux | -ef]",
     "Without options: only the processes in your terminal.\n"
     "  ps aux    every process, BSD style (USER, %CPU, %MEM, COMMAND)\n"
     "  ps -ef    every process, System V style (UID, PID, PPID, CMD)\n"
     "Tip: ps aux | grep NAME  finds a process by name.", group="process")
async def c_ps(ctx: Ctx) -> int:
    procs = processes(ctx)
    opts = "".join(a.lstrip("-") for a in ctx.args)
    me = Proc(ctx.shell.new_pid(), ctx.user, "ps " + " ".join(ctx.args), tty="pts/0", stat="R+")
    if not opts:
        ctx.write("    PID TTY          TIME CMD")
        for p in procs + [me]:
            if p.tty == "pts/0":
                ctx.write(f"{p.pid:>7} pts/0    00:00:00 {p.cmd.split()[0].lstrip('-')}")
        return 0
    if "e" in opts or "f" in opts:
        ctx.write("UID          PID    PPID  C STIME TTY          TIME CMD")
        for p in procs + [me]:
            ppid = 0 if p.pid == 1 else 1 if not p.tty.startswith("pts") else 3000
            ctx.write(f"{p.user:<8} {p.pid:>7} {ppid:>7}  0 {p.start:<5} {p.tty:<8} 00:00:00 {p.cmd}")
        return 0
    ctx.write("USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND")
    for p in procs + [me]:
        vsz = 10000 + p.pid * 13 % 90000
        ctx.write(f"{p.user:<10} {p.pid:>5} {p.cpu:>4} {p.mem:>4} {vsz:>6} {vsz // 9:>5} "
                  f"{p.tty:<8} {p.stat:<4} {p.start:<6} 0:00 {p.cmd}")
    return 0


@cmd("pgrep", "find process IDs by name", "pgrep [-l] PATTERN", group="process")
async def c_pgrep(ctx: Ctx) -> int:
    args = [a for a in ctx.args if not a.startswith("-")]
    if not args:
        ctx.err("no matching criteria specified")
        return 2
    found = False
    for p in processes(ctx):
        if args[0] in p.cmd:
            found = True
            ctx.write(f"{p.pid} {p.cmd.split()[0]}" if "-l" in ctx.args else str(p.pid))
    return 0 if found else 1


def _signal(args: list[str]) -> tuple[int, list[str]]:
    sig = 15
    rest = []
    for a in args:
        if a.startswith("-") and len(a) > 1 and not a[1:].lstrip("-").isdigit() and a != "-l":
            name = a[1:].upper().removeprefix("SIG")
            if name == "S":
                continue
            sig = SIGNALS.get(name, 15)
        elif a.startswith("-") and a[1:].isdigit():
            sig = int(a[1:])
        else:
            rest.append(a)
    return sig, rest


def _kill_proc(ctx: Ctx, p: Proc, sig: int, by_pid: bool) -> str | None:
    """Returns an error message, or None on success."""
    if p.job is not None:
        if not ctx.is_root and p.user != ctx.user:
            return "Operation not permitted"
        p.job.task.cancel()
        if by_pid:
            ctx.game.state.flags.add("killed_by_pid")
        ctx.game.award("kill")
        return None
    if p.shell:
        if sig == 9:
            return "refusing to kill your own login shell (use exit)"
        return None                      # interactive bash ignores SIGTERM
    if ctx.frame.node != GATEWAY:
        return "Operation not permitted (the node's ICE protects its services)"
    if p.pid == 1:
        return None                      # init ignores signals it doesn't handle
    if not ctx.is_root:
        return "Operation not permitted"
    svc = p.cmd.split()[0].rsplit("/", 1)[-1].rstrip(":")
    ctx.game.syslog("systemd", f"{svc}.service: Main process exited, code=killed, status={sig}/"
                               f"{next((k for k, v in SIGNALS.items() if v == sig), 'TERM')}")
    ctx.game.syslog("systemd", f"{svc}.service: Scheduled restart job, restart counter is at 1.")
    ctx.game.syslog("systemd", f"Started {svc}.service.")
    ctx.game.award("kill")
    return None


@cmd("kill", "send a signal to a process", "kill [-9|-TERM|-KILL] PID|%JOB ...",
     "Asks a process to stop (signal TERM, 15). -9 (KILL) forces it.\n"
     "  kill 4123      stop process 4123      kill %1    stop background job 1\n"
     "  kill -l       list signals\n"
     "You may only kill your own processes; root (sudo) may kill any.\n"
     "System services on your gateway are restarted by systemd.", group="process")
async def c_kill(ctx: Ctx) -> int:
    if "-l" in ctx.args:
        ctx.write(" ".join(f"{v}) SIG{k}" for k, v in sorted(SIGNALS.items(), key=lambda kv: kv[1])))
        return 0
    sig, targets = _signal(ctx.args)
    if not targets:
        ctx.write("kill: usage: kill [-s sigspec | -n signum | -sigspec] pid | jobspec ...")
        return 2
    status = 0
    procs = processes(ctx)
    for t in targets:
        if t.startswith("%"):
            job = ctx.shell.find_job(t)
            if job is None:
                ctx.err(f"{t}: no such job")
                status = 1
                continue
            job.task.cancel()
            ctx.game.award("kill")
            continue
        if not t.isdigit():
            ctx.err(f"{t}: arguments must be process or job IDs")
            status = 1
            continue
        p = next((p for p in procs if p.pid == int(t)), None)
        if p is None:
            ctx.err(f"({t}) - No such process")
            status = 1
            continue
        err = _kill_proc(ctx, p, sig, by_pid=True)
        if err:
            ctx.err(f"({t}) - {err}")
            status = 1
    await asyncio.sleep(0.05)
    return status


@cmd("killall", "kill processes by name", "killall NAME", group="process")
async def c_killall(ctx: Ctx) -> int:
    sig, names = _signal(ctx.args)
    if not names:
        ctx.write("Usage: killall NAME")
        return 1
    hit = False
    for p in processes(ctx):
        if p.cmd.split()[0].rsplit("/", 1)[-1] == names[0] and not p.shell:
            hit = True
            err = _kill_proc(ctx, p, sig, by_pid=False)
            if err:
                ctx.err(f"{names[0]}({p.pid}): {err}")
    if not hit:
        ctx.write(f"{names[0]}: no process found")
        return 1
    return 0


@cmd("pkill", "kill processes matching a pattern", "pkill PATTERN", group="process")
async def c_pkill(ctx: Ctx) -> int:
    sig, names = _signal(ctx.args)
    if not names:
        ctx.write("Usage: pkill PATTERN")
        return 2
    hit = False
    for p in processes(ctx):
        if names[0] in p.cmd and not p.shell and p.job is not None:
            hit = True
            _kill_proc(ctx, p, sig, by_pid=False)
    return 0 if hit else 1


@cmd("jobs", "list background jobs", "jobs [-l]", group="process")
async def c_jobs(ctx: Ctx) -> int:
    jobs = ctx.shell.jobs
    for i, j in enumerate(jobs):
        mark = "+" if i == len(jobs) - 1 else "-" if i == len(jobs) - 2 else " "
        pid = f"{j.pid} " if "-l" in ctx.args else ""
        ctx.write(f"[{j.id}]{mark}  {pid}{j.status:<22}{j.text} &")
    return 0


@cmd("fg", "bring a background job to the foreground", "fg [%JOB]",
     "Brings a background job back so it has your terminal again.\n"
     "Ctrl+C then stops it.", group="process")
async def c_fg(ctx: Ctx) -> int:
    job = ctx.shell.find_job(ctx.args[0] if ctx.args else "")
    if job is None:
        ctx.err(f"{ctx.args[0] if ctx.args else 'current'}: no such job")
        return 1
    ctx.write(job.text)
    ctx.game.award("fg")
    try:
        await asyncio.shield(job.task)
    except asyncio.CancelledError:
        job.task.cancel()
        raise
    except Exception:  # noqa: BLE001
        return 1
    return 0


@cmd("bg", "resume a job in the background", "bg [%JOB]", group="process")
async def c_bg(ctx: Ctx) -> int:
    job = ctx.shell.find_job(ctx.args[0] if ctx.args else "")
    if job is None:
        ctx.err(f"{ctx.args[0] if ctx.args else 'current'}: no such job")
        return 1
    ctx.err(f"job {job.id} already in background")
    return 1


@cmd("top", "live view of running processes", "top",
     "Shows the busiest processes, refreshed every second.\n"
     "Keys: q quit, P sort by CPU, M sort by memory, k kill a process.", group="process")
async def c_top(ctx: Ctx) -> int:
    ctx.game.award("top")
    await ctx.ui.open_view("top", procs=lambda: processes(ctx), ctx=ctx, style="top")
    return 0


@cmd("htop", "colourful interactive process viewer", "htop", group="process")
async def c_htop(ctx: Ctx) -> int:
    ctx.game.award("top")
    await ctx.ui.open_view("top", procs=lambda: processes(ctx), ctx=ctx, style="htop")
    return 0


@cmd("journalctl", "read the system journal", "journalctl [-n N] [-f] [-u UNIT]",
     "Shows the system log. -n N the last N lines, -f follow new lines,\n"
     "-u UNIT only lines from one service (e.g. -u CRON, -u mail).", group="process")
async def c_journalctl(ctx: Ctx) -> int:
    args = list(ctx.args)
    n = 40
    unit = None
    follow = "-f" in args
    if "-n" in args:
        i = args.index("-n")
        try:
            n = int(args[i + 1])
        except (IndexError, ValueError):
            pass
    if "-u" in args:
        i = args.index("-u")
        unit = args[i + 1] if i + 1 < len(args) else None
    if follow:
        ctx.argv = ["tail", "-n", str(min(n, 10)), "-f", "/var/log/syslog"]
        ctx.args = ctx.argv[1:]
        return await c_tail(ctx)
    node = ctx.fs.get("/var/log/syslog")
    if node is None:
        ctx.write("-- No entries --")
        return 0
    ctx.need(node, "r", "/var/log/syslog")
    lines = node.content.splitlines()
    if unit:
        lines = [l for l in lines if unit.lower() in l.lower().split(": ", 1)[0]]
    for l in lines[-n:]:
        ctx.write(l)
    return 0


@cmd("uptime", "how long the system has been running", "uptime", group="process")
async def c_uptime(ctx: Ctx) -> int:
    now = clock.to_dt(ctx.game.now).strftime("%H:%M:%S")
    up = int(ctx.game.now) + 3 * 1440 + 131
    d, rem = divmod(up, 1440)
    h, m = divmod(rem, 60)
    load = [round(0.05 + 0.3 * len(ctx.shell.jobs) + random.random() * 0.2, 2) for _ in range(3)]
    ctx.write(f" {now} up {d} days, {h:>2}:{m:02d},  1 user,  load average: "
              f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")
    return 0


@cmd("free", "show memory usage", "free [-h]", group="process")
async def c_free(ctx: Ctx) -> int:
    total = {1: 8, 2: 16, 3: 32, 4: 64}[ctx.game.state.hw["cpu"]] * 1024
    used = int(total * 0.23) + 37 * len(ctx.shell.jobs)
    cache = int(total * 0.31)
    free = total - used - cache
    if "-h" in ctx.args:
        f = lambda v: f"{v / 1024:.1f}Gi"  # noqa: E731
    else:
        f = lambda v: str(v * 1024)  # noqa: E731
    ctx.write("               total        used        free      shared  buff/cache   available")
    ctx.write(f"Mem:    {f(total):>12}{f(used):>12}{f(free):>12}{f(12):>12}{f(cache):>12}{f(total - used):>12}")
    ctx.write(f"Swap:   {f(2048):>12}{f(0):>12}{f(2048):>12}")
    return 0
