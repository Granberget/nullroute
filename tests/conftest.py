import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nullroute.game.engine import Game  # noqa: E402
from nullroute.game.state import new_state  # noqa: E402
from nullroute.shell.core import Shell  # noqa: E402


class FakeUI:
    def __init__(self):
        self.lines: list[str] = []
        self.views: list[str] = []
        self.quit_called = False
        self.answers: list[str] = []      # queued replies for prompts (passwords...)
        self.prompts: list[str] = []

    def write(self, text, style=None):
        self.lines.extend(str(text).split("\n"))

    def progress(self, text):
        pass

    async def prompt(self, label, secret=False):
        self.prompts.append(label)
        return self.answers.pop(0) if self.answers else ""

    async def open_view(self, name, **kw):
        self.views.append(name)
        return None

    def clear(self):
        self.lines.clear()

    def quit(self):
        self.quit_called = True

    def logout(self):
        self.logged_out = True

    def new_terminal(self):
        self.views.append("new_terminal")

    @property
    def text(self):
        return "\n".join(self.lines)


class Harness:
    def __init__(self, seed=42):
        self.state = new_state("tester", seed=seed, password="hunter2")
        self.game = Game(self.state)
        self.notes = []
        self.game.listeners.append(lambda t, s: self.notes.append(t))
        self.game.start_new()
        self.ui = FakeUI()
        self.shell = Shell(self.game, self.ui)
        self.game.on_caught = lambda how: self.shell.disconnect_all()

    def run(self, line: str) -> str:
        self.ui.lines.clear()
        asyncio.run(self._fast(line))
        return self.ui.text

    def session(self, *steps):
        """Run several lines in ONE event loop (so background jobs survive).
        A step is a command line, or a float meaning 'wait this many seconds'."""
        async def go():
            for step in steps:
                if isinstance(step, (int, float)):
                    await asyncio.sleep(step)
                else:
                    await self.shell.run_line(step)
            await asyncio.sleep(0.05)
        self.ui.lines.clear()
        asyncio.run(go())
        return self.ui.text

    async def _fast(self, line):
        # make waits instant
        orig = asyncio.sleep

        async def fast_sleep(t, *a, **k):
            await orig(0)
        asyncio.sleep = fast_sleep
        try:
            await self.shell.run_line(line)
        finally:
            asyncio.sleep = orig


@pytest.fixture
def h():
    return Harness()
