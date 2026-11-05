import os
from pathlib import Path

import pytest

from nullroute.ui.app import NullrouteApp, TerminalScreen

SHOTS = Path(__file__).resolve().parents[1] / "screenshots"


async def type_line(pilot, text):
    for ch in text:
        await pilot.press(ch if ch != " " else "space")
    await pilot.press("enter")
    await pilot.pause(0.3)


def log_text(app):
    term = app.term
    return "\n".join(line.text for line in term.log_w.lines)


@pytest.mark.asyncio
async def test_full_ui_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    SHOTS.mkdir(exist_ok=True)
    app = NullrouteApp()
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        app.save_screenshot(str(SHOTS / "01_title.svg"))
        await pilot.press("enter")                  # menu: "New game"
        await pilot.pause(0.2)
        await type_line(pilot, "neo")
        await type_line(pilot, "secret")
        assert isinstance(app.screen, TerminalScreen)
        # sudo asks for the password through the real prompt
        await type_line(pilot, "sudo apt install cowsay")
        await type_line(pilot, "secret")
        await pilot.pause(1.5)
        assert "Setting up cowsay" in log_text(app)
        assert "secret" not in log_text(app)          # passwords are never echoed
        await type_line(pilot, "cowsay hello")
        await type_line(pilot, "top")
        await pilot.pause(0.5)
        app.save_screenshot(str(SHOTS / "11_top.svg"))
        await pilot.press("q")
        await pilot.pause(0.3)
        assert isinstance(app.screen, TerminalScreen)
        await type_line(pilot, "ls -la")
        assert "README.txt" in log_text(app)
        await type_line(pilot, "tutorial")
        app.save_screenshot(str(SHOTS / "02_terminal.svg"))
        # mail view
        await type_line(pilot, "mail")
        await pilot.pause(0.3)
        app.save_screenshot(str(SHOTS / "03_mail.svg"))
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert isinstance(app.screen, TerminalScreen)
        # bbs
        await type_line(pilot, "ssh blackrelay.net")
        await pilot.pause(0.3)
        app.save_screenshot(str(SHOTS / "04_bbs.svg"))
        await pilot.press("escape")
        await pilot.pause(0.3)
        await type_line(pilot, "probe sandbox")
        await pilot.pause(1.6)
        await type_line(pilot, "route add tallinn")
        await type_line(pilot, "route add osaka")
        await type_line(pilot, "map")
        await pilot.pause(0.3)
        app.save_screenshot(str(SHOTS / "05_map.svg"))
        await pilot.press("escape")
        await pilot.pause(0.2)
        await type_line(pilot, "breach sandbox")
        await pilot.pause(9)
        await type_line(pilot, "ssh sandbox")
        await pilot.pause(1.5)
        assert app.term.shell.frame.node.startswith("sandbox")
        await type_line(pilot, "find /data -name '*.dat'")
        app.save_screenshot(str(SHOTS / "06_connected.svg"))
        text = log_text(app)
        assert "training_payload.dat" in text
        # tab completion
        for ch in "cd /da":
            await pilot.press(ch if ch != " " else "space")
        await pilot.press("tab")
        assert app.term.cmd.value == "cd /data/"


@pytest.mark.asyncio
async def test_split_terminals_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    from nullroute.ui.title import TitleScreen
    app = NullrouteApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(0.2)
        await type_line(pilot, "neo")
        await type_line(pilot, "secret")
        gs = app.screen
        # the prompt sits right under the output, not at the bottom of the screen
        pane = app.term
        assert pane.cmd.region.y < 20
        await pilot.press("ctrl+n")
        await pilot.pause(0.3)
        assert len(gs.panes) == 2 and app.term.index == 2
        await type_line(pilot, "split")
        await type_line(pilot, "split")
        await pilot.pause(0.3)
        assert len(gs.panes) == 4
        app.save_screenshot(str(SHOTS / "12_split.svg"))
        await pilot.press("alt+1")
        await pilot.pause(0.1)
        assert app.term.index == 1
        await pilot.press("f2")
        await pilot.pause(0.1)
        assert app.term.index == 2
        # each terminal is its own shell
        await type_line(pilot, "cd /etc")
        assert gs.panes[1].shell.frame.cwd == "/etc"
        assert gs.panes[0].shell.frame.cwd != "/etc"
        # close three terminals
        for _ in range(3):
            await type_line(pilot, "exit")
            await pilot.pause(0.2)
        assert len(gs.panes) == 1
        # closing the last one asks first
        await pilot.press("ctrl+d")
        await pilot.pause(0.3)
        await pilot.press("n")
        await pilot.pause(0.2)
        assert len(gs.panes) == 1 and app.screen is gs
        await type_line(pilot, "logout")
        await pilot.pause(0.3)
        await pilot.press("y")
        await pilot.pause(0.5)
        assert isinstance(app.screen, TitleScreen)
        # and the save shows up in the keyboard menu
        await pilot.press("enter")                  # "Continue as neo"
        await pilot.pause(0.5)
        assert isinstance(app.screen, TerminalScreen)


@pytest.mark.asyncio
async def test_password_reset_from_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    from nullroute.game import state as S
    S.save(S.new_state("zed", seed=3, password="old"))
    app = NullrouteApp()
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        # menu: Continue as zed, New game, Reset a password, Quit
        await pilot.press("down", "down", "enter")
        await pilot.pause(0.2)
        await pilot.press("enter")                  # pick zed
        await pilot.pause(0.2)
        await type_line(pilot, "fresh")
        await type_line(pilot, "fresh")
        assert S.load("zed").password == "fresh"


@pytest.mark.asyncio
async def test_tutorial_follow_pane(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    from textual.widgets import Static
    app = NullrouteApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(0.2)
        await type_line(pilot, "neo")
        await type_line(pilot, "secret")
        gs = app.screen
        status = str(gs.query_one("#status", Static).render())
        assert "1/13: Split the screen" in status
        await pilot.press("ctrl+n")
        await pilot.pause(0.3)
        guide = app.term
        await type_line(pilot, "tutorial -f")
        await pilot.pause(0.5)
        assert guide.tutorial_follow
        assert "TUTORIAL 2/13: Read your mail" in log_text(app)
        assert "2/13: Read your mail" in str(gs.query_one("#status", Static).render())
        await pilot.press("alt+left")                  # back to the work terminal
        await pilot.pause(0.2)
        work = app.term
        assert work is not guide
        await type_line(pilot, "mail")
        await pilot.pause(0.3)
        await pilot.press("escape")
        await pilot.pause(0.6)
        work_text = log_text(app)
        assert "Objective done: Read your mail." in work_text
        assert "Contracts tab" not in work_text        # details only in the guide pane
        guide_text = "\n".join(line.text for line in guide.log_w.lines)
        assert "TUTORIAL 3/13: Visit the agency" in guide_text
        assert "TUTORIAL 2/13" not in guide_text       # redrawn, not appended
        SHOTS.mkdir(exist_ok=True)
        app.save_screenshot(str(SHOTS / "13_tutorial_follow.svg"))


@pytest.mark.asyncio
async def test_delete_runner_from_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    from nullroute.game import state as S
    from nullroute.ui.terminal import ConfirmScreen
    from nullroute.ui.title import TitleScreen
    S.save(S.new_state("amy", seed=1, password="pw"))
    S.save(S.new_state("bob", seed=2, password="pw"))
    app = NullrouteApp()
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert "Del/d delete" in str(app.screen.query_one("#keys").render())
        # menu: Continue as amy, Continue as bob, ... - Del on amy, then cancel
        await pilot.press("delete")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConfirmScreen)
        assert "Delete runner amy? This cannot be undone." in app.screen.question
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert isinstance(app.screen, TitleScreen)
        assert S.list_saves() == ["amy", "bob"]
        # "n" also cancels
        await pilot.press("d")
        await pilot.pause(0.2)
        await pilot.press("n")
        await pilot.pause(0.2)
        assert S.list_saves() == ["amy", "bob"]
        # confirm with y
        await pilot.press("d")
        await pilot.pause(0.2)
        await pilot.press("y")
        await pilot.pause(0.2)
        assert S.list_saves() == ["bob"]
        ids = [app.screen.query_one("#menu").get_option_at_index(i).id
               for i in range(app.screen.query_one("#menu").option_count)]
        assert ids == ["load:bob", "new", "reset", "delete", "quit"]
        # delete the last runner through the "Delete a runner" menu entry
        await pilot.press("down", "down", "down", "enter")   # -> Delete a runner
        await pilot.pause(0.2)
        await pilot.press("enter")                          # pick bob
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause(0.2)
        assert S.list_saves() == []
        menu = app.screen.query_one("#menu")
        ids = [menu.get_option_at_index(i).id for i in range(menu.option_count)]
        assert ids == ["new", "quit"]
        # Del on a non-runner entry does nothing
        await pilot.press("delete")
        await pilot.pause(0.2)
        assert isinstance(app.screen, TitleScreen)
