from pathlib import Path

import pytest

from nullroute.ui.app import NullrouteApp, TerminalScreen
from nullroute.ui.nano import NanoScreen
from nullroute.ui.views import BBSScreen

SHOTS = Path(__file__).resolve().parents[1] / "screenshots"


async def typ(pilot, text):
    for ch in text:
        await pilot.press({" ": "space", "'": "apostrophe", ">": "greater_than_sign",
                           "/": "slash", ".": "full_stop"}.get(ch, ch))


async def line(pilot, text):
    await typ(pilot, text)
    await pilot.press("enter")
    await pilot.pause(0.3)


def gw_file(app, path):
    node = app.game.world.nodes["gateway"].fs.get(f"/home/neo/{path}")
    return None if node is None else node.content


async def start(pilot, app):
    await pilot.pause()
    await pilot.press("enter")                      # menu: "New game"
    await pilot.pause(0.2)
    await line(pilot, "neo")
    await line(pilot, "secret")
    assert isinstance(app.screen, TerminalScreen)


@pytest.mark.asyncio
async def test_nano_write_out_exit_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    SHOTS.mkdir(exist_ok=True)
    app = NullrouteApp()
    async with app.run_test(size=(110, 32)) as pilot:
        await start(pilot, app)
        await line(pilot, "echo hello world > notes.txt")
        await line(pilot, "nano notes.txt")
        await pilot.pause(0.3)
        assert isinstance(app.screen, NanoScreen)
        nano = app.screen
        # search for "world"
        await pilot.press("ctrl+w")
        await typ(pilot, "world")
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert nano.area.selected_text == "world"
        # cut the line and paste it twice
        await pilot.press("home")
        await pilot.press("ctrl+k")
        assert nano.area.text == ""
        await pilot.press("ctrl+u")
        await pilot.press("ctrl+u")
        assert nano.area.text == "hello world\nhello world\n"
        app.save_screenshot(str(SHOTS / "07_nano.svg"))
        # exit -> asks to save -> Y -> file name prompt -> Enter
        await pilot.press("ctrl+x")
        await pilot.pause(0.1)
        assert nano.mode == "save_changes"
        app.save_screenshot(str(SHOTS / "08_nano_save_prompt.svg"))
        await pilot.press("y")
        await pilot.pause(0.1)
        assert nano.mode == "write"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, TerminalScreen)
        assert gw_file(app, "notes.txt") == "hello world\nhello world\n"


@pytest.mark.asyncio
async def test_nano_new_file_discard_and_replace(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    app = NullrouteApp()
    async with app.run_test(size=(110, 32)) as pilot:
        await start(pilot, app)
        await line(pilot, "nano todo.txt")
        nano = app.screen
        assert isinstance(nano, NanoScreen)
        await typ(pilot, "cat cat dog cat")
        # write out under the default name, stays in the editor
        await pilot.press("ctrl+o")
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert gw_file(app, "todo.txt") == "cat cat dog cat"
        assert isinstance(app.screen, NanoScreen)
        # replace: first instance yes, then all
        await pilot.press("ctrl+backslash")
        await typ(pilot, "cat")
        await pilot.press("enter")
        await typ(pilot, "cow")
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert nano.mode == "replace_confirm"
        await pilot.press("y")
        await pilot.pause(0.1)
        await pilot.press("a")
        await pilot.pause(0.1)
        assert nano.area.text == "cow cow dog cow"
        # exit and discard the change
        await pilot.press("ctrl+x")
        await pilot.press("n")
        await pilot.pause(0.3)
        assert isinstance(app.screen, TerminalScreen)
        assert gw_file(app, "todo.txt") == "cat cat dog cat"
        # ctrl+c on a Y/N prompt cancels instead of quitting the app
        await line(pilot, "nano todo.txt")
        await typ(pilot, "x")
        await pilot.press("ctrl+x")
        await pilot.press("ctrl+c")
        await pilot.pause(0.1)
        assert isinstance(app.screen, NanoScreen)
        assert app.screen.mode is None


@pytest.mark.asyncio
async def test_bbs_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    app = NullrouteApp()
    async with app.run_test(size=(120, 34)) as pilot:
        await start(pilot, app)
        await line(pilot, "ssh blackrelay.net")
        bbs = app.screen
        assert isinstance(bbs, BBSScreen)
        # first row is the accepted training contract: no accept key shown
        assert bbs.check_action("accept", ()) is False
        assert bbs.check_action("buy", ()) is False
        await pilot.press("down")
        await pilot.pause(0.1)
        c = bbs._selected_contract()
        assert c.status == "open"
        assert bbs.check_action("accept", ()) is True
        await pilot.press("a")
        await pilot.pause(0.2)
        assert c.status == "accepted"
        app.save_screenshot(str(SHOTS / "09_bbs_contracts.svg"))
        # number keys switch tabs
        await pilot.press("2")
        await pilot.pause(0.2)
        assert bbs.active_tab == "tab-store"
        assert bbs.check_action("buy", ()) is True
        assert bbs.check_action("accept", ()) is False
        app.save_screenshot(str(SHOTS / "10_bbs_store.svg"))
        await pilot.press("3")
        await pilot.pause(0.2)
        assert bbs.active_tab == "tab-docs"
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert isinstance(app.screen, TerminalScreen)
