"""Start menu (keyboard driven), password reset and game over screens."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from ..game import state as S
from ..game.engine import Game

LOGO = r"""
 _   _ _   _ _     _     ____   ___  _   _ _____ _____
| \ | | | | | |   | |   |  _ \ / _ \| | | |_   _| ____|
|  \| | | | | |   | |   | |_) | | | | | | | | | |  _|
| |\  | |_| | |___| |___|  _ <| |_| | |_| | | | | |___
|_| \_|\___/|_____|_____|_| \_\\___/ \___/  |_| |_____|
"""


class TitleScreen(Screen):
    CSS = """
    TitleScreen { align: center middle; background: $background; }
    #title-box { width: 72; height: auto; border: heavy $primary; padding: 1 2; }
    #logo { color: $accent; text-style: bold; width: 100%; }
    #tagline { color: $text-muted; margin-bottom: 1; }
    #menu { height: auto; max-height: 12; border: none; background: $background; }
    #menu:focus { border: none; }
    .form { height: auto; display: none; }
    .form Input { margin-bottom: 1; }
    .form Label { margin-top: 0; }
    #keys { color: $text-muted; margin-top: 1; }
    #title-msg { color: $error; height: auto; }
    """
    BINDINGS = [Binding("escape", "back", show=False)]

    def __init__(self):
        super().__init__()
        self.mode = "menu"
        self.reset_handle = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="title-box"):
            yield Static(LOGO, id="logo")
            yield Static("a terminal hacking game  -  fictional nodes, real shell", id="tagline")
            yield OptionList(id="menu")
            with Vertical(id="new-form", classes="form"):
                yield Label("New runner - choose a handle:")
                yield Input(placeholder="handle (letters, digits, - _)", id="handle", max_length=16)
                yield Label("Password for your gateway (sudo will ask for it):")
                yield Input(placeholder="password", id="password", password=True, max_length=32)
            with Vertical(id="reset-form", classes="form"):
                yield Label("", id="reset-label")
                yield Input(placeholder="new password", id="reset-pw", password=True, max_length=32)
                yield Input(placeholder="type it again", id="reset-pw2", password=True, max_length=32)
            yield Static("", id="title-msg")
            yield Static("", id="keys")

    def on_mount(self) -> None:
        self.show_menu()

    # ------------------------------------------------------------ menu
    def show_menu(self, highlight: str | None = None) -> None:
        self.mode = "menu"
        menu = self.query_one("#menu", OptionList)
        menu.clear_options()
        saves = S.list_saves()
        for name in saves:
            menu.add_option(Option(f"▶  Continue as {name}", id=f"load:{name}"))
        menu.add_option(Option("✚  New game", id="new"))
        if saves:
            menu.add_option(Option("⚿  Reset a password", id="reset"))
        menu.add_option(Option("✖  Quit", id="quit"))
        menu.display = True
        for f in self.query(".form"):
            f.display = False
        self.query_one("#title-msg", Static).update("")
        self.query_one("#keys", Static).update("↑/↓ choose   Enter select   Esc back")
        menu.highlighted = 0
        if highlight:
            for i in range(menu.option_count):
                if menu.get_option_at_index(i).id == highlight:
                    menu.highlighted = i
        menu.focus()

    def show_reset_choice(self) -> None:
        self.mode = "reset-pick"
        menu = self.query_one("#menu", OptionList)
        menu.clear_options()
        for name in S.list_saves():
            menu.add_option(Option(f"⚿  {name}", id=f"pick:{name}"))
        menu.highlighted = 0
        menu.focus()
        self.query_one("#keys", Static).update("Whose password?   ↑/↓ choose   Enter select   Esc back")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        oid = event.option.id or ""
        msg = self.query_one("#title-msg", Static)
        if oid.startswith("load:"):
            try:
                st = S.load(oid[5:])
            except Exception as e:  # noqa: BLE001
                msg.update(f"Could not load: {e}")
                return
            self.app.start_game(Game(st), new=False)
        elif oid == "new":
            self.mode = "new"
            self.query_one("#menu").display = False
            self.query_one("#new-form").display = True
            self.query_one("#keys", Static).update("Enter next field / start   Esc back")
            self.query_one("#handle", Input).focus()
        elif oid == "reset":
            self.show_reset_choice()
        elif oid.startswith("pick:"):
            self.mode = "reset"
            self.reset_handle = oid[5:]
            self.query_one("#menu").display = False
            self.query_one("#reset-form").display = True
            self.query_one("#reset-label", Label).update(
                f"New sudo password for {self.reset_handle} (like booting into recovery mode):")
            self.query_one("#reset-pw", Input).value = ""
            self.query_one("#reset-pw2", Input).value = ""
            self.query_one("#keys", Static).update("Enter next field / save   Esc back")
            self.query_one("#reset-pw", Input).focus()
        elif oid == "quit":
            self.app.exit()

    def action_back(self) -> None:
        if self.mode != "menu":
            self.show_menu()

    # ------------------------------------------------------------ forms
    def on_input_submitted(self, event: Input.Submitted) -> None:
        iid = event.input.id
        if iid == "handle":
            self.query_one("#password", Input).focus()
        elif iid == "password":
            self._new()
        elif iid == "reset-pw":
            self.query_one("#reset-pw2", Input).focus()
        elif iid == "reset-pw2":
            self._reset()

    def _new(self) -> None:
        handle = self.query_one("#handle", Input).value.strip()
        password = self.query_one("#password", Input).value
        msg = self.query_one("#title-msg", Static)
        if not handle or not all(c.isalnum() or c in "-_" for c in handle):
            msg.update("Use letters, digits, - or _ only.")
            self.query_one("#handle", Input).focus()
            return
        if handle.lower() in S.list_saves():
            msg.update(f"A save for '{handle}' exists - continue it from the menu, or pick another handle.")
            self.query_one("#handle", Input).focus()
            return
        if not password:
            msg.update("Pick a password too - you'll type it whenever you use sudo.")
            self.query_one("#password", Input).focus()
            return
        st = S.new_state(handle.lower(), password=password)
        game = Game(st)
        game.start_new()
        self.app.start_game(game, new=True)

    def _reset(self) -> None:
        pw = self.query_one("#reset-pw", Input).value
        pw2 = self.query_one("#reset-pw2", Input).value
        msg = self.query_one("#title-msg", Static)
        if not pw:
            msg.update("The password can't be empty.")
            self.query_one("#reset-pw", Input).focus()
            return
        if pw != pw2:
            msg.update("Sorry, passwords do not match.")
            self.query_one("#reset-pw", Input).value = ""
            self.query_one("#reset-pw2", Input).value = ""
            self.query_one("#reset-pw", Input).focus()
            return
        try:
            st = S.load(self.reset_handle)
            st.password = pw
            S.save(st)
        except Exception as e:  # noqa: BLE001
            msg.update(f"Could not update the save: {e}")
            return
        self.show_menu(highlight=f"load:{self.reset_handle}")
        self.query_one("#title-msg", Static).update(
            f"passwd: password updated successfully for {self.reset_handle}")


class GameOverScreen(Screen):
    CSS = """
    GameOverScreen { align: center middle; background: $background; }
    #go-box { width: 72; height: auto; border: heavy $error; padding: 1 2; }
    #go-title { color: $error; text-style: bold; margin-bottom: 1; }
    #go-keys { color: $text-muted; margin-top: 1; }
    """
    BINDINGS = [Binding("enter,escape", "to_menu", show=False)]

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="go-box"):
            yield Static("BURNED", id="go-title")
            yield Static(self.text)
            yield Static("Enter: back to the start menu", id="go-keys")

    def action_to_menu(self) -> None:
        self.app.back_to_title()
