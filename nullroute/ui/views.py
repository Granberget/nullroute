"""Full-screen TUI views opened from the shell."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, DataTable, Footer, Input, Label, ListItem,
                             ListView, Markdown, Static, TabbedContent, TabPane,
                             TextArea)

from ..game.vfs import Identity

from ..game import clock, store
from ..game.engine import Game
from ..game.world import GATEWAY
from .docs import DOCS

WORLD_MAP = [
    "                                                                        ",
    "        .:::::::.        .::.         .:::::::::::::::::::::::::.       ",
    "  .::::::::::::::::::. .::::::     .:::::::::::::::::::::::::::::::::.  ",
    " ::::::::::::::::::::  ':::'    .::::::::::::::::::::::::::::::::::::   ",
    "  ':::::::::::::::::'          ::::::::::::::::::::::::::::::::::::'    ",
    "     ::::::::::::::'          .:::::::::::::::::::::::::::::::::::'     ",
    "     ':::::::::::::           :::::::::::::::::::::::::::::::::'.:      ",
    "      ':::::::::::'           '::::::::::::::::::::::::::::::' ::      ",
    "        ':::::::'              ::::::::':::::::::::::::::::'           ",
    "          '::::.              .::::::::. ':::::::'::::::::'            ",
    "            ':::.            ::::::::::::. ':::'  ':::' ':.            ",
    "              '::::.         ':::::::::::'   '     '::.  ':.           ",
    "               ::::::.         ':::::::::'           '::.  '::::.       ",
    "               ':::::::.        ':::::::'              '   .::::::.     ",
    "                ':::::'          :::::'                  .::::::::::.   ",
    "                 ':::'           '::::                   '::::::::::'   ",
    "                  :::             ':'                      ':'  '::'    ",
    "                  ::                                              '     ",
    "                  '                                                     ",
    "                                                                        ",
]


class GameScreen(Screen):
    """Base for views: Escape or q closes, and the game keeps ticking."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("q", "close", "Close", show=False)]

    def __init__(self, game: Game):
        super().__init__()
        self.game = game

    def action_close(self) -> None:
        self.dismiss(None)


# ====================================================================== BBS
class BBSScreen(GameScreen):
    CSS = """
    BBSScreen { background: $background; }
    #bbs-head { height: 2; padding: 0 2; background: $primary-background; color: $text; }
    #tabs { height: 1fr; }
    TabPane { height: 1fr; padding: 0; }
    .hint { height: 1; padding: 0 1; color: $text-muted; background: $surface; }
    .split { height: 1fr; }
    .split DataTable { width: 3fr; height: 1fr; }
    .detail { width: 2fr; padding: 0 1; border-left: tall $primary; }
    .detail Static { height: auto; }
    .buttons { height: auto; margin-top: 1; }
    .buttons Button { margin-right: 1; }
    #docs-list { width: 28; }
    #docs-view { width: 1fr; padding: 0 1; }
    #answer { margin-top: 1; }
    """

    TABS = ["tab-contracts", "tab-store", "tab-docs", "tab-news", "tab-account"]

    BINDINGS = [
        Binding("escape", "close", "Leave BBS"),
        Binding("1", "show_tab(0)", "Contracts"),
        Binding("2", "show_tab(1)", "Store"),
        Binding("3", "show_tab(2)", "Docs"),
        Binding("4", "show_tab(3)", "News"),
        Binding("5", "show_tab(4)", "Account"),
        Binding("a", "accept", "Accept contract"),
        Binding("x", "abandon", "Abandon contract"),
        Binding("s", "answer", "Submit answer"),
        Binding("b", "buy", "Buy item"),
        Binding("q", "close", "Leave", show=False),
    ]

    HINTS = {
        "tab-contracts": "↑/↓ choose a contract · the briefing is on the right · "
                         "a accept · x abandon · s type the answer (Find contracts)",
        "tab-store": "↑/↓ choose an item · b buy it · green = you can afford it",
        "tab-docs": "↑/↓ choose an article · Tab jumps to the text, ↑/↓ scrolls it, Shift+Tab goes back",
        "tab-news": "Latest news from the net. ↑/↓ or PgUp/PgDn scrolls.",
        "tab-account": "Your record with Blackrelay.",
    }

    def compose(self) -> ComposeResult:
        yield Static(id="bbs-head")
        with TabbedContent(id="tabs"):
            with TabPane("1 Contracts", id="tab-contracts"):
                yield Static(self.HINTS["tab-contracts"], classes="hint")
                with Horizontal(classes="split"):
                    yield DataTable(id="contracts", cursor_type="row", zebra_stripes=True)
                    with VerticalScroll(classes="detail"):
                        yield Static(id="contract-detail")
                        yield Input(placeholder="type the passphrase, Enter submits", id="answer")
                        with Horizontal(classes="buttons"):
                            yield Button("Accept (a)", id="accept", variant="success")
                            yield Button("Submit (Enter)", id="submit", variant="primary")
                            yield Button("Abandon (x)", id="abandon", variant="error")
            with TabPane("2 Store", id="tab-store"):
                yield Static(self.HINTS["tab-store"], classes="hint")
                with Horizontal(classes="split"):
                    yield DataTable(id="store", cursor_type="row", zebra_stripes=True)
                    with VerticalScroll(classes="detail"):
                        yield Static(id="store-detail")
                        with Horizontal(classes="buttons"):
                            yield Button("Buy (b)", id="buy", variant="success")
            with TabPane("3 Docs", id="tab-docs"):
                yield Static(self.HINTS["tab-docs"], classes="hint")
                with Horizontal(classes="split"):
                    yield ListView(*[ListItem(Label(t)) for t in DOCS], id="docs-list")
                    with VerticalScroll(id="docs-view"):
                        yield Markdown(next(iter(DOCS.values())), id="docs-md")
            with TabPane("4 News", id="tab-news"):
                yield Static(self.HINTS["tab-news"], classes="hint")
                with VerticalScroll(id="news-scroll"):
                    yield Static(id="news")
            with TabPane("5 Account", id="tab-account"):
                yield Static(self.HINTS["tab-account"], classes="hint")
                with VerticalScroll(id="account-scroll"):
                    yield Static(id="account")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#contracts", DataTable)
        t.add_columns("ID", "Type", "Target", "Pay", "Sec", "Deadline", "Status")
        s = self.query_one("#store", DataTable)
        s.add_columns("Item", "Type", "Price", "")
        self.refresh_all()
        self.set_interval(1.0, self.refresh_head)
        t.focus()

    # ---------------------------------------------------------------- navigation
    @property
    def active_tab(self) -> str:
        return self.query_one("#tabs", TabbedContent).active

    def action_show_tab(self, index: int) -> None:
        self.query_one("#tabs", TabbedContent).active = self.TABS[index]
        self._focus_tab()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._focus_tab()

    def _focus_tab(self) -> None:
        main = {"tab-contracts": "#contracts", "tab-store": "#store", "tab-docs": "#docs-list",
                "tab-news": "#news-scroll", "tab-account": "#account-scroll"}[self.active_tab]
        self.query_one(main).focus()
        self.refresh_bindings()

    def check_action(self, action: str, parameters) -> bool | None:
        """Only show the keys that make sense on the current tab."""
        tab = self.active_tab if self.is_mounted else "tab-contracts"
        if action in ("accept", "abandon", "answer"):
            if tab != "tab-contracts":
                return False
            c = self._selected_contract()
            if c is None:
                return False
            if action == "accept":
                return c.status == "open"
            if action == "abandon":
                return c.status == "accepted" and c.kind != "training"
            return c.status == "accepted" and c.kind == "find"
        if action == "buy":
            return tab == "tab-store" and self._selected_item() is not None
        return True

    # ---------------------------------------------------------------- data
    def refresh_head(self) -> None:
        s = self.game.state
        self.query_one("#bbs-head", Static).update(Text.assemble(
            ("BLACKRELAY ", "bold magenta"), ("// runner board   ", "dim"),
            (f"{s.handle}  ", "bold"), (f"¢{s.money:,}  ", "green"),
            (f"{s.rating_title} ({s.rating})  ", "cyan"),
            (f"strikes {s.strikes}/3  ", "red" if s.strikes else "dim"),
            (clock.fmt_status(self.game.now), "dim"),
            ("\n1-5 switch tab · ↑/↓ move · Tab next field · Esc leave the BBS (back to your shell)",
             "dim")))

    def refresh_all(self) -> None:
        self.refresh_head()
        self._fill_contracts()
        self._fill_store()
        self._fill_news()
        self._fill_account()

    def _contracts(self):
        s = self.game.state
        shown = [c for c in s.contracts if c.status in ("accepted", "open")]
        shown.sort(key=lambda c: (c.status != "accepted", c.difficulty, c.pay))
        return shown

    def _fill_contracts(self) -> None:
        t = self.query_one("#contracts", DataTable)
        cur = t.cursor_row
        t.clear()
        s = self.game.state
        for c in self._contracts():
            locked = s.rating_level < c.min_rating
            status = {"accepted": Text("ACTIVE", "bold green"),
                      "open": Text("locked", "red") if locked else Text("open", "dim")}[c.status]
            left = clock.fmt_duration(c.deadline - self.game.now)
            t.add_row(c.id, c.label, self.game.world.nodes[c.target].hostname,
                      f"¢{c.pay:,}", "★" * c.difficulty, left, status, key=c.id)
        if t.row_count:
            t.move_cursor(row=min(max(cur, 0), t.row_count - 1))
        self._show_contract()

    def _selected_contract(self):
        t = self.query_one("#contracts", DataTable)
        rows = self._contracts()
        if not rows or t.cursor_row < 0 or t.cursor_row >= len(rows):
            return None
        return rows[t.cursor_row]

    def _show_contract(self) -> None:
        c = self._selected_contract()
        detail = self.query_one("#contract-detail", Static)
        answer = self.query_one("#answer", Input)
        if c is None:
            detail.update("No contracts right now. New ones arrive over time.")
            answer.display = False
            return
        from ..game.state import RATING_TITLES
        need = RATING_TITLES[c.min_rating][1]
        txt = Text()
        txt.append(f"{c.id}  {c.title}\n", "bold")
        txt.append(f"{c.corp_name}   pay ¢{c.pay:,}   deadline {clock.fmt_short(c.deadline)}\n", "cyan")
        txt.append(f"Requires rating: {need}\n\n", "dim")
        txt.append(c.brief)
        detail.update(txt)
        answer.display = c.kind == "find" and c.status == "accepted"
        self.query_one("#accept", Button).display = c.status == "open"
        self.query_one("#abandon", Button).display = c.status == "accepted" and c.kind != "training"
        self.query_one("#submit", Button).display = c.kind == "find" and c.status == "accepted"
        self.refresh_bindings()

    def _store_items(self):
        s = self.game.state
        return [i for i in store.CATALOG if not store.owned(s, i)]

    def _fill_store(self) -> None:
        t = self.query_one("#store", DataTable)
        cur = t.cursor_row
        t.clear()
        s = self.game.state
        nxt = store.available(s)
        for i in self._store_items():
            if i in nxt:
                tag = Text("available", "green") if s.money >= i.price else Text("too expensive", "yellow")
            else:
                tag = Text("needs previous", "dim")
            t.add_row(i.name, i.kind, f"¢{i.price:,}", tag)
        if t.row_count:
            t.move_cursor(row=min(max(cur, 0), t.row_count - 1))
        self._show_item()

    def _selected_item(self):
        t = self.query_one("#store", DataTable)
        items = self._store_items()
        if not items or t.cursor_row < 0 or t.cursor_row >= len(items):
            return None
        return items[t.cursor_row]

    def _show_item(self) -> None:
        i = self._selected_item()
        s = self.game.state
        owned_sw = ", ".join(f"{k} v{v}" for k, v in s.sw.items() if v)
        owned_hw = ", ".join(f"{k} mk{v}" for k, v in s.hw.items())
        txt = Text()
        if i:
            txt.append(f"{i.name}\n", "bold")
            txt.append(f"¢{i.price:,}\n\n", "green")
            txt.append(i.desc + "\n\n")
        else:
            txt.append("You own everything. Impressive.\n\n")
        txt.append(f"Credits: ¢{s.money:,}\n", "cyan")
        txt.append(f"Software: {owned_sw}\nHardware: {owned_hw}\n", "dim")
        self.query_one("#store-detail", Static).update(txt)
        self.refresh_bindings()

    def _fill_news(self) -> None:
        txt = Text()
        for n in reversed(self.game.state.news[-30:]):
            txt.append(f"{clock.fmt_short(n.time)}  ", "dim")
            txt.append(n.headline + "\n", "bold")
            if n.body:
                txt.append(f"    {n.body}\n")
        self.query_one("#news", Static).update(txt or "No news.")

    def _fill_account(self) -> None:
        s = self.game.state
        from ..game.state import RATING_TITLES
        nxt = next(((p, t) for p, t in RATING_TITLES if p > s.rating), None)
        done = sum(1 for c in s.contracts if c.status == "done")
        txt = Text()
        txt.append(f"Runner:      {s.handle}\n", "bold")
        txt.append(f"Credits:     ¢{s.money:,}\n")
        txt.append(f"Rating:      {s.rating_title} ({s.rating} points)\n")
        if nxt:
            txt.append(f"Next title:  {nxt[1]} at {nxt[0]} points\n", "dim")
        txt.append(f"Strikes:     {s.strikes}/3\n", "red" if s.strikes else "")
        txt.append(f"Completed:   {done} contracts\n")
        self.query_one("#account", Static).update(txt)

    # ---------------------------------------------------------------- events
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "contracts":
            self._show_contract()
        else:
            self._show_item()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is None:
            return
        title = list(DOCS)[event.list_view.index]
        self.query_one("#docs-md", Markdown).update(DOCS[title])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "accept":
            self.action_accept()
        elif bid == "abandon":
            self.action_abandon()
        elif bid == "submit":
            self._submit()
        elif bid == "buy":
            self.action_buy()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "answer":
            self._submit()

    def _submit(self) -> None:
        c = self._selected_contract()
        inp = self.query_one("#answer", Input)
        if c:
            self.notify(self.game.submit_answer(c, inp.value))
            inp.value = ""
            self.refresh_all()
            self.query_one("#contracts").focus()

    def action_accept(self) -> None:
        if self.active_tab != "tab-contracts":
            return
        c = self._selected_contract()
        if c:
            msg = self.game.accept(c)
            self.notify(msg, severity="information" if "accepted" in msg else "warning")
            self.refresh_all()

    def action_abandon(self) -> None:
        c = self._selected_contract()
        if c and self.active_tab == "tab-contracts":
            self.notify(self.game.abandon(c))
            self.refresh_all()

    def action_answer(self) -> None:
        inp = self.query_one("#answer", Input)
        if inp.display:
            inp.focus()

    def action_buy(self) -> None:
        if self.active_tab != "tab-store":
            return
        i = self._selected_item()
        if i:
            msg = self.game.buy(i)
            self.notify(msg, severity="information" if msg.startswith("Purchased") else "warning")
            self.refresh_all()

    def action_close(self) -> None:
        if isinstance(self.focused, Input):
            self._focus_tab()
            return
        self.dismiss(None)


# ====================================================================== mail
class MailScreen(GameScreen):
    CSS = """
    MailScreen { background: $background; }
    #mail-list { width: 2fr; height: 1fr; }
    #mail-body { width: 3fr; padding: 0 2; border-left: tall $primary; }
    """

    BINDINGS = GameScreen.BINDINGS + [Binding("r", "reply", "Reply"), Binding("c", "compose", "Compose"),
                                      Binding("d", "delete", "Delete")]

    def action_reply(self) -> None:
        mails = self._mails()
        if not mails:
            return
        m = mails[min(self.query_one(DataTable).cursor_row, len(mails) - 1)]
        addr = m.sender.split("<")[-1].rstrip(">") if "<" in m.sender else m.sender
        subj = m.subject if m.subject.lower().startswith("re:") else f"Re: {m.subject}"
        self.app.push_screen(ComposeScreen(self.game, addr, subj), lambda _: self._fill())

    def action_compose(self) -> None:
        self.app.push_screen(ComposeScreen(self.game), lambda _: self._fill())

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield DataTable(id="mail-list", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="mail-body"):
                yield Static(id="mail-text")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one(DataTable)
        t.add_columns(" ", "From", "Subject", "Date")
        self._fill()
        t.focus()

    def _mails(self):
        return list(reversed(self.game.state.mail))

    def _fill(self) -> None:
        t = self.query_one(DataTable)
        cur = t.cursor_row
        t.clear()
        for m in self._mails():
            sender = m.sender.split("<")[0].strip()
            t.add_row("●" if not m.read else " ", sender[:22], m.subject[:40],
                      clock.fmt_short(m.time))
        if t.row_count:
            t.move_cursor(row=min(max(cur, 0), t.row_count - 1))
        self._show_mail()

    def _show_mail(self) -> None:
        mails = self._mails()
        t = self.query_one(DataTable)
        if not mails:
            self.query_one("#mail-text", Static).update("Inbox is empty.")
            return
        m = mails[min(t.cursor_row, len(mails) - 1)]
        was_unread = not m.read
        m.read = True
        txt = Text()
        txt.append(f"From:    {m.sender}\n", "cyan")
        txt.append(f"Subject: {m.subject}\n", "bold")
        txt.append(f"Date:    {clock.fmt_date(m.time)}\n\n", "dim")
        txt.append(m.body)
        self.query_one("#mail-text", Static).update(txt)
        if was_unread:
            t.update_cell_at((t.cursor_row, 0), " ")

    def on_data_table_row_highlighted(self, event) -> None:
        self._show_mail()

    def action_delete(self) -> None:
        mails = self._mails()
        t = self.query_one(DataTable)
        if mails:
            self.game.state.mail.remove(mails[t.cursor_row])
            self._fill()


class ComposeScreen(ModalScreen):
    """Write a mail. Tab moves between fields, Ctrl+S sends, Esc cancels."""

    CSS = """
    ComposeScreen { align: center middle; background: $background 60%; }
    #compose-box { width: 84; height: 30; border: heavy $accent; padding: 0 1; background: $surface; }
    #compose-box Label { margin-top: 1; color: $text-muted; }
    #compose-box Input { height: 3; }
    #c-body { height: 1fr; }
    #c-msg { color: $error; height: auto; }
    #c-keys { color: $text-muted; height: 1; }
    """
    BINDINGS = [Binding("ctrl+s", "send", "Send", priority=True), Binding("escape", "cancel", "Cancel")]

    def __init__(self, game: Game, to: str = "", subject: str = ""):
        super().__init__()
        self.game = game
        self.to = to
        self.subject = subject

    def compose(self) -> ComposeResult:
        with Vertical(id="compose-box"):
            yield Label("To:")
            yield Input(self.to, id="c-to", placeholder="name@domain")
            yield Label("Subject:")
            yield Input(self.subject, id="c-subject")
            yield Label("Attach (files on your gateway, comma separated, e.g. ~/downloads/x.dat):")
            yield Input(id="c-attach")
            yield TextArea(id="c-body")
            yield Static("", id="c-msg")
            yield Static("Tab next field   Ctrl+S send   Esc cancel", id="c-keys")

    def on_mount(self) -> None:
        self.query_one("#c-subject" if self.to else "#c-to", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.focus_next()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_send(self) -> None:
        msg = self.query_one("#c-msg", Static)
        to = [a.strip() for a in self.query_one("#c-to", Input).value.replace(";", ",").split(",") if a.strip()]
        if not to or not all("@" in a for a in to):
            msg.update("Enter a valid address (name@domain).")
            return
        from ..game.vfs import FSError, allowed, normpath
        s = self.game.state
        fs = self.game.world.nodes[GATEWAY].fs
        ident = Identity(s.handle, {s.handle, "sudo", "adm"})
        files = []
        for raw in self.query_one("#c-attach", Input).value.split(","):
            raw = raw.strip()
            if not raw:
                continue
            path = s.home + raw[1:] if raw.startswith("~") else raw
            try:
                node = fs.resolve(normpath(path, s.home), "/", ident, want="file")
            except FSError as e:
                msg.update(f"Attachment: {e}")
                return
            if not allowed(node, ident, "r"):
                msg.update(f"Attachment: {raw}: Permission denied")
                return
            files.append(node)
        self.game.send_mail(to, self.query_one("#c-subject", Input).value,
                            self.query_one("#c-body", TextArea).text, files)
        self.app.notify(f"Mail sent to {', '.join(to)}")
        self.dismiss(True)


# ====================================================================== map
class MapScreen(GameScreen):
    CSS = """
    MapScreen { background: $background; }
    #map-art { height: 22; padding: 0 1; border: round $primary; width: 76; }
    #map-side { width: 1fr; padding: 0 1; }
    #map-table { height: 1fr; }
    #map-help { height: auto; color: $text-muted; }
    """

    BINDINGS = GameScreen.BINDINGS + [
        Binding("enter", "toggle", "Add/remove relay"),
        Binding("c", "clear", "Clear route"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(id="map-art")
            with Vertical(id="map-side"):
                yield Static(id="map-help")
                yield DataTable(id="map-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one(DataTable)
        t.add_columns("Node", "IP", "Type", "Sec")
        self._fill()
        t.focus()

    def _known_nodes(self):
        s = self.game.state
        nodes = [self.game.world.nodes[h] for h in s.known if h in self.game.world.nodes]
        order = {"gateway": 0, "agency": 1, "drop": 2, "relay": 3, "sandbox": 4, "front": 5, "core": 6}
        return sorted(nodes, key=lambda n: (order.get(n.kind, 9), n.hostname))

    def _fill(self) -> None:
        t = self.query_one(DataTable)
        cur = t.cursor_row
        t.clear()
        route = self.game.state.route
        for n in self._known_nodes():
            name = Text(n.hostname)
            if n.hostname in route:
                name = Text(f"{n.hostname}  [hop {route.index(n.hostname) + 1}]", "bold yellow")
            t.add_row(name, n.ip, n.label, "★" * n.sec if n.sec else "")
        if t.row_count:
            t.move_cursor(row=min(max(cur, 0), t.row_count - 1))
        self._draw()

    def _draw(self) -> None:
        grid = [list(row) for row in WORLD_MAP]
        styles: dict[tuple[int, int], str] = {}
        s = self.game.state
        world = self.game.world
        nodes = self._known_nodes()
        path = [GATEWAY] + list(s.route)
        pts = [world.nodes[h].loc for h in path]
        # draw the route as a dotted line
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for i in range(1, steps):
                x = round(x0 + (x1 - x0) * i / steps)
                y = round(y0 + (y1 - y0) * i / steps)
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    grid[y][x] = "·"
                    styles[(x, y)] = "yellow"
        sel = None
        t = self.query_one(DataTable)
        if nodes and 0 <= t.cursor_row < len(nodes):
            sel = nodes[t.cursor_row]
        for n in nodes:
            x, y = n.loc
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                continue
            ch, st = {"gateway": ("@", "bold green"), "relay": ("o", "cyan"),
                      "agency": ("B", "bold magenta"), "drop": ("B", "bold magenta"),
                      "sandbox": ("T", "white"), "front": ("■", "red"),
                      "core": ("■", "bold red")}.get(n.kind, ("*", "white"))
            if n.hostname in s.route:
                st = "bold yellow"
            grid[y][x] = ch
            styles[(x, y)] = st
        if sel:
            x, y = sel.loc
            if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                styles[(x, y)] = "reverse bold"
        txt = Text()
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                st = styles.get((x, y))
                txt.append(ch, st or ("rgb(60,90,80)" if ch in ".:'" else None))
            txt.append("\n")
        txt.append(" @ you  o relay  B agency  T training  ■ corp   ··· route", "dim")
        self.query_one("#map-art", Static).update(txt)
        hops = len(s.route)
        help_txt = Text()
        help_txt.append(f"Route: {hops} hop{'s' if hops != 1 else ''}\n", "bold")
        help_txt.append("gateway → " + " → ".join(world.nodes[h].short for h in s.route) + " → target\n"
                        if s.route else "direct (no relays)\n", "yellow")
        help_txt.append("Enter: add/remove the selected relay   c: clear route\n", "dim")
        if sel:
            help_txt.append(f"\n{sel.hostname}  {sel.title}\n", "bold")
        self.query_one("#map-help", Static).update(help_txt)

    def on_data_table_row_highlighted(self, event) -> None:
        self._draw()

    def on_data_table_row_selected(self, event) -> None:
        self.action_toggle()

    def action_toggle(self) -> None:
        nodes = self._known_nodes()
        t = self.query_one(DataTable)
        if not nodes:
            return
        n = nodes[t.cursor_row]
        route = self.game.state.route
        if not n.public:
            self.notify("Only public relays can be part of your route.", severity="warning")
            return
        if n.hostname in route:
            route.remove(n.hostname)
        elif len(route) < 8:
            route.append(n.hostname)
            self.game.flag("route")
        self._fill()

    def action_clear(self) -> None:
        self.game.state.route.clear()
        self._fill()

