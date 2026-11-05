"""The Textual application: start menu, game screen, logout and quit."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from ..game import state as S
from ..game.engine import Game
from .terminal import GameScreen, TerminalPane
from .title import GameOverScreen, TitleScreen

# backwards compatible name used by tests and older code
TerminalScreen = GameScreen

__all__ = ["NullrouteApp", "TerminalScreen", "GameScreen", "TitleScreen", "GameOverScreen", "main"]


class NullrouteApp(App):
    TITLE = "NULLROUTE"
    CSS = "Screen { background: #0b0f0c; }"
    BINDINGS = [Binding("ctrl+q", "quit_game", "Quit", show=False, priority=True)]

    def __init__(self):
        super().__init__()
        self.game: Game | None = None
        self.game_screen: GameScreen | None = None

    @property
    def term(self) -> TerminalPane | None:
        """The active terminal pane."""
        return self.game_screen.active if self.game_screen else None

    def on_mount(self) -> None:
        self.theme = "textual-dark"
        self.push_screen(TitleScreen())

    def start_game(self, game: Game, new: bool) -> None:
        self.game = game
        self.game_screen = GameScreen(game, new)
        self.switch_screen(self.game_screen)
        if new:
            self._save()

    def _save(self) -> None:
        g = self.game
        if g and not g.state.game_over:
            try:
                S.save(g.state)
            except OSError:
                pass

    def _end_session(self) -> None:
        if self.game_screen:
            self.game_screen.stop()
        self._save()
        self.game = None
        self.game_screen = None

    def logout_to_title(self) -> None:
        """Last terminal closed: save and go back to the start menu."""
        self._end_session()
        self.switch_screen(TitleScreen())

    def back_to_title(self) -> None:
        """From the game over screen."""
        self.game = None
        self.game_screen = None
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self.switch_screen(TitleScreen())

    def action_quit_game(self) -> None:
        self.quit_game()

    def quit_game(self) -> None:
        self._end_session()
        self.exit()


def main() -> None:
    NullrouteApp().run()
