"""top / htop: a live process viewer."""

from __future__ import annotations

import random

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from ..game import clock


class TopScreen(Screen):
    AUTO_FOCUS = None          # keys go to the screen, not the hidden PID box
    CSS = """
    TopScreen { background: $background; layout: vertical; }
    #top-head { height: auto; padding: 0 1; }
    #top-table { height: 1fr; padding: 0 1; }
    #top-prompt { height: 1; display: none; padding: 0 1; }
    #top-prompt Input { border: none; height: 1; padding: 0; width: 20; }
    #top-keys { height: 1; background: $panel; padding: 0 1; }
    """
    BINDINGS = [
        Binding("q,escape,f10", "quit_top", show=False),
        Binding("P", "sort('cpu')", show=False),
        Binding("M", "sort('mem')", show=False),
        Binding("N", "sort('pid')", show=False),
        Binding("k,f9", "kill", show=False),
    ]

    def __init__(self, procs, ctx, style: str = "top"):
        super().__init__()
        self.get_procs = procs
        self.ctx = ctx
        self.style = style
        self.sort = "cpu"
        self.rng = random.Random()
        self.message = ""

    def compose(self) -> ComposeResult:
        yield Static(id="top-head")
        yield Static(id="top-table")
        with Horizontal(id="top-prompt"):
            yield Label(Text("PID to signal/kill [default pid = none]: "))
            yield Input(id="top-pid", disabled=True)
        yield Static(id="top-keys")

    def on_mount(self) -> None:
        self.refresh_view()
        self.set_interval(1.0, self.refresh_view)
        keys = ("q quit   P sort by CPU   M sort by memory   N sort by PID   k kill"
                if self.style == "top" else
                "F9 kill   F10 quit   P CPU%   M MEM%   N PID")
        self.query_one("#top-keys", Static).update(Text(keys, "bold"))

    def refresh_view(self) -> None:
        game = self.ctx.game
        procs = self.get_procs()
        for p in procs:
            if p.job is not None:
                p.cpu = round(self.rng.uniform(0.0, 6.0), 1)
            elif p.pid > 600:
                p.cpu = round(max(0.0, p.cpu + self.rng.uniform(-0.4, 0.6)), 1)
        key = {"cpu": lambda p: -p.cpu, "mem": lambda p: -p.mem, "pid": lambda p: p.pid}[self.sort]
        procs.sort(key=key)
        now = clock.to_dt(game.now).strftime("%H:%M:%S")
        ncpu = {1: 2, 2: 4, 3: 8, 4: 16}[game.state.hw["cpu"]]
        total_mem = {1: 8, 2: 16, 3: 32, 4: 64}[game.state.hw["cpu"]] * 1024
        used = sum(p.mem for p in procs) / 100 * total_mem + total_mem * 0.18
        busy = sum(p.cpu for p in procs) / ncpu
        load = [round(busy / 50 + self.rng.uniform(0, 0.1), 2) for _ in range(3)]
        head = Text()
        if self.style == "htop":
            for i in range(ncpu):
                pct = min(100.0, self.rng.uniform(0, busy * 2 + 3))
                bar_len = 30
                full = int(pct / 100 * bar_len)
                head.append(f"{i:>3}[", "bold")
                head.append("|" * full, "green" if pct < 60 else "yellow" if pct < 85 else "red")
                head.append(" " * (bar_len - full) + f"{pct:5.1f}%]", "bold")
                head.append("   " if i % 2 == 0 else "\n")
            if ncpu % 2:
                head.append("\n")
            mem_frac = used / total_mem
            head.append("  Mem[", "bold")
            head.append("|" * int(mem_frac * 30), "green")
            head.append(" " * (30 - int(mem_frac * 30)) + f"{used / 1024:.2f}G/{total_mem / 1024:.1f}G]\n",
                        "bold")
            head.append(f"  Tasks: {len(procs)}; 1 running   Load average: {load[0]} {load[1]} {load[2]}   "
                        f"Uptime: {clock.fmt_duration(game.now + 4500)}\n")
        else:
            head.append(f"top - {now} up 3 days,  1 user,  load average: "
                        f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}\n")
            head.append(f"Tasks: {len(procs):>3} total,   1 running, {len(procs) - 1:>3} sleeping,   "
                        "0 stopped,   0 zombie\n")
            head.append(f"%Cpu(s): {busy:4.1f} us,  0.7 sy,  0.0 ni, {100 - busy - 0.7:4.1f} id,  "
                        "0.0 wa,  0.0 hi,  0.1 si,  0.0 st\n")
            head.append(f"MiB Mem : {total_mem:8.1f} total, {total_mem - used:8.1f} free, "
                        f"{used:8.1f} used, {total_mem * 0.3:8.1f} buff/cache\n")
            head.append(f"MiB Swap:   2048.0 total,   2048.0 free,      0.0 used. "
                        f"{total_mem - used:8.1f} avail Mem\n")
        if self.message:
            head.append(self.message + "\n", "yellow")
        self.query_one("#top-head", Static).update(head)
        table = Text()
        table.append(f"{'PID':>7} {'USER':<9} {'PR':>3} {'NI':>3} {'VIRT':>7} {'RES':>6} S "
                     f"{'%CPU':>5} {'%MEM':>5}     TIME+ COMMAND\n", "reverse")
        for p in procs:
            virt = 10000 + p.pid * 13 % 90000
            style = "bold" if p.job is not None or p.shell else None
            if self.style == "htop" and p.user == "root":
                style = (style or "") + " red"
            table.append(f"{p.pid:>7} {p.user[:9]:<9} {20:>3} {0:>3} {virt:>7} {virt // 9:>6} "
                         f"{'R' if p.cpu > 3 else 'S'} {p.cpu:>5.1f} {p.mem:>5.1f}   0:00.{p.pid % 97:02d} "
                         f"{p.cmd[:max(10, (self.size.width or 120) - 66)]}\n", style)
        self.query_one("#top-table", Static).update(table)

    def action_sort(self, key: str) -> None:
        self.sort = key
        self.refresh_view()

    def action_quit_top(self) -> None:
        if self.query_one("#top-prompt").display:
            self._close_prompt()
            return
        self.dismiss(None)

    def _close_prompt(self) -> None:
        self.query_one("#top-prompt").display = False
        self.query_one("#top-pid", Input).disabled = True
        self.set_focus(None)

    def action_kill(self) -> None:
        self.query_one("#top-prompt").display = True
        inp = self.query_one("#top-pid", Input)
        inp.disabled = False
        inp.value = ""
        inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        from ..shell.cmd_proc import _kill_proc
        value = event.value.strip()
        self._close_prompt()
        if not value.isdigit():
            self.message = ""
            return
        procs = self.get_procs()
        p = next((p for p in procs if p.pid == int(value)), None)
        if p is None:
            self.message = f"Failed signal pid '{value}' with 15: No such process"
        else:
            err = _kill_proc(self.ctx, p, 15, by_pid=True)
            self.message = f"Failed signal pid '{value}' with 15: {err}" if err else f"Sent signal 15 to {value}"
        self.refresh_view()
