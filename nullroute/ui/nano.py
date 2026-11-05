"""A GNU nano look-alike built on Textual's TextArea.

Implements the everyday nano workflow: ^O write out (with file name
prompt), ^X exit (asks to save a modified buffer), ^W search, ^\\ replace,
^K / ^U cut and paste lines, ^C cursor position, ^_ go to line, ^G help,
M-U / M-E undo and redo.
"""

from __future__ import annotations

from typing import Callable

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Label, Static, TextArea
from textual.widgets.text_area import Selection

# (key, label) pairs for the two shortcut rows at the bottom of the screen
MAIN_KEYS = [
    [("^G", "Help"), ("^O", "Write Out"), ("^W", "Where Is"), ("^K", "Cut"),
     ("^C", "Location"), ("M-U", "Undo")],
    [("^X", "Exit"), ("^R", "Read File"), ("^\\", "Replace"), ("^U", "Paste"),
     ("^_", "Go To Line"), ("M-E", "Redo")],
]
PROMPT_KEYS = [[("Enter", "Confirm"), ("^C", "Cancel")], [("Up/Down", "Previous answers")]]
YESNO_KEYS = [[("Y", "Yes")], [("N", "No"), ("^C", "Cancel")]]
REPLACE_KEYS = [[("Y", "Yes"), ("A", "All")], [("N", "No"), ("^C", "Cancel")]]

HELP_TEXT = """\
Main nano help text

The nano editor is designed to emulate the functionality and ease-of-use
of the UW Pico text editor. The editor has four main sections. The top line
shows the program version, the current filename being edited, and whether
or not the file has been modified. Next is the main editor window showing
the file being edited. The status line is the third line from the bottom
and shows important messages. The bottom two lines show the most commonly
used shortcuts in the editor.

Shortcuts are written as follows: Control-key sequences are notated with a
'^' and can be entered either by using the Ctrl key or pressing the Esc key
twice. Meta-key sequences are notated with 'M-' and can be entered using
either the Alt or the Esc key.

^G          Display this help text
^X          Close the current buffer / Exit from nano
^O          Write the current buffer to disk (asks for a file name)
^S          Save the file without prompting
^R          Insert another file into the current one
^W          Search forward for a string
M-W         Repeat the last search
^\\          Replace a string
^K          Cut the current line into the cutbuffer
^U          Paste the contents of the cutbuffer at the cursor
^C          Display the position of the cursor
^_ / M-G    Go to line and column number
^A / ^E     Go to beginning / end of the current line
^Y / ^V     Go one screenful up / down
M-\\ / M-/   Go to the first / last line of the file
M-U / M-E   Undo / Redo the last operation

Press ^X, Esc or q to close this help."""


def shortcut_bar(rows: list[list[tuple[str, str]]], width: int = 16) -> Text:
    out = Text()
    for i, row in enumerate(rows):
        for key, label in row:
            out.append(key, "reverse")
            out.append(" " + label.ljust(width - len(key) - 1))
        if i < len(rows) - 1:
            out.append("\n")
    return out


class NanoArea(TextArea):
    """TextArea with nano's key bindings instead of the default ones."""

    BINDINGS = [
        Binding("ctrl+x", "nano('exit')", show=False),
        Binding("ctrl+o", "nano('write_out')", show=False),
        Binding("ctrl+s", "nano('save')", show=False),
        Binding("ctrl+r", "nano('read_file')", show=False),
        Binding("ctrl+w", "nano('search')", show=False),
        Binding("alt+w", "nano('search_again')", show=False),
        Binding("ctrl+backslash", "nano('replace')", show=False),
        Binding("ctrl+k", "nano('cut')", show=False),
        Binding("ctrl+u", "nano('paste')", show=False),
        Binding("ctrl+c", "nano('location')", show=False),
        Binding("ctrl+underscore,alt+g", "nano('goto')", show=False),
        Binding("ctrl+g", "nano('help')", show=False),
        Binding("alt+u", "undo", show=False),
        Binding("alt+e", "redo", show=False),
        Binding("ctrl+y", "cursor_page_up", show=False),
        Binding("ctrl+v", "cursor_page_down", show=False),
        Binding("alt+backslash", "nano('top')", show=False),
        Binding("alt+slash", "nano('bottom')", show=False),
        Binding("ctrl+z", "nano('suspend')", show=False),
        Binding("ctrl+t", "nano('execute')", show=False),
        Binding("ctrl+j", "nano('justify')", show=False),
    ]

    def action_nano(self, name: str) -> None:
        self.screen.nano_action(name)


class PromptInput(Input):
    BINDINGS = [
        Binding("ctrl+c", "cancel", show=False, priority=True),
        Binding("escape", "cancel", show=False),
        Binding("up", "history(-1)", show=False),
        Binding("down", "history(1)", show=False),
    ]

    def action_cancel(self) -> None:
        self.screen.cancel_prompt()

    def action_history(self, delta: int) -> None:
        self.screen.prompt_history(delta)


class NanoHelp(ModalScreen):
    BINDINGS = [Binding("escape,q,ctrl+x,ctrl+g", "close", show=False)]
    CSS = """
    NanoHelp { background: $background; }
    #nano-help { padding: 0 1; }
    #help-keys { dock: bottom; height: 2; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(HELP_TEXT, id="nano-help")
        yield Static(shortcut_bar([[("^X", "Close")], [("Up/Dn", "Scroll")]]), id="help-keys")

    def action_close(self) -> None:
        self.dismiss(None)


class NanoScreen(Screen):
    """Full-screen nano. Writes through the callbacks it is given."""

    CSS = """
    NanoScreen { background: $background; layout: vertical; }
    #nano-title { height: 1; background: $foreground; color: $background; }
    NanoArea { height: 1fr; border: none; padding: 0; background: $background; }
    NanoArea:focus { border: none; }
    #nano-status { height: 1; content-align: center middle; }
    #nano-prompt { height: 1; display: none; background: $foreground; color: $background; }
    #nano-prompt Label { width: auto; background: $foreground; color: $background; }
    #nano-prompt Input { height: 1; border: none; padding: 0; width: 1fr;
                         background: $foreground; color: $background; }
    #nano-keys { height: 2; }
    """

    # Only reached while a Y/N prompt is active (nothing has focus then).
    BINDINGS = [Binding("ctrl+c,escape", "cancel_keys", show=False)]

    def action_cancel_keys(self) -> None:
        if self.mode in ("save_changes", "replace_confirm"):
            n = self.replaced if self.mode == "replace_confirm" else 0
            self.cancel_prompt()
            if n:
                self.status(f"Replaced {n} occurrence{'s' if n != 1 else ''}")

    def __init__(self, path: str, content: str, *, new_file: bool,
                 write: Callable[[str, str], str | None],
                 read: Callable[[str], tuple[str | None, str | None]],
                 start_line: int = 0):
        super().__init__()
        self.path = path
        self.saved = content
        self.new_file = new_file
        self.write_cb = write
        self.read_cb = read
        self.start_line = start_line
        self.mode: str | None = None          # active prompt
        self.after_write: str | None = None   # "exit" when ^X -> Y -> write
        self.cutbuffer = ""
        self.last_was_cut = False
        self.last_search = ""
        self.history: dict[str, list[str]] = {}
        self.hist_pos = 0
        self.replace_with = ""
        self.replaced = 0
        self.r_origin = (0, 0)
        self.r_wrapped = False
        self.status_timer = None

    # ------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Static(id="nano-title")
        yield NanoArea(self.saved, id="nano-text", soft_wrap=False,
                       show_line_numbers=False, tab_behavior="indent")
        yield Static(id="nano-status")
        with Horizontal(id="nano-prompt"):
            yield Label("", id="nano-prompt-label")
            yield PromptInput(id="nano-prompt-input")
        yield Static(id="nano-keys")

    def on_mount(self) -> None:
        area = self.area
        area.focus()
        if self.start_line:
            area.move_cursor((max(0, self.start_line - 1), 0))
        self._title()
        self._keys(MAIN_KEYS)
        lines = self.saved.count("\n") + (0 if self.saved.endswith("\n") or not self.saved else 1)
        self.status("New File" if self.new_file else f"Read {lines} line{'s' if lines != 1 else ''}")

    @property
    def area(self) -> NanoArea:
        return self.query_one(NanoArea)

    @property
    def modified(self) -> bool:
        return self.area.text != self.saved

    def _title(self) -> None:
        width = max(40, self.size.width or 80)
        left = "  GNU nano 7.2"
        name = self.path if self.path else "New Buffer"
        right = "Modified  " if self.modified else ""
        mid = name.center(width - len(left) * 2)
        line = (left + mid).ljust(width - len(right)) + right
        self.query_one("#nano-title", Static).update(Text(line[:width]))

    def _keys(self, rows) -> None:
        self.query_one("#nano-keys", Static).update(shortcut_bar(rows))

    def status(self, message: str) -> None:
        st = self.query_one("#nano-status", Static)
        st.update(Text(f"[ {message} ]", "reverse") if message else "")
        if self.status_timer:
            self.status_timer.stop()
        if message:
            self.status_timer = self.set_timer(4.0, lambda: st.update(""))

    def on_text_area_changed(self, event) -> None:
        self._title()

    def on_resize(self, event: events.Resize) -> None:
        self._title()

    # ------------------------------------------------------------ prompts
    def ask(self, mode: str, label: str, default: str = "") -> None:
        """Show a one-line text prompt above the shortcut bar."""
        self.mode = mode
        self.hist_pos = 0
        self.query_one("#nano-status", Static).update("")
        self.query_one("#nano-prompt-label", Label).update(Text(label))
        row = self.query_one("#nano-prompt")
        row.display = True
        inp = self.query_one("#nano-prompt-input", PromptInput)
        inp.value = default
        inp.cursor_position = len(default)
        inp.focus()
        self._keys(PROMPT_KEYS)

    def ask_keys(self, mode: str, label: str, rows) -> None:
        """Show a Y/N style prompt that reacts to single key presses."""
        self.mode = mode
        self.query_one("#nano-prompt-label", Label).update(Text(label))
        self.query_one("#nano-prompt").display = True
        self.query_one("#nano-prompt-input").display = False
        self.query_one("#nano-status", Static).update("")
        self.set_focus(None)
        self._keys(rows)

    def end_prompt(self, focus: bool = True) -> None:
        self.mode = None
        self.query_one("#nano-prompt").display = False
        self.query_one("#nano-prompt-input").display = True
        self._keys(MAIN_KEYS)
        if focus:
            self.area.focus()

    def cancel_prompt(self) -> None:
        self.end_prompt()
        self.after_write = None
        self.status("Cancelled")

    def prompt_history(self, delta: int) -> None:
        hist = self.history.get(self.mode or "", [])
        if not hist:
            return
        self.hist_pos = max(-len(hist), min(0, self.hist_pos + delta))
        inp = self.query_one("#nano-prompt-input", PromptInput)
        inp.value = hist[self.hist_pos] if self.hist_pos < 0 else ""
        inp.cursor_position = len(inp.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        mode, value = self.mode, event.value
        if mode and value:
            hist = self.history.setdefault(mode, [])
            if not hist or hist[-1] != value:
                hist.append(value)
        self.end_prompt(focus=False)
        self._handle_answer(mode, value)
        if self.mode is None:
            self.area.focus()

    def _handle_answer(self, mode: str | None, value: str) -> None:
        if mode == "write":
            self._write(value)
        elif mode == "search":
            if value:
                self.last_search = value
            if self.last_search:
                self._search(self.last_search)
            else:
                self.status("Cancelled")
        elif mode == "replace_search":
            if not value and not self.last_search:
                self.status("Cancelled")
                return
            if value:
                self.last_search = value
            self.ask("replace_with", "Replace with: ")
        elif mode == "replace_with":
            self.replace_with = value
            self.replaced = 0
            self._replace_next()
        elif mode == "goto":
            self._goto(value)
        elif mode == "read":
            self._read(value)

    def on_key(self, event: events.Key) -> None:
        if self.mode not in ("save_changes", "replace_confirm"):
            return
        event.stop()
        event.prevent_default()
        key = event.key.lower()
        if key in ("ctrl+c", "escape"):
            self.action_cancel_keys()
            return
        if self.mode == "save_changes":
            if key == "y":
                self.end_prompt(focus=False)
                self.after_write = "exit"
                self.ask("write", "File Name to Write: ", self.path)
            elif key == "n":
                self.dismiss(None)
        elif self.mode == "replace_confirm":
            if key in ("y", "n", "a"):
                self._replace_answer(key)

    # ------------------------------------------------------------ actions
    def nano_action(self, name: str) -> None:
        if name != "cut":
            self.last_was_cut = False
        getattr(self, f"_do_{name}")()

    def _do_exit(self) -> None:
        if self.modified:
            self.ask_keys("save_changes",
                          "Save modified buffer?  (Answering \"No\" will DISCARD changes.) ",
                          YESNO_KEYS)
        else:
            self.dismiss(None)

    def _do_write_out(self) -> None:
        self.after_write = None
        self.ask("write", "File Name to Write: ", self.path)

    def _do_save(self) -> None:
        self.after_write = None
        self._write(self.path)

    def _do_read_file(self) -> None:
        self.ask("read", "File to insert [from ./]: ")

    def _do_search(self) -> None:
        hint = f" [{self.last_search}]" if self.last_search else ""
        self.ask("search", f"Search{hint}: ")

    def _do_search_again(self) -> None:
        if self.last_search:
            self._search(self.last_search)
        else:
            self.status("No current search pattern")

    def _do_replace(self) -> None:
        hint = f" [{self.last_search}]" if self.last_search else ""
        self.ask("replace_search", f"Search (to replace){hint}: ")

    def _do_cut(self) -> None:
        area = self.area
        lines = area.text.split("\n")
        row = area.cursor_location[0]
        line = lines[row]
        if row < len(lines) - 1:
            area.delete((row, 0), (row + 1, 0))
            chunk = line + "\n"
        else:
            area.delete((row, 0), (row, len(line)))
            chunk = line
        self.cutbuffer = (self.cutbuffer + chunk) if self.last_was_cut else chunk
        self.last_was_cut = True
        area.move_cursor((min(row, area.document.line_count - 1), 0))

    def _do_paste(self) -> None:
        if not self.cutbuffer:
            self.status("Cutbuffer is empty")
            return
        self.area.insert(self.cutbuffer)

    def _do_location(self) -> None:
        area = self.area
        row, col = area.cursor_location
        lines = area.text.split("\n")
        total_lines = len(lines)
        line_len = len(lines[row]) + 1
        char = sum(len(l) + 1 for l in lines[:row]) + col + 1
        total_chars = len(area.text) + 1
        pct = lambda a, b: int(a * 100 / b) if b else 0  # noqa: E731
        self.status(f"line {row + 1}/{total_lines} ({pct(row + 1, total_lines)}%), "
                    f"col {col + 1}/{line_len} ({pct(col + 1, line_len)}%), "
                    f"char {char}/{total_chars} ({pct(char, total_chars)}%)")

    def _do_goto(self) -> None:
        self.ask("goto", "Enter line number, column number: ")

    def _do_help(self) -> None:
        self.app.push_screen(NanoHelp())

    def _do_top(self) -> None:
        self.area.move_cursor((0, 0))

    def _do_bottom(self) -> None:
        area = self.area
        last = area.document.line_count - 1
        area.move_cursor((last, len(area.document.get_line(last))))

    def _do_suspend(self) -> None:
        self.status("Suspension is not enabled")

    def _do_execute(self) -> None:
        self.status("Execute is not available on this node")

    def _do_justify(self) -> None:
        self.status("Justify is not available")

    # ------------------------------------------------------------ helpers
    def _write(self, name: str) -> None:
        name = name.strip()
        if not name:
            self.status("Cancelled")
            self.after_write = None
            return
        text = self.area.text
        err = self.write_cb(name, text)
        if err:
            self.status(f"Error writing {name}: {err}")
            self.after_write = None
            return
        self.path = name
        self.saved = text
        self.new_file = False
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        self._title()
        self.status(f"Wrote {lines} line{'s' if lines != 1 else ''}")
        if self.after_write == "exit":
            self.dismiss(None)
        self.after_write = None

    def _read(self, name: str) -> None:
        if not name.strip():
            self.status("Cancelled")
            return
        text, err = self.read_cb(name.strip())
        if err:
            self.status(err)
            return
        self.area.insert(text or "")
        n = (text or "").count("\n")
        self.status(f"Read {n} line{'s' if n != 1 else ''}")

    def _find(self, needle: str, start: tuple[int, int]) -> tuple[tuple[int, int] | None, bool]:
        """Case-insensitive search from start. Returns (location, wrapped)."""
        lines = self.area.text.split("\n")
        low = needle.lower()
        row, col = start
        for r in range(row, len(lines)):
            idx = lines[r].lower().find(low, col if r == row else 0)
            if idx >= 0:
                return (r, idx), False
        for r in range(0, row + 1):
            idx = lines[r].lower().find(low)
            if idx >= 0 and (r < row or idx < col):
                return (r, idx), True
        return None, False

    def _search(self, needle: str) -> None:
        area = self.area
        row, col = area.cursor_location
        here = area.text.split("\n")[row][col:col + len(needle)].lower() == needle.lower()
        loc, wrapped = self._find(needle, (row, col + 1 if here else col))
        if loc is None:
            self.status(f"\"{needle}\" not found")
            return
        area.selection = Selection(loc, (loc[0], loc[1] + len(needle)))
        if wrapped:
            self.status("Search Wrapped")
        elif loc == (row, col):
            self.status("This is the only occurrence")

    def _next_replace_loc(self, start: tuple[int, int]) -> tuple[int, int] | None:
        """Next match for replace: wraps around once, stops at the origin."""
        loc, wrapped = self._find(self.last_search, start)
        if loc is None:
            return None
        if wrapped:
            if self.r_wrapped:
                return None
            self.r_wrapped = True
        if self.r_wrapped and loc >= self.r_origin:
            return None
        return loc

    def _replace_next(self, start: tuple[int, int] | None = None) -> None:
        area = self.area
        if start is None:
            start = area.cursor_location
            self.r_origin = start
            self.r_wrapped = False
        loc = self._next_replace_loc(start)
        if loc is None:
            n = self.replaced
            self.status(f"Replaced {n} occurrence{'s' if n != 1 else ''}")
            return
        area.selection = Selection(loc, (loc[0], loc[1] + len(self.last_search)))
        self.ask_keys("replace_confirm", "Replace this instance? ", REPLACE_KEYS)

    def _replace_answer(self, key: str) -> None:
        area = self.area
        (r, c) = area.selection.start
        end = (r, c + len(self.last_search))
        if key in ("y", "a"):
            area.replace(self.replace_with, (r, c), end)
            self.replaced += 1
            nxt = (r, c + len(self.replace_with))
        else:
            nxt = (r, c + 1)
        if key == "a":
            while True:
                loc = self._next_replace_loc(nxt)
                if loc is None:
                    break
                area.replace(self.replace_with, loc, (loc[0], loc[1] + len(self.last_search)))
                self.replaced += 1
                nxt = (loc[0], loc[1] + len(self.replace_with))
            self.end_prompt()
            n = self.replaced
            self.status(f"Replaced {n} occurrence{'s' if n != 1 else ''}")
            return
        self.end_prompt(focus=False)
        area.move_cursor(nxt)
        self._replace_next(nxt)
        if self.mode is None:
            area.focus()

    def _goto(self, value: str) -> None:
        area = self.area
        parts = [p.strip() for p in value.replace(" ", ",").split(",") if p.strip()]
        try:
            line = int(parts[0]) if parts else 0
            col = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            self.status("Invalid line or column number")
            return
        if not parts:
            self.status("Cancelled")
            return
        total = area.document.line_count
        line = total if line < 0 else max(1, min(line, total))
        text = area.document.get_line(line - 1)
        area.move_cursor((line - 1, max(0, min(col - 1, len(text)))))
