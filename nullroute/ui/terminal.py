"""Terminal panes (up to four, split screen) and the screen that holds them."""

from __future__ import annotations

import asyncio
import time

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Label, RichLog, Static

from ..game import clock, state as S
from ..game.engine import MAX_STRIKES, Game
from ..game.world import GATEWAY
from ..shell.core import Shell
from .nano import NanoScreen
from .top import TopScreen
from .views import BBSScreen, MailScreen, MapScreen

STYLES = {
    "error": "red", "warn": "yellow", "good": "green", "dim": "grey50",
    "title": "bold cyan", "accent": "magenta", "dir": "bold blue", "match": "",
    "alert": "bold white on red", "mail": "cyan", "tutorial": "bold yellow",
    "info": "cyan", "prompt": "bold green", "tip": "italic rgb(120,170,200)",
    "achievement": "bold rgb(255,200,60)",
}

LOGO = r"""
 _   _ _   _ _     _     ____   ___  _   _ _____ _____
| \ | | | | | |   | |   |  _ \ / _ \| | | |_   _| ____|
|  \| | | | | |   | |   | |_) | | | | | | | | | |  _|
| |\  | |_| | |___| |___|  _ <| |_| | |_| | | | | |___
|_| \_|\___/|_____|_____|_| \_\\___/ \___/  |_| |_____|
"""

MAX_PANES = 4


class TermLog(RichLog):
    """A RichLog that grows with its content (height: auto), so the prompt
    sits right below the last line of output like in a real terminal."""

    def write(self, *args, **kwargs):
        result = super().write(*args, **kwargs)
        self.refresh(layout=True)
        return result

    def clear(self):
        result = super().clear()
        self.refresh(layout=True)
        return result


class CommandInput(Input):
    BINDINGS = [
        Binding("tab", "complete", show=False, priority=True),
        Binding("up", "history(-1)", show=False),
        Binding("down", "history(1)", show=False),
        Binding("ctrl+c", "interrupt", show=False, priority=True),
        Binding("ctrl+d", "eof", show=False, priority=True),
        Binding("ctrl+l", "clear_screen", show=False),
        Binding("pageup", "scroll_page(-1)", show=False),
        Binding("pagedown", "scroll_page(1)", show=False),
        Binding("shift+up", "scroll_lines(-1)", show=False),
        Binding("shift+down", "scroll_lines(1)", show=False),
        Binding("shift+pageup", "scroll_page(-1)", show=False),
        Binding("shift+pagedown", "scroll_page(1)", show=False),
        Binding("ctrl+home", "scroll_edge(-1)", show=False),
        Binding("ctrl+end", "scroll_edge(1)", show=False),
    ]

    @property
    def pane(self) -> "TerminalPane":
        node = self.parent
        while node is not None and not isinstance(node, TerminalPane):
            node = node.parent
        return node

    def action_complete(self) -> None:
        self.pane.complete()

    def action_history(self, delta: int) -> None:
        self.pane.history(delta)

    def action_interrupt(self) -> None:
        self.pane.interrupt()

    def action_eof(self) -> None:
        if self.value:
            self.action_delete_right()
        else:
            self.pane.eof()

    def action_clear_screen(self) -> None:
        self.pane.clear()

    def action_scroll_page(self, direction: int) -> None:
        self.pane.scroll_by_page(direction)

    def action_scroll_lines(self, direction: int) -> None:
        self.pane.scroll_by_lines(direction * 3)

    def action_scroll_edge(self, direction: int) -> None:
        self.pane.scroll_edge(direction)


class TerminalPane(Vertical):
    """One shell session. Implements the shell's UI protocol."""

    DEFAULT_CSS = """
    TerminalPane { height: 1fr; width: 1fr; border: round $panel; padding: 0 1; }
    TerminalPane.active { border: round $accent; }
    TerminalPane.single { border: none; padding: 0 1; }
    TerminalPane .term-scroll { height: 1fr; scrollbar-size-vertical: 1; }
    TerminalPane RichLog.out { height: auto; overflow: hidden hidden; background: $background;
                               padding: 0; scrollbar-size: 0 0; }
    TerminalPane .progress { height: auto; color: $warning; display: none; }
    TerminalPane .prompt-row { height: auto; min-height: 1; }
    TerminalPane .prompt { width: auto; color: $success; text-style: bold; }
    TerminalPane CommandInput { border: none; height: 1; padding: 0; background: $background;
                                width: 1fr; }
    TerminalPane CommandInput:focus { border: none; }
    """

    def __init__(self, game: Game, index: int, welcome: str = ""):
        super().__init__()
        self.game = game
        self.index = index
        self.welcome = welcome
        self.shell = Shell(game, self)
        self.hist_pos = 0
        self.cmd_task: asyncio.Task | None = None
        self.pending_prompt = None
        self.closed = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="term-scroll"):
            yield TermLog(classes="out", wrap=True, markup=False, highlight=False,
                          auto_scroll=False, max_lines=3000, min_width=20)
            yield Static(classes="progress")
            with Horizontal(classes="prompt-row"):
                yield Label(Text(self.shell.prompt()), classes="prompt")
                yield CommandInput(classes="cmd")

    def on_mount(self) -> None:
        self.log_w = self.query_one(RichLog)
        self.log_w.can_focus = False
        self.scroller = self.query_one(".term-scroll", VerticalScroll)
        self.scroller.can_focus = False
        self.cmd = self.query_one(CommandInput)
        self.prompt_label = self.query_one(".prompt", Label)
        self.follow = True            # keep the view at the bottom as output arrives
        if self.welcome == "new" or self.welcome == "back":
            self._welcome()
        else:
            self.write(f"Terminal {self.index} - {clock.fmt_status(self.game.now)}", "dim")
        self.cmd.focus()
        self.update_title()

    def _welcome(self) -> None:
        s = self.game.state
        self.write(LOGO.strip("\n"), "accent")
        self.write("")
        if self.welcome == "new":
            self.write(f"Gateway online. Welcome, {s.handle}.", "good")
            self.write("You have new mail - type 'mail' to read it. 'tutorial' shows your next step.",
                       "tutorial")
        else:
            self.write(f"Welcome back, {s.handle}. {clock.fmt_status(s.minutes)}", "good")
            if s.unread:
                self.write(f"You have {s.unread} unread mail.", "mail")
            if not s.password:
                self.write("Your gateway has real users, sudo and apt now. Set a password for sudo "
                           "first: passwd", "tutorial")
        self.write("Type 'help' for commands. Tab completes, Ctrl+C stops a command, "
                   "PgUp/PgDn scrolls.", "dim")
        self.write("Ctrl+N opens another terminal, Alt+←/→ (or F2) switches between them.", "dim")
        self.write("")

    @property
    def game_screen(self) -> "GameScreen":
        return self.screen  # type: ignore[return-value]

    def update_title(self) -> None:
        self.border_title = f" {self.index}  {self.shell.prompt().strip()} "
        self.border_subtitle = ""

    # ------------------------------------------------------------ UI protocol
    def write(self, text: str, style: str | None = None) -> None:
        st = STYLES.get(style, style) if style else None
        for line in str(text).split("\n"):
            self.log_w.write(Text(line, style=st or ""))
        self._stick()

    def _stick(self) -> None:
        if self.follow:
            self.scroller.call_after_refresh(self.scroller.scroll_end, animate=False)

    def progress(self, text: str | None) -> None:
        p = self.query_one(".progress", Static)
        if text is None:
            p.display = False
        else:
            p.display = True
            p.update(Text(text))
        self._stick()

    async def prompt(self, label: str, secret: bool = False) -> str:
        """Ask the player for a line of input (passwords are not echoed)."""
        fut = asyncio.get_running_loop().create_future()
        self.pending_prompt = (fut, label, secret)
        self.prompt_label.update(Text(label))
        self.cmd.password = secret
        self.cmd.value = ""
        self.cmd.focus()
        try:
            return await fut
        finally:
            self.pending_prompt = None
            self.cmd.password = False
            self.prompt_label.update(Text(self.shell.prompt()))

    async def open_view(self, name: str, **kw):
        screens = {"bbs": BBSScreen, "mail": MailScreen, "map": MapScreen}
        if name == "editor":
            screen = NanoScreen(kw["path"], kw["content"], new_file=kw["new_file"],
                                write=kw["write"], read=kw["read"],
                                start_line=kw.get("start_line", 0))
        elif name == "top":
            screen = TopScreen(kw["procs"], kw["ctx"], kw.get("style", "top"))
        else:
            screen = screens[name](self.game)
        result = await self.app.push_screen_wait(screen)
        self.cmd.focus()
        return result

    def clear(self) -> None:
        self.log_w.clear()

    def quit(self) -> None:
        self.app.quit_game()

    def logout(self) -> None:
        """'exit' on the gateway: close this terminal."""
        self.call_after_refresh(self.game_screen.close_pane, self)

    def new_terminal(self) -> None:
        self.game_screen.add_pane()

    # ------------------------------------------------------------ input
    def on_descendant_focus(self, event) -> None:
        if not self.closed and self.is_attached:
            self.game_screen.set_active(self)

    def on_click(self, event: events.Click) -> None:
        self.cmd.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self.pending_prompt:
            fut, label, secret = self.pending_prompt
            value = event.value
            event.input.value = ""
            self.write(label + ("" if secret else value), "prompt")
            if not fut.done():
                fut.set_result(value)
            return
        if self.cmd_task and not self.cmd_task.done():
            self.app.bell()
            return
        line = event.value
        event.input.value = ""
        self.write(self.shell.prompt() + line, "prompt")
        self.hist_pos = 0
        self.follow = True
        self._stick()
        self.run_line(line)

    @work(exclusive=True, group="shell")
    async def run_line(self, line: str) -> None:
        self.cmd_task = asyncio.current_task()
        try:
            await self.shell.run_line(line)
        except asyncio.CancelledError:
            self.progress(None)
            self.write("^C", "dim")
        except Exception as e:  # noqa: BLE001 - never crash the game
            self.write(f"bash: internal error: {e!r}", "error")
        finally:
            self.cmd_task = None
            self.after_command()

    def after_command(self) -> None:
        if self.closed or not self.is_attached:
            return
        try:
            self.prompt_label.update(Text(self.shell.prompt()))
        except Exception:  # noqa: BLE001 - being torn down
            return
        self.update_title()
        self.game_screen.update_status()
        if self.game.state.game_over:
            self.game_screen.show_game_over()

    def interrupt(self) -> None:
        if self.cmd_task and not self.cmd_task.done():
            self.workers.cancel_group(self, "shell")
            self.cmd_task.cancel()
        else:
            self.write(self.shell.prompt() + self.cmd.value + "^C", "dim")
            self.cmd.value = ""

    def eof(self) -> None:
        """Ctrl+D on an empty line, like bash: log out (or end of input)."""
        if self.pending_prompt:
            fut = self.pending_prompt[0]
            if not fut.done():
                fut.set_result("\x04")
            return
        if self.cmd_task and not self.cmd_task.done():
            return
        self.write(self.shell.prompt() + "logout", "prompt")
        self.run_line("logout")

    def complete(self) -> None:
        before = self.cmd.value[: self.cmd.cursor_position]
        after = self.cmd.value[self.cmd.cursor_position:]
        new, cands = self.shell.complete(before)
        if cands:
            self.write(self.shell.prompt() + self.cmd.value, "dim")
            self.write("  ".join(cands), "dim")
        self.cmd.value = new + after
        self.cmd.cursor_position = len(new)

    def history(self, delta: int) -> None:
        hist = self.shell.history
        if not hist or self.pending_prompt:
            return
        self.hist_pos = max(-len(hist), min(0, self.hist_pos + delta))
        self.cmd.value = hist[self.hist_pos] if self.hist_pos < 0 else ""
        self.cmd.cursor_position = len(self.cmd.value)

    # ------------------------------------------------------------ scrolling
    def _after_scroll(self) -> None:
        s = self.scroller
        self.follow = s.scroll_target_y >= s.max_scroll_y - 0.5

    def scroll_by_page(self, direction: int) -> None:
        if direction < 0:
            self.scroller.scroll_page_up(animate=False)
        else:
            self.scroller.scroll_page_down(animate=False)
        self._after_scroll()

    def scroll_by_lines(self, n: int) -> None:
        self.scroller.scroll_relative(y=n, animate=False)
        self._after_scroll()

    def scroll_edge(self, direction: int) -> None:
        if direction < 0:
            self.scroller.scroll_home(animate=False)
            self.follow = False
        else:
            self.follow = True
            self._stick()

    # ------------------------------------------------------------ lifecycle
    def shutdown(self) -> None:
        """Hang up: drop connections and kill background jobs (SIGHUP)."""
        self.closed = True
        for job in list(self.shell.jobs):
            job.task.cancel()
        if self.cmd_task and not self.cmd_task.done():
            self.cmd_task.cancel()
        for f in self.shell.frames:
            if f.conn:
                self.game.close_conn(f.conn)


class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    ConfirmScreen { align: center middle; background: $background 60%; }
    #confirm-box { width: 64; height: auto; border: heavy $warning; padding: 1 2; background: $surface; }
    #confirm-keys { color: $text-muted; margin-top: 1; }
    """
    BINDINGS = [Binding("y,j", "answer(True)", show=False), Binding("n,escape", "answer(False)", show=False),
                Binding("enter", "answer(False)", show=False)]

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        keys = Text()
        keys.append(" Y ", "reverse bold")
        keys.append(" Yes        ")
        keys.append(" N ", "reverse bold")
        keys.append(" No (default, also Esc/Enter)")
        with Vertical(id="confirm-box"):
            yield Static(Text(self.question))
            yield Static(keys, id="confirm-keys")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class GameScreen(Screen):
    """Status bar plus 1-4 terminal panes."""

    CSS = """
    GameScreen { background: $background; layout: vertical; }
    #status { height: 1; background: $panel; padding: 0 1; }
    #panes { height: 1fr; grid-gutter: 0 0; }
    #panes.n1 { grid-size: 1 1; }
    #panes.n2 { grid-size: 2 1; }
    #panes.n3 { grid-size: 2 2; }
    #panes.n3 > TerminalPane:first-child { row-span: 2; }
    #panes.n4 { grid-size: 2 2; }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_pane", "New terminal", show=False, priority=True),
        Binding("f2,alt+right,alt+down", "cycle(1)", show=False, priority=True),
        Binding("shift+f2,alt+left,alt+up", "cycle(-1)", show=False, priority=True),
        Binding("alt+1", "jump(1)", show=False, priority=True),
        Binding("alt+2", "jump(2)", show=False, priority=True),
        Binding("alt+3", "jump(3)", show=False, priority=True),
        Binding("alt+4", "jump(4)", show=False, priority=True),
    ]

    def __init__(self, game: Game, new: bool):
        super().__init__()
        self.game = game
        self.new = new
        self.panes: list[TerminalPane] = []
        self.active: TerminalPane | None = None
        self.last_tick = time.monotonic()
        self.flash = False
        self.timers = []
        self.ending = False

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        yield Grid(id="panes", classes="n1")

    def on_mount(self) -> None:
        self.game.listeners.append(self._game_notify)
        self.game.on_caught = self._game_caught
        self.add_pane(welcome="new" if self.new else "back")
        self.timers = [self.app.set_interval(0.1, self._tick),
                       self.app.set_interval(60.0, self._autosave)]
        self.update_status()

    # ------------------------------------------------------------ panes
    def _layout(self) -> None:
        grid = self.query_one("#panes", Grid)
        for i in range(1, MAX_PANES + 1):
            grid.remove_class(f"n{i}")
        grid.add_class(f"n{len(self.panes)}")
        for p in self.panes:
            p.set_class(len(self.panes) == 1, "single")

    def add_pane(self, welcome: str = "") -> TerminalPane | None:
        if len(self.panes) >= MAX_PANES:
            if self.active:
                self.active.write(f"You already have {MAX_PANES} terminals open.", "warn")
            return None
        used = {p.index for p in self.panes}
        index = next(i for i in range(1, MAX_PANES + 1) if i not in used)
        pane = TerminalPane(self.game, index, welcome)
        self.panes.append(pane)
        self.panes.sort(key=lambda p: p.index)
        grid = self.query_one("#panes", Grid)
        before = next((p for p in self.panes if p.index > index and p.is_attached), None)
        grid.mount(pane, before=before)
        self._layout()
        self.set_active(pane)
        if len(self.panes) >= 2:
            self.game.award("split")
        return pane

    def set_active(self, pane: TerminalPane) -> None:
        if pane is self.active:
            return
        self.active = pane
        for p in self.panes:
            p.set_class(p is pane, "active")
        if pane.is_mounted:
            pane.cmd.focus()
        self.update_status()

    def close_pane(self, pane: TerminalPane) -> None:
        if pane not in self.panes or self.ending:
            return
        if len(self.panes) == 1:
            def done(ok: bool | None) -> None:
                if ok:
                    self.app.logout_to_title()
                else:
                    pane.write("Logout cancelled.", "dim")
                    pane.cmd.focus()
            self.app.push_screen(ConfirmScreen(
                "Close your last terminal and log out to the start menu?\n"
                "(The game is saved.)"), done)
            return
        pane.shutdown()
        self.panes.remove(pane)
        pane.remove()
        self._layout()
        self.active = None
        self.set_active(self.panes[0])

    def action_new_pane(self) -> None:
        self.add_pane()

    def action_cycle(self, step: int) -> None:
        if not self.panes or self.active is None:
            return
        i = self.panes.index(self.active)
        self.set_active(self.panes[(i + step) % len(self.panes)])

    def action_jump(self, index: int) -> None:
        for p in self.panes:
            if p.index == index:
                self.set_active(p)

    # ------------------------------------------------------------ game loop
    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.5, now - self.last_tick)
        self.last_tick = now
        if self.ending or self.game.state.game_over:
            return
        self.game.tick(dt)
        self.flash = not self.flash
        self.update_status()

    def stop(self) -> None:
        self.ending = True
        for t in self.timers:
            t.stop()
        for p in self.panes:
            p.shutdown()
        if self._game_notify in self.game.listeners:
            self.game.listeners.remove(self._game_notify)

    def all_home(self) -> bool:
        return not self.game.conns and all(f.node == GATEWAY for p in self.panes for f in p.shell.frames)

    def _autosave(self) -> None:
        if self.all_home() and not self.game.state.game_over and not self.ending:
            try:
                S.save(self.game.state)
            except OSError:
                pass

    def _game_notify(self, text: str, style: str) -> None:
        prefix = {"alert": "!! ", "mail": "✉ ", "good": "✓ ", "tutorial": "» ",
                  "achievement": "★ "}.get(style, "")
        if self.active is not None and self.active.is_mounted:
            self.active.write(prefix + text, style)
        if style in ("alert", "mail", "good", "achievement") and self.app.screen is not self:
            self.app.notify(text, severity="error" if style == "alert" else "information")

    def _game_caught(self, how: str) -> None:
        s = self.game.state
        for p in self.panes:
            p.shell.disconnect_all()
            if p.cmd_task and not p.cmd_task.done():
                p.cmd_task.cancel()
            p.progress(None)
            p.write("")
            p.write(" CONNECTION TERMINATED - YOU HAVE BEEN TRACED ", "alert")
            p.write(how, "error")
            p.write(f"Strikes: {s.strikes}/{MAX_STRIKES}", "error")
            p.prompt_label.update(Text(p.shell.prompt()))
            p.update_title()
        if s.game_over:
            self.show_game_over()
        elif self.app.screen is not self:
            self.app.notify("You have been traced!", severity="error")

    def show_game_over(self) -> None:
        from .title import GameOverScreen
        if self.ending:
            return
        S.delete_save(self.game.state.handle)
        self.stop()
        self.app.push_screen(GameOverScreen(self.game.state.game_over))

    def update_status(self) -> None:
        if not self.is_mounted or self.active is None:
            return
        s = self.game.state
        g = self.game
        node = g.world.nodes[self.active.shell.frame.node]
        t = Text()
        t.append(f" {node.short} ", "bold black on green" if node.kind == "gateway" else "bold black on cyan")
        if len(self.panes) > 1:
            t.append(f" T{self.active.index}/{len(self.panes)}", "bold")
        t.append(f"  ¢{s.money:,}", "green")
        t.append(f"  {s.rating_title}", "cyan")
        t.append("  strikes ", "dim")
        t.append("●" * s.strikes + "○" * (MAX_STRIKES - s.strikes), "red" if s.strikes else "dim")
        hops = len(s.route)
        t.append(f"  route {hops} hop{'s' if hops != 1 else ''}", "yellow" if hops else "red")
        tr = g.active_trace()
        if tr:
            n, c = tr
            lvl = s.sw.get("tracemon", 1)
            t.append("  TRACE ", "bold white on red" if self.flash or lvl > 1 else "bold red")
            if lvl >= 2:
                frac = n.trace_progress
                full = int(frac * 12)
                t.append(" " + "█" * full + "░" * (12 - full), "red")
                t.append(f" {int(frac * 100)}%", "bold red")
            if lvl >= 3:
                left = g.trace_left() or 0
                t.append(f" {left:.0f}s", "bold red")
        elif any(n.trace_active for n in g.world.nodes.values()):
            t.append("  trace paused", "yellow")
        if node.kind not in ("gateway",) and node.footprint > 0:
            t.append(f"  footprint {int(node.footprint)}%", "magenta")
        if s.unread:
            t.append(f"  ✉ {s.unread}", "bold cyan")
        t.append(f"   {clock.fmt_status(s.minutes)}", "dim")
        self.query_one("#status", Static).update(t)
