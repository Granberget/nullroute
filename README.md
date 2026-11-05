# NULLROUTE

A terminal hacking game in the spirit of Uplink. You play a freelance
runner in a fictional cyberpunk net. You break corporate ICE with breach
programs and race a real-time trace. Once inside a node you work with
familiar Linux commands: `ls`, `cd`, `cat`, `grep`, `find`, `cp`, `rm`,
`ssh`, `scp`, `sudo`, `apt`, `nano`, `tail -f` and many more.

Everything in the game is fictional, but the shell is real enough that
playing it teaches you Linux. There are even built-in lessons (`learn`).

## Requirements

- Python 3.10 or newer
- A terminal at least about 110x30 characters

The launch scripts create a private virtual environment in `.venv` and
install the only dependency, [Textual](https://textual.textualize.io/),
the first time you run them.

## Start

### Windows

Double-click `play.bat`, or from PowerShell:

```powershell
.\play.bat
```

Windows Terminal gives the best result. If Python is missing, install it
from [python.org](https://www.python.org/downloads/) and tick
"Add python.exe to PATH".

### Linux and macOS

```bash
chmod +x play.sh     # once, if the file isn't executable yet
./play.sh
```

Or without changing permissions:

```bash
sh play.sh
```

If Python is missing:

- Debian/Ubuntu: `sudo apt install python3 python3-venv`
- Fedora: `sudo dnf install python3`
- macOS: `brew install python`, or the installer from python.org

On macOS, set the terminal to send Option as Meta to use the Alt shortcuts.
In Terminal.app this is under Settings → Profiles → Keyboard → "Use Option
as Meta key", and in iTerm2 under Profiles → Keys → Left Option = Esc+.
F2 works for switching terminals either way.

### Install it as a command (optional)

```bash
python3 -m pip install .
nullroute
```

## How to play

- Type `mail`, then `tutorial`. The tutorial walks you through a whole job
  on a training node, step by step.
- `ssh blackrelay.net` opens the agency BBS. It has contracts, a hardware
  and software store, docs (worth reading), news and your account.
  Keys 1-5 switch tabs, ↑/↓ choose a row, Esc returns to your shell. The
  bottom line only shows the keys that work on the current tab (`a` accept,
  `x` abandon, `s` submit answer, `b` buy).
- On your gateway you are a normal user. System files need `sudo`, which
  asks for the password you chose at the start (`passwd` changes it).
  Software from the store is installed with `sudo apt update` and
  `sudo apt install NAME`. Free extras: `nmap`, `htop`, `cowsay`,
  `fortune`, `figlet`, `sl`.
- Learning aids: `learn` (10 lessons with checked exercises), `man CMD`
  (with EXAMPLES), `achievements`, and tips (`tips off` turns them off).
- `help` lists all commands. Tab completes commands, files and host names.
  Ctrl+C stops a command.

### Keys

| Where | Keys |
|-------|------|
| Start menu | ↑/↓ choose, Enter select, Esc back. "Reset a password" sets a new sudo password for a save |
| Terminal | PgUp/PgDn or Shift+↑/↓ scroll, Ctrl+Home/End top/bottom, ↑/↓ history, Ctrl+L clear |
| Copy/paste | Drag with the mouse to select text, **Ctrl+Shift+C** copies it (Ctrl+C too, while text is selected). **Right-click** pastes at the prompt |
| Terminals | **Ctrl+N** (or `split`) new terminal, up to four side by side. **Alt+←/→** or **F2** switch, Alt+1..4 jump |
| Closing | `exit`, `logout` or Ctrl+D on your gateway closes a terminal. Closing the last one asks first, then logs out to the start menu |
| nano | `^O` write out, `^X` exit, `^W` search, `^\` replace, `^K`/`^U` cut/paste line, `^C` position, `^_` go to line, `^G` help, `M-U`/`M-E` undo/redo (`^` = Ctrl, `M-` = Alt) |
| top/htop | `q` quit, `P`/`M`/`N` sort by CPU/memory/PID, `k` kill |
| Mail inbox | `r` reply, `c` compose (Tab between fields, Ctrl+S send), `d` delete |
| Anywhere | Ctrl+Q saves and quits |

The game autosaves every minute while you are on your gateway. Saves live
in `~/.nullroute/` (Windows: `%USERPROFILE%\.nullroute\`).

### The loop

1. Accept a contract on the BBS. The briefing lands in `~/contracts/`.
   Tip: Ctrl+N and `contracts -f` in the new terminal gives a live checklist
   of every active job (next step, time left, commands to copy, trace).
2. `probe <node>` shows the ICE layers and whether your programs can break them.
3. `route add <relay>` adds a bounce hop. More hops means a slower trace.
4. `breach <node>`: **the trace starts now.**
5. `ssh <node>`, then do the job with ordinary commands.
6. `scrub` removes your footprint, then `exit`.
7. Report back by mail from your gateway.

Core nodes (`core.<corp>`) only accept connections from their intranet
node (`intra.<corp>`). Breach and ssh into the intranet node first.

| Contract | What you do |
|----------|-------------|
| Retrieve | `scp` a file home, then `mail -A ~/downloads/FILE client@...` |
| Wipe     | `rm` a file (and its backups), then mail the client to confirm |
| Modify   | Change one value in a CSV register (`nano`), then mail to confirm |
| Plant    | `scp gateway:~/contracts/<id>/<file> <dir>/` on the target |
| Find     | Find a passphrase (`grep -r`) and mail it to the client |

If a trace completes you get a strike and a fine. A footprint left behind
can also be traced back to you a few hours later. Three strikes and the
game is over.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"     # Windows: .venv\Scripts\python
.venv/bin/python -m pytest
```

The UI tests run the app headless and write SVG screenshots to
`screenshots/` (ignored by git).

### Code layout

```
nullroute/
  game/     world model: vfs (filesystem), nodes, world generation, engine
            (clock, trace, footprints, mail), contracts, store, packages,
            tutorial, learning (lessons, tips, achievements), save/load
  shell/    parser (pipes, redirects, && || &), shell core with users, jobs
            and permissions, and the commands (files, admin, network,
            processes, learning) plus man page examples
  ui/       Textual app: start menu, split-screen terminals, BBS, mail,
            map, nano, top
tests/      logic tests and headless UI tests
play.bat    Windows launcher
play.sh     Linux/macOS launcher
```

## Ideas for later

- Story campaign with recurring characters
- More ICE types and small interactive breach mini-games
- Shell scripts, variables and aliases (`for` loops, `~/.bashrc`)
- Text tools: `sed`, `awk`, `cut`, `tr`, `diff`, `xargs`
- Rival runners competing for the same contracts
