"""The shell: frames (where you are), users, expansion, pipelines, jobs."""

from __future__ import annotations

import asyncio
import difflib
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from ..game.engine import Conn, Game
from ..game.vfs import VFS, Dir, File, FSError, Identity, allowed, normpath
from ..game.world import GATEWAY
from .parser import ParseError, Pipeline, Word, parse, tokenize

ROOT = Identity("root", {"root"})
BIN_DIRS = {"/bin", "/usr/bin", "/usr/local/bin", "/sbin", "/usr/sbin"}


class UI(Protocol):
    def write(self, text: str, style: str | None = None) -> None: ...
    def progress(self, text: str | None) -> None: ...
    async def prompt(self, label: str, secret: bool = False) -> str: ...
    async def open_view(self, name: str, **kw) -> object: ...
    def clear(self) -> None: ...
    def quit(self) -> None: ...
    def logout(self) -> None: ...
    def new_terminal(self) -> None: ...


@dataclass
class Frame:
    node: str
    cwd: str
    conn: Conn | None = None
    user: str = "root"

    @property
    def path(self) -> list[str]:
        return self.conn.path if self.conn else [GATEWAY]


@dataclass
class CmdSpec:
    name: str
    fn: Callable[["Ctx"], Awaitable[int]]
    summary: str
    usage: str = ""
    man: str = ""
    group: str = "files"


@dataclass
class Job:
    id: int
    pid: int
    text: str
    task: asyncio.Task
    node: str
    status: str = "Running"


class Ctx:
    def __init__(self, shell: "Shell", argv: list[str], stdin: str | None,
                 sink: Callable[[str, str | None], None],
                 errsink: Callable[[str], None], *, user: str, frame: Frame,
                 piped: bool = False, background: bool = False):
        self.shell = shell
        self.argv = argv
        self.args = argv[1:]
        self.stdin = stdin
        self._sink = sink
        self._err = errsink
        self.user = user
        self._frame = frame
        self.piped = piped            # stdout goes to a pipe or file, not the screen
        self.background = background  # started with &

    # output
    def write(self, text: str = "", style: str | None = None) -> None:
        self._sink(text, style)

    def err(self, text: str) -> None:
        self._err(f"{self.argv[0]}: {text}")

    # shortcuts
    @property
    def game(self) -> Game:
        return self.shell.game

    @property
    def ui(self) -> UI:
        return self.shell.ui

    @property
    def frame(self) -> Frame:
        return self._frame

    @property
    def fs(self) -> VFS:
        fs = self.game.world.nodes[self._frame.node].fs
        assert fs is not None
        return fs

    @property
    def cwd(self) -> str:
        return self._frame.cwd

    @property
    def at_gateway(self) -> bool:
        return self._frame.node == GATEWAY

    @property
    def is_root(self) -> bool:
        return self.user == "root"

    @property
    def ident(self) -> Identity:
        return self.shell.identity(self.user)

    @property
    def home(self) -> str:
        return self.shell.home_for(self.user, self._frame.node)

    # filesystem helpers with permission checks
    def resolve(self, path: str, want: str | None = None):
        return self.fs.resolve(path, self.cwd, self.ident, want=want)

    def need(self, node, perm: str, path: str) -> None:
        if not allowed(node, self.ident, perm):
            raise FSError(f"{path}: Permission denied")

    def parent_for_write(self, path: str) -> tuple[Dir, str]:
        """Parent directory of path, checking we may create entries in it."""
        parent, name = self.fs.parent_of(self.abspath(path), "/", self.ident)
        self.need(parent, "w", path)
        return parent, name

    def can_delete(self, node) -> bool:
        parent = node.parent
        if parent is None or not allowed(parent, self.ident, "w"):
            return False
        if parent.mode & 0o1000 and not self.is_root:      # sticky bit (/tmp)
            return node.owner == self.user or parent.owner == self.user
        return True

    def new_file(self, name: str, content: str = "") -> File:
        return File(name, content, owner=self.user, group=self.user,
                    mode=0o644, mtime=self.game.now)

    def new_dir(self, name: str) -> Dir:
        return Dir(name, owner=self.user, group=self.user, mode=0o755,
                   mtime=self.game.now)

    def abspath(self, path: str) -> str:
        return normpath(path, self.cwd)

    async def sleep(self, seconds: float, label: str | None = None,
                    render: Callable[[float], str] | None = None) -> None:
        """Wait in real time while showing a progress line."""
        if self.background:
            await asyncio.sleep(seconds)
            return
        steps = max(1, int(seconds / 0.1))
        for i in range(steps + 1):
            frac = i / steps
            if render:
                self.ui.progress(render(frac))
            elif label:
                self.ui.progress(f"{label} {bar(frac)} {int(frac * 100):3d}%")
            if i < steps:
                await asyncio.sleep(seconds / steps)
        self.ui.progress(None)


def bar(frac: float, width: int = 24) -> str:
    frac = max(0.0, min(1.0, frac))
    full = int(frac * width)
    return "[" + "█" * full + "░" * (width - full) + "]"


class Shell:
    def __init__(self, game: Game, ui: UI):
        self.game = game
        self.ui = ui
        state = game.state
        self.frames: list[Frame] = [Frame(GATEWAY, state.home, user=state.handle)]
        self.history: list[str] = []
        self.commands: dict[str, CmdSpec] = {}
        self.aliases: dict[str, str] = {"ll": "ls -la", "la": "ls -a", "l": "ls -l",
                                        "hint": "tutorial", "logout": "exit",
                                        "more": "less", "vi": "nano", "vim": "nano",
                                        "dir": "ls"}
        self.last_status = 0
        self.last_args: list[str] = []
        self.jobs: list[Job] = []
        self.sudo_until = -1.0
        self.observers: list[Callable[[str, list[Pipeline], int], None]] = []
        self._next_pid = 4100
        from . import commands
        commands.register(self)

    # ------------------------------------------------------------ users
    @property
    def handle(self) -> str:
        return self.game.state.handle

    def identity(self, user: str) -> Identity:
        if user == "root":
            return ROOT
        if user == self.handle:
            return Identity(user, {user, "sudo", "adm"})
        return Identity(user, {user})

    def home_for(self, user: str, node: str) -> str:
        if node != GATEWAY:
            return "/"
        return "/root" if user == "root" else self.game.state.home

    # ------------------------------------------------------------ state
    @property
    def frame(self) -> Frame:
        return self.frames[-1]

    @property
    def fs(self) -> VFS:
        fs = self.game.world.nodes[self.frame.node].fs
        assert fs is not None
        return fs

    def home_dir(self) -> str:
        return self.home_for(self.frame.user, self.frame.node)

    def prompt(self) -> str:
        node = self.game.world.nodes[self.frame.node]
        cwd = self.frame.cwd
        home = self.home_dir()
        if home != "/" and (cwd == home or cwd.startswith(home + "/")):
            cwd = "~" + cwd[len(home):]
        user = self.frame.user
        sign = "#" if user == "root" else "$"
        return f"{user}@{node.short}:{cwd}{sign} "

    def add(self, spec: CmdSpec) -> None:
        self.commands[spec.name] = spec

    def disconnect_all(self) -> None:
        """Drop every remote connection; local (gateway) shells survive."""
        for f in self.frames:
            if f.conn:
                self.game.close_conn(f.conn)
        self.frames = [f for f in self.frames if f.node == GATEWAY] or self.frames[:1]

    def pop_frame(self) -> Frame | None:
        if len(self.frames) <= 1:
            return None
        f = self.frames.pop()
        if f.conn:
            self.game.close_conn(f.conn)
        return f

    def new_pid(self) -> int:
        self._next_pid += self.game.state.rng.randint(1, 37)
        return self._next_pid

    # ------------------------------------------------------------ expansion
    def expand(self, words: list[Word]) -> list[str]:
        out: list[str] = []
        for w in words:
            text = w.text
            if not w.quoted:
                if text == "~" or text.startswith("~/"):
                    text = self.home_dir() + text[1:]
                text = self._vars(text)
                if any(c in text for c in "*?["):
                    matches = self.fs.glob(text, self.frame.cwd)
                    if matches:
                        out.extend(matches)
                        continue
            out.append(text)
        return out

    def _vars(self, text: str) -> str:
        if "$" not in text:
            return text
        env = {"HOME": self.home_dir(), "USER": self.frame.user,
               "HOSTNAME": self.game.world.nodes[self.frame.node].hostname,
               "PWD": self.frame.cwd, "?": str(self.last_status),
               "SHELL": "/bin/bash", "$": str(self._next_pid - 3)}
        for k in sorted(env, key=len, reverse=True):
            text = text.replace("${" + k + "}", env[k]).replace("$" + k, env[k])
        return text

    def _history_expand(self, line: str) -> tuple[str, bool]:
        if "!" not in line or not self.history:
            return line, False
        new = line.replace("!!", self.history[-1])
        if "!$" in new:
            last = self.last_args[-1] if self.last_args else ""
            new = new.replace("!$", last)
        return new, new != line

    # ------------------------------------------------------------ running
    async def run_line(self, line: str) -> int:
        line = line.strip()
        if not line:
            return self.last_status
        line, expanded = self._history_expand(line)
        if expanded:
            self.ui.write(line)
        self.history.append(line)
        try:
            pipelines = parse(line)
        except ParseError as e:
            self.ui.write(f"bash: {e}", "error")
            self.last_status = 2
            return 2
        status = 0
        prev_op = ";"
        for pl in pipelines:
            if prev_op == "&&" and status != 0:
                prev_op = pl.op
                continue
            if prev_op == "||" and status == 0:
                prev_op = pl.op
                continue
            if pl.background:
                self.start_job(pl)
                status = 0
            else:
                status = await self.run_pipeline(pl.commands)
            self.last_status = status
            prev_op = pl.op
        words = [w.text for w in pipelines[-1].commands[-1].words] if pipelines else []
        if words:
            self.last_args = words
        for obs in self.observers:
            try:
                obs(line, pipelines, status)
            except Exception:  # noqa: BLE001 - learning hooks must never break the shell
                pass
        return status

    # ------------------------------------------------------------ jobs
    def start_job(self, pl: Pipeline) -> Job:
        text = " | ".join(" ".join(w.text for w in c.words) for c in pl.commands)
        job_id = max((j.id for j in self.jobs), default=0) + 1
        pid = self.new_pid()
        frame = self.frame
        task = asyncio.ensure_future(self.run_pipeline(pl.commands, background=True, frame=frame))
        job = Job(job_id, pid, text, task, frame.node)
        self.jobs.append(job)
        self.ui.write(f"[{job_id}] {pid}")
        task.add_done_callback(lambda t, j=job: self._job_done(j, t))
        return job

    def _job_done(self, job: Job, task: asyncio.Task) -> None:
        if task.cancelled():
            job.status = "Terminated"
        else:
            exc = task.exception()
            code = 1 if exc else (task.result() or 0)
            job.status = "Done" if code == 0 else f"Exit {code}"
        self.ui.write(f"[{job.id}]+  {job.status:<22}{job.text}", "dim")
        if job in self.jobs:
            self.jobs.remove(job)

    def find_job(self, spec: str) -> Job | None:
        spec = spec.lstrip("%")
        if not spec and self.jobs:
            return self.jobs[-1]
        for j in self.jobs:
            if str(j.id) == spec or str(j.pid) == spec:
                return j
        return None

    # ------------------------------------------------------------ pipelines
    async def run_pipeline(self, cmds, background: bool = False,
                           frame: Frame | None = None, user: str | None = None) -> int:
        frame = frame or self.frame
        data: str | None = None
        status = 0
        for i, cmd in enumerate(cmds):
            last = i == len(cmds) - 1
            words = list(cmd.words)
            if words and not words[0].quoted and words[0].text in self.aliases:
                alias = [t for t in tokenize(self.aliases[words[0].text]) if isinstance(t, Word)]
                words = alias + words[1:]
            argv = self.expand(words)
            if not argv:
                continue
            stdin = data
            if cmd.stdin:
                try:
                    stdin = self._read_file(cmd.stdin, frame)
                except FSError as e:
                    self.ui.write(f"bash: {e}", "error")
                    return 1
            buf: list[str] = []
            to_buffer = (not last) or cmd.stdout is not None

            def sink(text: str, style: str | None = None, _buf=buf, _tb=to_buffer):
                if _tb:
                    _buf.append(text)
                else:
                    self.ui.write(text, style)

            def errsink(text: str, _cmd=cmd, _sink=sink):
                if _cmd.stderr == "/dev/null":
                    return
                if _cmd.stderr == "&1":
                    _sink(text)
                    return
                self.ui.write(text, "error")

            status = await self.dispatch(argv, stdin, sink, errsink, piped=to_buffer,
                                         user=user, background=background, frame=frame)
            data = "\n".join(buf) + ("\n" if buf else "")
            if cmd.stdout is not None:
                try:
                    self._write_file(cmd.stdout, data, cmd.append, frame)
                except FSError as e:
                    self.ui.write(f"bash: {e}", "error")
                    return 1
                data = ""
        return status

    async def dispatch(self, argv, stdin, sink, errsink, piped: bool = False,
                       user: str | None = None, background: bool = False,
                       frame: Frame | None = None) -> int:
        frame = frame or self.frame
        name = argv[0]
        if "/" in name:                     # /usr/bin/decrypt -> decrypt
            path = normpath(name, frame.cwd)
            head, base = path.rsplit("/", 1)
            if head in BIN_DIRS and base in self.commands:
                name = base
                argv = [base, *argv[1:]]
        spec = self.commands.get(name)
        if spec is None:
            errsink(self._not_found(name))
            return 127
        from ..game import packages
        pkg = packages.COMMAND_PKG.get(name)
        if pkg and not packages.is_installed(self.game.state, pkg):
            errsink(f"Command '{name}' not found, but can be installed with:\n"
                    f"  sudo apt install {pkg}")
            return 127
        ctx = Ctx(self, argv, stdin, sink, errsink, user=user or frame.user, frame=frame,
                  piped=piped, background=background)
        try:
            result = await spec.fn(ctx)
        except FSError as e:
            ctx.err(str(e))
            return 1
        except asyncio.CancelledError:
            if not background:
                self.ui.progress(None)
            raise
        return result or 0

    def _not_found(self, name: str) -> str:
        if "/" in name:
            return f"bash: {name}: No such file or directory"
        from ..game import packages
        if name in packages.PACKAGES:
            return (f"Command '{name}' not found, but can be installed with:\n"
                    f"  sudo apt install {name}")
        names = sorted(set(self.commands) | set(self.aliases))
        close = difflib.get_close_matches(name, names, n=3, cutoff=0.75)
        if close:
            lines = [f"Command '{name}' not found, did you mean:"]
            lines += [f"  command '{c}'" for c in close]
            return "\n".join(lines)
        return f"{name}: command not found"

    def _read_file(self, path: str, frame: Frame) -> str:
        fs = self.game.world.nodes[frame.node].fs
        ident = self.identity(frame.user)
        node = fs.resolve(path, frame.cwd, ident, want="file")
        if not allowed(node, ident, "r"):
            raise FSError(f"{path}: Permission denied")
        assert isinstance(node, File)
        return node.content

    def _write_file(self, path: str, data: str, append: bool, frame: Frame) -> None:
        """Redirection: always runs as the shell's user, never as sudo."""
        if path == "/dev/null":
            return
        fs = self.game.world.nodes[frame.node].fs
        ident = self.identity(frame.user)
        full = normpath(path, frame.cwd)
        node = fs.get(full)
        if node is not None and node.is_dir:
            raise FSError(f"{path}: Is a directory")
        if isinstance(node, File):
            if not allowed(node, ident, "w"):
                raise FSError(f"{path}: Permission denied")
            node.content = (node.content + data) if append else data
            node.binary = False
            node.fake_size = None
            node.mtime = self.game.now
            return
        parent, name = fs.parent_of(full, "/", ident)
        if not allowed(parent, ident, "w"):
            raise FSError(f"{path}: Permission denied")
        parent.add(File(name, data, owner=frame.user, group=frame.user,
                        mtime=self.game.now))

    # ------------------------------------------------------------ completion
    def complete(self, text: str) -> tuple[str, list[str]]:
        """Complete the last word of text. Returns (new_text, candidates)."""
        head, sep, word = text.rpartition(" ")
        prefix = head + sep
        # only the last command of a pipeline / list matters: 'echo x | mail ...'
        seg = re.split(r"\|\||&&|[|;]", head)[-1]
        first = not seg.strip() or seg.strip() in ("sudo", "man", "which")
        if first:
            names = sorted(set(self.commands) | set(self.aliases))
            cands = [n for n in names if n.startswith(word)]
            return self._apply(prefix, word, cands, " ")
        parts = seg.split()
        cmd = parts[1] if parts and parts[0] == "sudo" and len(parts) > 1 else (parts[0] if parts else "")
        hostish = cmd in ("ssh", "breach", "probe", "hydra", "ping", "traceroute", "host",
                          "nslookup", "dig") or (cmd == "route" and len(parts) >= 2)
        cands: list[str] = []
        if cmd in ("apt", "apt-get") and len(parts) >= 2:
            from ..game import packages
            cands = [p for p in sorted(packages.PACKAGES) if p.startswith(word)]
            return self._apply(prefix, word, cands, " ")
        if cmd == "mail" and len(parts) >= 1:
            prev = parts[-1] if len(parts) > 1 else ""
            active = [c for c in self.game.state.contracts if c.status == "accepted"]
            if prev == "-s":
                # subject: the contract id is what clients look for
                cands = [c.id for c in active if c.id.lower().startswith(word.lower())]
                return self._apply(prefix, word, cands, " ")
            if prev not in ("-A", "-a", "--attach") and not word.startswith(("-", "~", "/", ".")):
                addrs = [c.client_addr for c in active if c.client_addr]
                addrs.append("vex@blackrelay.net")
                cands = [a for a in dict.fromkeys(addrs) if a.startswith(word)]
                return self._apply(prefix, word, cands, " ")
        if hostish:
            known = sorted(self.game.state.known)
            cands = [h for h in known if h.startswith(word)]
            cands += [self.game.world.nodes[h].short for h in known
                      if self.game.world.nodes[h].short.startswith(word)
                      and self.game.world.nodes[h].short not in cands]
            return self._apply(prefix, word, sorted(set(cands)), " ")
        # paths
        w = word
        if w.startswith("~"):
            w = self.home_dir() + w[1:]
        dirpart, _, base = w.rpartition("/")
        lookup = dirpart if dirpart else ("/" if w.startswith("/") else ".")
        if w.startswith("/") and not dirpart:
            lookup = "/"
        node = self.fs.get(lookup, self.frame.cwd)
        if node is None or not node.is_dir:
            return text, []
        show_hidden = base.startswith(".")
        for name, child in sorted(node.children.items()):
            if name.startswith(base) and (show_hidden or not name.startswith(".")):
                cands.append(name + ("/" if child.is_dir else ""))
        word_dir = word[: len(word) - len(base)]
        new_text, shown = self._apply(prefix + word_dir, base, cands, "")
        if len(cands) == 1 and not cands[0].endswith("/"):
            new_text += " "
        return new_text, shown

    @staticmethod
    def _apply(prefix: str, word: str, cands: list[str], suffix: str):
        if not cands:
            return prefix + word, []
        if len(cands) == 1:
            return prefix + cands[0] + suffix, []
        common = cands[0]
        for c in cands[1:]:
            while not c.startswith(common):
                common = common[:-1]
        return prefix + common, cands
