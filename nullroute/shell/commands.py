"""All shell commands."""

from __future__ import annotations

import asyncio
import fnmatch
import posixpath
import random
import re

from ..game import clock, store, tutorial
from ..game.engine import Conn
from ..game.hosts import LAYER_DESC
from ..game.state import save as save_state
from ..game.vfs import Dir, File, FSError, human_size, mode_string, normpath
from ..game.vfs import allowed as vfs_allowed
from ..game.world import AGENCY, DROP, GATEWAY
from .core import ROOT, CmdSpec, Ctx, Shell, bar

_REG: list[CmdSpec] = []


def cmd(name: str, summary: str, usage: str = "", man: str = "", group: str = "files"):
    def deco(fn):
        _REG.append(CmdSpec(name, fn, summary, usage or name, man, group))
        return fn
    return deco


def register(shell: Shell) -> None:
    from . import cmd_admin, cmd_learn, cmd_net, cmd_proc  # noqa: F401 - registers commands
    for spec in _REG:
        shell.add(spec)
    from ..game import learning

    def after(line, pls, status):
        learning.observe(shell.game, shell, line, pls, status)
        for msg in tutorial.advance(shell.game):       # instant tutorial feedback
            shell.game.notify(msg, "tutorial")
    shell.observers.append(after)


def split_flags(args: list[str], known: str) -> tuple[set[str], list[str]]:
    """Split short flags like -la into a set; stop at '--'."""
    flags: set[str] = set()
    rest: list[str] = []
    end = False
    for a in args:
        if not end and a == "--":
            end = True
            continue
        if not end and a.startswith("-") and len(a) > 1 and not a[1:].isdigit():
            for ch in a[1:]:
                if ch in known:
                    flags.add(ch)
                else:
                    raise FSError(f"invalid option -- '{ch}'")
            continue
        rest.append(a)
    return flags, rest


def fmt_mtime(minutes: float) -> str:
    return clock.to_dt(minutes).strftime("%b %d %H:%M")


# ====================================================================== files
@cmd("pwd", "print the current directory")
async def c_pwd(ctx: Ctx) -> int:
    ctx.write(ctx.cwd)
    return 0


@cmd("cd", "change directory", "cd [dir]")
async def c_cd(ctx: Ctx) -> int:
    target = ctx.args[0] if ctx.args else ctx.shell.home_dir()
    if target == "-":
        target = getattr(ctx.shell, "_oldpwd", ctx.cwd)
    node = ctx.resolve(target, want="dir")
    ctx.need(node, "x", target)
    ctx.shell._oldpwd = ctx.cwd
    ctx.frame.cwd = node.path()
    return 0


@cmd("ls", "list directory contents", "ls [-lahtr1] [path...]",
     "Flags: -l long listing, -a show hidden files, -h human sizes,\n"
     "-t newest first, -r reverse the order, -1 one name per line.")
async def c_ls(ctx: Ctx) -> int:
    flags, paths = split_flags(ctx.args, "lah1Rtr")
    paths = paths or ["."]
    status = 0
    many = len(paths) > 1
    for i, p in enumerate(paths):
        try:
            node = ctx.resolve(p)
        except FSError as e:
            ctx.err(f"cannot access {e}")
            status = 2
            continue
        if not node.is_dir:
            _ls_entries(ctx, [(p, node)], flags)
            continue
        if not vfs_allowed(node, ctx.ident, "r"):
            ctx.err(f"cannot open directory '{p}': Permission denied")
            status = 2
            continue
        if many:
            ctx.write(f"{p}:")
        entries = []
        if "a" in flags:
            entries.append((".", node))
            entries.append(("..", node.parent or node))
        children = sorted(node.children.items())
        if "t" in flags:
            children.sort(key=lambda kv: -kv[1].mtime)
        if "r" in flags:
            children.reverse()
        for name, child in children:
            if name.startswith(".") and "a" not in flags:
                continue
            entries.append((name, child))
        _ls_entries(ctx, entries, flags)
        if many and i < len(paths) - 1:
            ctx.write("")
    return status


def _ls_entries(ctx: Ctx, entries, flags) -> None:
    if "l" in flags:
        total = sum(max(1, n.size // 1024) for _, n in entries)
        if len(entries) > 1:
            ctx.write(f"total {total}")
        ow = max([len(n.owner) for _, n in entries] + [4])
        gw = max([len(n.group) for _, n in entries] + [4])
        for name, n in entries:
            size = human_size(n.size) if "h" in flags else str(n.size)
            ctx.write(f"{mode_string(n)} 1 {n.owner:<{ow}} {n.group:<{gw}} {size:>8} "
                      f"{fmt_mtime(n.mtime)} {name}{'/' if n.is_dir else ''}",
                      "dir" if n.is_dir else None)
    elif "1" in flags or ctx.piped:     # like real ls: one per line into a pipe
        for name, n in entries:
            ctx.write(name, "dir" if n.is_dir else None)
    else:
        names = [name + ("/" if n.is_dir and name not in (".", "..") else "") for name, n in entries]
        if not names:
            return
        width = max(len(n) for n in names) + 2
        per_line = max(1, 78 // width)
        for i in range(0, len(names), per_line):
            ctx.write("".join(n.ljust(width) for n in names[i:i + per_line]).rstrip())


def _input_texts(ctx: Ctx, files: list[str]):
    """Yield (name, text) for each file, or stdin if no files."""
    if not files:
        yield "(standard input)", ctx.stdin or ""
        return
    for f in files:
        if f == "-":
            yield "(standard input)", ctx.stdin or ""
            continue
        node = ctx.resolve(f)
        if node.is_dir:
            raise FSError(f"{f}: Is a directory")
        ctx.need(node, "r", f)
        yield f, node.content


def _garble(node: File) -> str:
    rng = random.Random(node.size)
    chars = "@#$%&*!?^~<>|{}[]ÆØÅ¤§±÷ßµ¶"
    return "".join(rng.choice(chars) for _ in range(48))


@cmd("cat", "print files", "cat [file...]")
async def c_cat(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.write((ctx.stdin or "").rstrip("\n"))
        return 0
    status = 0
    for f in ctx.args:
        try:
            node = ctx.resolve(f, want="file")
            ctx.need(node, "r", f)
        except FSError as e:
            ctx.err(str(e))
            status = 1
            continue
        if node.binary:
            ctx.write(_garble(node), "dim")
            ctx.write(f"(binary data, {human_size(node.size)} - copy it, don't read it)", "dim")
        else:
            text = node.content.rstrip("\n")
            if text:
                ctx.write(text)
    return status


@cmd("less", "view a file (same as cat here)", "less file")
async def c_less(ctx: Ctx) -> int:
    return await c_cat(ctx)


def _n_arg(args: list[str], default: int = 10) -> tuple[int, list[str]]:
    n = default
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-n" and i + 1 < len(args):
            n = int(args[i + 1].lstrip("+"))
            i += 2
            continue
        if a.startswith("-n") and a[2:].isdigit():
            n = int(a[2:])
        elif a.startswith("-") and a[1:].isdigit():
            n = int(a[1:])
        else:
            rest.append(a)
        i += 1
    return n, rest


@cmd("head", "first lines of a file", "head [-n N] [file...]")
async def c_head(ctx: Ctx) -> int:
    n, files = _n_arg(ctx.args)
    for name, text in _input_texts(ctx, files):
        if len(files) > 1:
            ctx.write(f"==> {name} <==")
        for line in text.splitlines()[:n]:
            ctx.write(line)
    return 0


@cmd("tail", "last lines of a file (-f: keep following it)", "tail [-n N] [-f] [file...]",
     "Prints the last 10 lines (or -n N lines) of each file.\n"
     "-f / -F  follow: keep the file open and print new lines as they are\n"
     "         written. Stop with Ctrl+C, or run it in the background with &.")
async def c_tail(ctx: Ctx) -> int:
    args = [a for a in ctx.args if a not in ("-f", "-F", "--follow")]
    follow = len(args) != len(ctx.args)
    n, files = _n_arg(args)
    texts = list(_input_texts(ctx, files))
    for name, text in texts:
        if len(files) > 1:
            ctx.write(f"==> {name} <==")
        lines = text.splitlines()
        for line in lines[-n:] if n else []:
            ctx.write(line)
    if not follow or not files:
        return 0
    if ctx.piped:
        ctx.err("following into a pipe is not supported here, sorry")
        return 1
    # follow: poll the files for new content until cancelled
    fs = ctx.fs
    paths = [ctx.abspath(f) for f in files]
    seen = {p: len(fs.get(p).content) for p in paths}
    for p in paths:
        if p == "/var/log/syslog":
            ctx.game.state.flags.add("tail_f_syslog")
    ctx.game.award("tail_f")
    last_shown = paths[-1]
    while True:
        await asyncio.sleep(0.25)
        for p in paths:
            node = fs.get(p)
            if node is None or node.is_dir:
                continue
            size = len(node.content)
            if size < seen[p]:
                ctx.err(f"{p}: file truncated")
                seen[p] = 0
            if size > seen[p]:
                new = node.content[seen[p]:]
                seen[p] = size
                if len(paths) > 1 and p != last_shown:
                    ctx.write(f"\n==> {p} <==")
                    last_shown = p
                for line in new.rstrip("\n").split("\n"):
                    ctx.write(line)


@cmd("grep", "search for a pattern", "grep [-ivnrcl] pattern [file...]",
     "Flags: -i ignore case, -v invert, -n line numbers, -r recursive,\n"
     "-c count, -l list matching files. Patterns are regular expressions.")
async def c_grep(ctx: Ctx) -> int:
    flags, rest = split_flags(ctx.args, "ivnrRclEFsHho")
    if not rest:
        ctx.err("usage: grep [-ivnrcl] pattern [file...]")
        return 2
    pattern, files = rest[0], rest[1:]
    reflags = re.IGNORECASE if "i" in flags else 0
    try:
        rx = re.compile(re.escape(pattern) if "F" in flags else pattern, reflags)
    except re.error:
        rx = re.compile(re.escape(pattern), reflags)
    recursive = "r" in flags or "R" in flags
    targets: list[tuple[str, str]] = []
    if recursive:
        for f in files or ["."]:
            node = ctx.resolve(f)
            for n in walk_readable(ctx, node, "s" not in flags):
                if isinstance(n, File) and not n.binary:
                    disp = n.path()
                    if not f.startswith("/"):
                        rel = posixpath.relpath(n.path(), node.path() if node.is_dir else posixpath.dirname(node.path()))
                        disp = posixpath.join(f, rel) if node.is_dir else f
                    targets.append((disp, n.content))
    else:
        try:
            for name, text in _input_texts(ctx, files):
                targets.append((name, text))
        except FSError as e:
            if "s" not in flags:
                ctx.err(str(e))
            return 2
    show_name = (recursive or len(files) > 1 or "H" in flags) and "h" not in flags
    found = False
    for name, text in targets:
        count = 0
        for i, line in enumerate(text.splitlines(), 1):
            hit = bool(rx.search(line))
            if hit == ("v" in flags):
                continue
            count += 1
            found = True
            if "l" in flags or "c" in flags:
                continue
            out = line
            if "o" in flags and "v" not in flags:
                out = "\n".join(m.group(0) for m in rx.finditer(line))
            prefix = (f"{name}:" if show_name else "") + (f"{i}:" if "n" in flags else "")
            ctx.write(prefix + out, "match" if prefix else None)
        if "l" in flags and count:
            ctx.write(name)
        if "c" in flags:
            ctx.write(f"{name}:{count}" if show_name else str(count))
    return 0 if found else 1


@cmd("find", "search for files", "find [path] [-name pattern] [-type f|d]",
     "Example: find / -name '*.dat'   (quote the pattern!)")
async def c_find(ctx: Ctx) -> int:
    args = list(ctx.args)
    start = "."
    if args and not args[0].startswith("-"):
        start = args.pop(0)
    name_pat = None
    iname = False
    ftype = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-name", "-iname") and i + 1 < len(args):
            name_pat, iname = args[i + 1], a == "-iname"
            i += 2
        elif a == "-type" and i + 1 < len(args):
            ftype = args[i + 1]
            i += 2
        else:
            ctx.err(f"unknown predicate `{a}'")
            return 1
    root = ctx.resolve(start)
    base = root.path()
    for n in walk_readable(ctx, root, True, files_need_read=False):
        if ftype == "f" and n.is_dir or ftype == "d" and not n.is_dir:
            continue
        if name_pat:
            nm = n.name if n is not ctx.fs.root else "/"
            if iname:
                if not fnmatch.fnmatch(nm.lower(), name_pat.lower()):
                    continue
            elif not fnmatch.fnmatchcase(nm, name_pat):
                continue
        p = n.path()
        if not start.startswith("/"):
            rel = posixpath.relpath(p, base)
            p = start if rel == "." else posixpath.join(start, rel)
        ctx.write(p)
    return 0


def walk_readable(ctx: Ctx, start, report: bool, files_need_read: bool = True):
    """Like fs.walk, but skips what the current user may not read (and says so)."""
    def rel(n):
        return n.path()
    if start.is_dir:
        if not (vfs_allowed(start, ctx.ident, "r") and vfs_allowed(start, ctx.ident, "x")):
            if report:
                ctx.err(f"'{rel(start)}': Permission denied")
            return
        yield start
        for child in list(start.children.values()):
            yield from walk_readable(ctx, child, report, files_need_read)
    else:
        if files_need_read and not vfs_allowed(start, ctx.ident, "r"):
            if report:
                ctx.err(f"{rel(start)}: Permission denied")
            return
        yield start


def _own(ctx: Ctx, node) -> None:
    """New copies belong to whoever made them."""
    for n in ctx.fs.walk(node):
        n.owner = n.group = ctx.user


def _check_disk(ctx: Ctx, node_name: str, extra: int) -> None:
    if node_name != GATEWAY:
        return
    fs = ctx.game.world.nodes[GATEWAY].fs
    cap = store.DISK_SIZE[ctx.game.state.hw["disk"]]
    if fs.used_bytes() + extra > cap:
        raise FSError("No space left on device (buy more storage)")


def _copy_into(ctx: Ctx, src_node, dst: str, move: bool = False) -> None:
    fs = ctx.fs
    full = ctx.abspath(dst)
    target = fs.get(full)
    if isinstance(target, Dir):
        parent, name = target, src_node.name
    else:
        parent, name = fs.parent_of(full, "/", ctx.ident)
    ctx.need(parent, "w", dst)
    existing = parent.children.get(name)
    if isinstance(existing, File) and not move:
        ctx.need(existing, "w", dst)
    if move:
        if not ctx.can_delete(src_node):
            raise FSError(f"cannot move '{src_node.name}': Permission denied")
    else:
        for n in ctx.fs.walk(src_node):
            ctx.need(n, "r", n.path())
    if src_node.is_dir:
        cur = parent
        while cur is not None:
            if cur is src_node:
                raise FSError(f"cannot copy a directory into itself")
            cur = cur.parent
    if not move:
        size = sum(n.size for n in fs.walk(src_node) if isinstance(n, File))
        _check_disk(ctx, ctx.frame.node, size)
    if move:
        if src_node.parent is not None:
            del src_node.parent.children[src_node.name]
        src_node.name = name
        parent.add(src_node)
    else:
        copy = src_node.clone(name)
        copy.mtime = ctx.game.now
        parent.add(copy)
        _own(ctx, copy)


@cmd("cp", "copy files", "cp [-r] source... dest")
async def c_cp(ctx: Ctx) -> int:
    flags, args = split_flags(ctx.args, "rRfvaip")
    if len(args) < 2:
        ctx.err("missing destination file operand")
        return 1
    *srcs, dst = args
    status = 0
    for s in srcs:
        try:
            node = ctx.resolve(s)
            if node.is_dir and not ({"r", "R", "a"} & flags):
                ctx.err(f"-r not specified; omitting directory '{s}'")
                status = 1
                continue
            _copy_into(ctx, node, dst)
        except FSError as e:
            ctx.err(str(e))
            status = 1
    return status


@cmd("mv", "move or rename files", "mv source... dest")
async def c_mv(ctx: Ctx) -> int:
    flags, args = split_flags(ctx.args, "fvin")
    if len(args) < 2:
        ctx.err("missing destination file operand")
        return 1
    *srcs, dst = args
    status = 0
    for s in srcs:
        try:
            node = ctx.resolve(s)
            if node is ctx.fs.root:
                raise FSError("cannot move '/'")
            _copy_into(ctx, node, dst, move=True)
        except FSError as e:
            ctx.err(str(e))
            status = 1
    return status


@cmd("rm", "remove files", "rm [-rf] file...")
async def c_rm(ctx: Ctx) -> int:
    flags, args = split_flags(ctx.args, "rRfvid")
    if not args:
        ctx.err("missing operand")
        return 1
    status = 0
    for a in args:
        try:
            node = ctx.resolve(a)
        except FSError as e:
            if "f" not in flags:
                ctx.err(f"cannot remove {e}")
                status = 1
            continue
        if node is ctx.fs.root or node.path() in ("/bin", "/etc", "/home"):
            ctx.err(f"refusing to remove '{a}' - the node would crash and everyone would notice")
            status = 1
            continue
        if node.is_dir and not ({"r", "R"} & flags):
            ctx.err(f"cannot remove '{a}': Is a directory")
            status = 1
            continue
        if ctx.frame.node == GATEWAY and node.path() in (ctx.game.state.home, "/usr", "/usr/bin",
                                                         "/var", "/root", "/tmp"):
            ctx.err(f"refusing to remove '{a}' - your gateway needs it")
            status = 1
            continue
        if not ctx.can_delete(node):
            ctx.err(f"cannot remove '{a}': Permission denied")
            status = 1
            continue
        if node.parent is not None:
            del node.parent.children[node.name]
        if "v" in flags:
            ctx.write(f"removed '{a}'")
    return status


@cmd("mkdir", "create directories", "mkdir [-p] dir...")
async def c_mkdir(ctx: Ctx) -> int:
    flags, args = split_flags(ctx.args, "pv")
    status = 0
    for a in args:
        full = ctx.abspath(a)
        if ctx.fs.get(full) is not None:
            if "p" not in flags:
                ctx.err(f"cannot create directory '{a}': File exists")
                status = 1
            continue
        try:
            if "p" in flags:
                cur = ctx.fs.root
                for part in full.strip("/").split("/"):
                    nxt = cur.children.get(part)
                    if nxt is None:
                        ctx.need(cur, "w", a)
                        nxt = cur.add(ctx.new_dir(part))
                    if not nxt.is_dir:
                        raise FSError(f"cannot create directory '{a}': Not a directory")
                    cur = nxt
            else:
                parent, name = ctx.parent_for_write(a)
                parent.add(ctx.new_dir(name))
        except FSError as e:
            ctx.err(f"cannot create directory '{a}': {str(e).split(': ')[-1]}")
            status = 1
    return status


@cmd("rmdir", "remove empty directories", "rmdir dir...")
async def c_rmdir(ctx: Ctx) -> int:
    for a in ctx.args:
        node = ctx.resolve(a, want="dir")
        if node.children:
            ctx.err(f"failed to remove '{a}': Directory not empty")
            return 1
        if not ctx.can_delete(node):
            ctx.err(f"failed to remove '{a}': Permission denied")
            return 1
        del node.parent.children[node.name]
    return 0


@cmd("touch", "create empty files", "touch file...")
async def c_touch(ctx: Ctx) -> int:
    for a in ctx.args:
        full = ctx.abspath(a)
        node = ctx.fs.get(full)
        if node is not None:
            if not (vfs_allowed(node, ctx.ident, "w") or node.owner == ctx.user):
                ctx.err(f"cannot touch '{a}': Permission denied")
                return 1
            node.mtime = ctx.game.now
            continue
        try:
            parent, name = ctx.parent_for_write(a)
        except FSError as e:
            ctx.err(f"cannot touch '{a}': {str(e).split(': ')[-1]}")
            return 1
        parent.add(ctx.new_file(name))
    return 0


@cmd("echo", "print text", "echo [-n] text...")
async def c_echo(ctx: Ctx) -> int:
    args = ctx.args
    if args and args[0] == "-n":
        args = args[1:]
    ctx.write(" ".join(args))
    return 0


@cmd("wc", "count lines, words and bytes", "wc [-lwc] [file...]")
async def c_wc(ctx: Ctx) -> int:
    flags, files = split_flags(ctx.args, "lwcm")
    for name, text in _input_texts(ctx, files):
        counts = {"l": text.count("\n"), "w": len(text.split()), "c": len(text.encode())}
        keys = [k for k in "lwc" if k in flags] or ["l", "w", "c"]
        out = " ".join(f"{counts[k]:>7}" for k in keys)
        ctx.write(out + (f" {name}" if files else ""))
    return 0


@cmd("sort", "sort lines", "sort [-rnu] [file...]")
async def c_sort(ctx: Ctx) -> int:
    flags, files = split_flags(ctx.args, "rnuf")
    lines = []
    for _, text in _input_texts(ctx, files):
        lines.extend(text.splitlines())
    if "n" in flags:
        def key(s):
            m = re.match(r"\s*(-?\d+(\.\d+)?)", s)
            return float(m.group(1)) if m else 0.0
        lines.sort(key=key, reverse="r" in flags)
    else:
        lines.sort(key=(str.lower if "f" in flags else None), reverse="r" in flags)
    if "u" in flags:
        seen = set()
        lines = [l for l in lines if not (l in seen or seen.add(l))]
    for l in lines:
        ctx.write(l)
    return 0


@cmd("uniq", "drop repeated lines", "uniq [-c] [file]")
async def c_uniq(ctx: Ctx) -> int:
    flags, files = split_flags(ctx.args, "cd")
    lines = []
    for _, text in _input_texts(ctx, files):
        lines.extend(text.splitlines())
    groups: list[list] = []
    for l in lines:
        if groups and groups[-1][0] == l:
            groups[-1][1] += 1
        else:
            groups.append([l, 1])
    for l, n in groups:
        if "d" in flags and n < 2:
            continue
        ctx.write(f"{n:>7} {l}" if "c" in flags else l)
    return 0


@cmd("file", "guess a file's type", "file file...")
async def c_file(ctx: Ctx) -> int:
    for a in ctx.args:
        node = ctx.resolve(a)
        if node.is_dir:
            kind = "directory"
        elif node.binary:
            kind = "data (encrypted)" if node.name.endswith(".dat") else "data"
        elif node.name.endswith(".html"):
            kind = "HTML document, ASCII text"
        else:
            kind = "ASCII text" if node.content else "empty"
        ctx.write(f"{a}: {kind}")
    return 0


@cmd("du", "disk usage", "du [-sh] [path...]")
async def c_du(ctx: Ctx) -> int:
    flags, paths = split_flags(ctx.args, "shac")
    for p in paths or ["."]:
        node = ctx.resolve(p)
        total = sum(n.size for n in ctx.fs.walk(node) if isinstance(n, File))
        ctx.write(f"{human_size(total) if 'h' in flags else total // 1024}\t{p}")
    return 0


@cmd("df", "free space on your gateway", "df [-h]")
async def c_df(ctx: Ctx) -> int:
    fs = ctx.fs
    cap = store.DISK_SIZE[ctx.game.state.hw["disk"]] if ctx.at_gateway else 500_000_000_000
    used = fs.used_bytes()
    pct = int(used * 100 / cap)
    ctx.write("Filesystem      Size  Used Avail Use% Mounted on")
    ctx.write(f"/dev/nvme0n1p1 {human_size(cap):>5} {human_size(used):>5} "
              f"{human_size(cap - used):>5} {pct:>3}% /")
    return 0


@cmd("tree", "show a directory tree", "tree [path]")
async def c_tree(ctx: Ctx) -> int:
    start = ctx.args[0] if ctx.args else "."
    root = ctx.resolve(start, want="dir")
    ctx.write(start, "dir")
    counts = [0, 0]

    def walk(d, prefix):
        items = sorted((n, c) for n, c in d.children.items() if not n.startswith("."))
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            ctx.write(prefix + ("└── " if last else "├── ") + name, "dir" if child.is_dir else None)
            if child.is_dir:
                counts[0] += 1
                walk(child, prefix + ("    " if last else "│   "))
            else:
                counts[1] += 1
    walk(root, "")
    ctx.write(f"\n{counts[0]} directories, {counts[1]} files")
    return 0


@cmd("nano", "edit a text file", "nano [+LINE] [file]",
     "A small GNU nano. The two bottom lines list the shortcuts:\n"
     "  ^ means Ctrl, M- means Alt.\n"
     "  ^O write out (save, asks for a file name)   ^S save without asking\n"
     "  ^X exit (asks to save if the file changed)  ^G help\n"
     "  ^W search, M-W search again                 ^\\ search and replace\n"
     "  ^K cut line, ^U paste                       ^C show cursor position\n"
     "  ^_ go to line                               M-U undo, M-E redo\n"
     "'nano +12 file' opens the file with the cursor on line 12.")
async def c_nano(ctx: Ctx) -> int:
    args = list(ctx.args)
    start_line = 0
    if args and args[0].startswith("+"):
        try:
            start_line = int(args.pop(0)[1:].split(",")[0])
        except ValueError:
            start_line = 0
    display = args[0] if args else ""
    content = ""
    new_file = True
    if display:
        node = ctx.fs.get(ctx.abspath(display))
        if node is not None and node.is_dir:
            ctx.err(f"\"{display}\" is a directory")
            return 1
        if isinstance(node, File):
            if node.binary:
                ctx.err(f"\"{display}\" is a binary file - nano would only show garbage")
                return 1
            if not vfs_allowed(node, ctx.ident, "r"):
                ctx.err(f"\"{display}\": Permission denied (try: sudo nano {display})")
                return 1
            content, new_file = node.content, False
    frame = ctx.frame                     # stays valid even if we get traced
    ident = ctx.ident

    def write(name: str, text: str) -> str | None:
        fs = ctx.game.world.nodes[frame.node].fs
        full = normpath(name, frame.cwd)
        target = fs.get(full)
        if target is not None and target.is_dir:
            return "Is a directory"
        if isinstance(target, File):
            if not vfs_allowed(target, ident, "w"):
                return "Permission denied"
            target.content = text
            target.binary = False
            target.fake_size = None
            target.mtime = ctx.game.now
            ctx.game.award("nano_save")
            return None
        try:
            parent, fname = fs.parent_of(full, "/", ident)
        except FSError:
            return "No such file or directory"
        if not vfs_allowed(parent, ident, "w"):
            return "Permission denied"
        parent.add(File(fname, text, owner=ident.user, group=ident.user, mtime=ctx.game.now))
        ctx.game.award("nano_save")
        return None

    def read(name: str):
        fs = ctx.game.world.nodes[frame.node].fs
        node = fs.get(normpath(name, frame.cwd))
        if node is None:
            return None, f"\"{name}\" not found"
        if node.is_dir:
            return None, f"\"{name}\" is a directory"
        if node.binary:
            return None, f"\"{name}\" is a binary file"
        if not vfs_allowed(node, ident, "r"):
            return None, f"\"{name}\": Permission denied"
        return node.content, None

    await ctx.ui.open_view("editor", path=display, content=content, new_file=new_file,
                           write=write, read=read, start_line=start_line)
    return 0


# ====================================================================== system
@cmd("clear", "clear the screen", group="system")
async def c_clear(ctx: Ctx) -> int:
    ctx.ui.clear()
    return 0


@cmd("whoami", "print your user name", group="admin")
async def c_whoami(ctx: Ctx) -> int:
    ctx.write(ctx.user)
    return 0


@cmd("hostname", "print the node's name", group="system")
async def c_hostname(ctx: Ctx) -> int:
    ctx.write(ctx.game.world.nodes[ctx.frame.node].hostname)
    return 0


@cmd("date", "print the date and time", group="system")
async def c_date(ctx: Ctx) -> int:
    ctx.write(clock.fmt_date(ctx.game.now))
    return 0


@cmd("history", "show command history", "history [-c]", group="system")
async def c_history(ctx: Ctx) -> int:
    if ctx.args and ctx.args[0] == "-c":
        ctx.shell.history.clear()
        return 0
    for i, line in enumerate(ctx.shell.history[-100:], 1):
        ctx.write(f"{i:>5}  {line}")
    return 0


@cmd("split", "open another terminal (also Ctrl+N)", "split",
     "Opens a new terminal next to this one (up to four). Alt+←/→ or F2\n"
     "switches between them, Alt+1..4 jumps straight to one. 'exit' or\n"
     "Ctrl+D on your gateway closes a terminal.", group="system")
async def c_split(ctx: Ctx) -> int:
    ctx.ui.new_terminal()
    return 0


@cmd("exit", "close the connection, or this terminal when on your gateway", group="network")
async def c_exit(ctx: Ctx) -> int:
    if ctx.background:
        return 0
    f = ctx.shell.pop_frame()
    if f is None:                 # logging out of the gateway closes this terminal
        ctx.write("logout")
        ctx.ui.logout()
        return 0
    if f.conn is None:            # leaving a local root shell (sudo -i / su)
        ctx.write("logout")
        return 0
    node = ctx.game.world.nodes[f.node]
    ctx.write(f"Connection to {node.hostname} closed.")
    if node.footprint > 0 and node.kind != "sandbox":
        ctx.write(f"Warning: you left a footprint ({int(node.footprint)}%) on {node.hostname}.", "warn")
    if ctx.shell.frame.node == GATEWAY and f"scrub:{tutorial_sandbox()}" in ctx.game.state.flags:
        ctx.game.flag("home_after_scrub")
    return 0


def tutorial_sandbox() -> str:
    from ..game.world import SANDBOX
    return SANDBOX


@cmd("man", "show the manual for a command", "man command", group="system")
async def c_man(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.write("What manual page do you want? Try 'help' for a list.")
        return 1
    name = ctx.shell.aliases.get(ctx.args[0], ctx.args[0]).split()[0]
    spec = ctx.shell.commands.get(name)
    if not spec:
        ctx.err(f"No manual entry for {ctx.args[0]}")
        return 16
    from .manpages import EXAMPLES, SEE_ALSO
    ctx.write(f"{spec.name.upper()}(1)              User Commands              {spec.name.upper()}(1)",
              "title")
    ctx.write("")
    ctx.write("NAME", "title")
    ctx.write(f"       {spec.name} - {spec.summary}\n")
    ctx.write("SYNOPSIS", "title")
    ctx.write(f"       {spec.usage}\n")
    if spec.man:
        ctx.write("DESCRIPTION", "title")
        for line in spec.man.splitlines():
            ctx.write("       " + line)
        ctx.write("")
    if name in EXAMPLES:
        ctx.write("EXAMPLES", "title")
        for line in EXAMPLES[name].strip("\n").splitlines():
            ctx.write("       " + line, "accent" if line and not line.startswith(" ") else None)
        ctx.write("")
    if name in SEE_ALSO:
        ctx.write("SEE ALSO", "title")
        ctx.write("       " + ", ".join(f"{s}(1)" for s in SEE_ALSO[name]))
    s = ctx.game.state
    s.flags.add(f"man:{name}")
    if sum(1 for f in s.flags if f.startswith("man:")) >= 10:
        ctx.game.award("man10")
    return 0


HELP_GROUPS = {"game": "Runner tools", "network": "Network", "files": "Files & text",
               "admin": "Users, permissions & packages", "process": "Processes & jobs",
               "learn": "Learning", "system": "System"}


@cmd("help", "list commands", "help [group]", group="system")
async def c_help(ctx: Ctx) -> int:
    for key, title in HELP_GROUPS.items():
        specs = sorted((s for s in ctx.shell.commands.values() if s.group == key),
                       key=lambda s: s.name)
        if not specs:
            continue
        ctx.write(title, "title")
        for s in specs:
            ctx.write(f"  {s.name:<11} {s.summary}")
    ctx.write("\nType 'man <command>' for details and examples. Tab completes commands,\n"
              "files and hosts. New to Linux? Try 'learn'.", "dim")
    return 0


@cmd("neofetch", "show your gateway specs", group="system")
async def c_neofetch(ctx: Ctx) -> int:
    s = ctx.game.state
    cpu = {1: "Dual-core 2.4 GHz", 2: "Quad-core 4.2 GHz", 3: "Octa-core 5.0 GHz",
           4: "Quantum co-processor"}[s.hw["cpu"]]
    nic = {1: "1 Gbit copper", 2: "10 Gbit fibre", 3: "Optical backbone tap"}[s.hw["nic"]]
    disk = human_size(store.DISK_SIZE[s.hw["disk"]])
    used = human_size(ctx.game.world.nodes[GATEWAY].fs.used_bytes())
    art = ["   _  __     ____  ", "  / |/ /_ __/ / /  ", " /    / // / / /   ",
           "/_/|_/\\_,_/_/_/    ", "   NULLROUTE OS    ", "", "", ""]
    info = [f"{s.handle}@gateway", "-" * (len(s.handle) + 8), "OS: NullrouteOS 2.1 x86_64",
            f"CPU: {cpu}", f"Network: {nic}", f"Disk: {used} / {disk}",
            f"Rating: {s.rating_title} ({s.rating})", f"Credits: ¢{s.money:,}"]
    for a, b in zip(art, info):
        ctx.write(f"{a:<20} {b}", "accent")
    return 0


# ====================================================================== network
def _base_path(ctx: Ctx) -> list[str]:
    if ctx.at_gateway:
        return [GATEWAY] + list(ctx.game.state.route)
    return list(ctx.frame.path)


def _reach(ctx: Ctx, name: str):
    """Resolve a node and work out the route to it. Returns (node, path)."""
    node = ctx.game.node(name)
    if node is None:
        raise FSError(f"Could not resolve hostname {name}: Name or service not known")
    if node.parent and ctx.frame.node != node.parent:
        raise FSError(f"connect to {node.hostname}: Connection timed out\n"
                      f"  ({node.hostname} only accepts connections from {node.parent})")
    path = _base_path(ctx)
    if node.hostname in path:
        path = path[: path.index(node.hostname)]
    return node, path + [node.hostname]


@cmd("ssh", "connect to a node", "ssh host",
     "Connect to a node. Corporate nodes must be breached first.\n"
     "From your gateway, the connection follows your route (see 'route').\n"
     f"'ssh {AGENCY}' opens the agency BBS.", group="network")
async def c_ssh(ctx: Ctx) -> int:
    args = [a for a in ctx.args if not a.startswith("-")]
    if not args:
        ctx.err("usage: ssh host")
        return 255
    name = args[0].split("@", 1)[-1]
    node = ctx.game.node(name)
    if node is None:
        ctx.err(f"Could not resolve hostname {name}: Name or service not known")
        return 255
    if node.kind == "agency":
        if not ctx.at_gateway:
            ctx.err("The agency only accepts connections from your own gateway.")
            return 255
        ctx.game.flag("bbs")
        await ctx.ui.open_view("bbs")
        return 0
    if node.kind == "drop":
        ctx.err(f"{DROP} accepts uploads only. Use scp.")
        return 255
    if node.kind == "relay":
        ctx.err(f"{node.hostname} only forwards traffic. Add it to your route: route add {node.short}")
        return 255
    if node.kind == "gateway":
        ctx.err("That's your own gateway. Use 'exit' to go back.")
        return 255
    if any(f.node == node.hostname for f in ctx.shell.frames):
        ctx.err(f"You are already connected to {node.hostname}.")
        return 255
    try:
        node, path = _reach(ctx, name)
    except FSError as e:
        ctx.err(str(e))
        return 255
    ctx.game.state.known.add(node.hostname)
    if not node.is_open(ctx.game.now):
        layer = node.layers[0].kind.upper()
        ctx.err(f"connect to {node.hostname} port 22: Connection refused by ICE ({layer})")
        ctx.write(f"  Breach it first: breach {node.short}", "dim")
        return 255
    hops = len(path) - 2
    ctx.write(f"Routing via {hops} hop{'s' if hops != 1 else ''}: "
              + " -> ".join(ctx.game.world.nodes[h].short for h in path), "dim")
    await ctx.sleep(0.4 + 0.15 * hops, f"Connecting to {node.hostname}")
    conn = ctx.game.open_conn(Conn(node.hostname, path, "shell"))
    from .core import Frame
    ctx.shell.frames.append(Frame(node.hostname, "/", conn, user="root"))
    if node.trace_active:
        ctx.write("The node is still tracing you. Be quick.", "warn")
    if node.fs and node.fs.get("/etc/motd"):
        ctx.write(node.fs.get("/etc/motd").content.rstrip("\n"), "accent")
    ctx.write(f"Connected to {node.hostname} ({node.ip}).")
    ctx.game.flag(f"ssh:{node.hostname}")
    return 0


def _spec(arg: str) -> tuple[str | None, str]:
    if ":" in arg:
        host, path = arg.split(":", 1)
        if "/" not in host:
            return host.split("@", 1)[-1], path
    return None, arg


@cmd("scp", "copy files between nodes", "scp [-r] source dest",
     "Either side may be host:path. Examples:\n"
     f"  scp report.dat {DROP}:/drop/C001/     upload to the drop box\n"
     "  scp gateway:~/contracts/C002/x.dat /data/   (run on the target)\n"
     "  scp www.acme.corp:/data/x.dat ~/downloads/   (run on your gateway)\n"
     "Transfers take time depending on your network hardware.", group="network")
async def c_scp(ctx: Ctx) -> int:
    flags, args = split_flags(ctx.args, "rpqvC")
    if len(args) != 2:
        ctx.err("usage: scp [-r] source destination")
        return 1
    world = ctx.game.world
    (sh, sp), (dh, dp) = _spec(args[0]), _spec(args[1])
    conns: list[Conn] = []

    def endpoint(host: str | None, path: str):
        if host is None:
            node = world.nodes[ctx.frame.node]
            return node, ctx.abspath(path)
        node = ctx.game.node(host)
        if node is None:
            raise FSError(f"Could not resolve hostname {host}")
        home = ctx.game.state.home if node.kind == "gateway" else "/"
        if not path:
            path = home
        if path == "~" or path.startswith("~/"):
            path = home + path[1:]
        if node.hostname == ctx.frame.node:
            return node, ctx.abspath(path)
        if node.kind in ("drop", "gateway"):
            return node, normpath(path, home)
        if node.kind in ("relay", "agency") or node.fs is None:
            raise FSError(f"{node.hostname}: connection refused (no file service)")
        _, route = _reach(ctx, host)
        if not node.is_open(ctx.game.now):
            raise FSError(f"connect to {node.hostname} port 22: Connection refused by ICE")
        conns.append(Conn(node.hostname, route, "transfer"))
        return node, normpath(path, home)

    def ident_for(node):
        """You are yourself on your gateway (or root under sudo), root elsewhere."""
        if node.kind != "gateway":
            return ROOT
        return ctx.ident if ctx.at_gateway else ctx.shell.identity(ctx.shell.handle)

    try:
        src_node, src_path = endpoint(sh, sp)
        dst_node, dst_path = endpoint(dh, dp)
        src_id, dst_id = ident_for(src_node), ident_for(dst_node)
        src = src_node.fs.resolve(src_path, "/", src_id)
        if src.is_dir and "r" not in flags:
            raise FSError(f"{args[0]}: not a regular file")
        for n in src_node.fs.walk(src):
            if not vfs_allowed(n, src_id, "r"):
                raise FSError(f"{n.path()}: Permission denied")
        dfs = dst_node.fs
        if dst_node.kind == "drop" and (dp.endswith("/") or not posixpath.splitext(dst_path)[1]):
            dfs.mkdir_p(dst_path)
        target = dfs.get(dst_path)
        if isinstance(target, Dir):
            parent, name = target, src.name
        else:
            parent, name = dfs.parent_of(dst_path, "/", dst_id)
        if not vfs_allowed(parent, dst_id, "w"):
            raise FSError(f"{args[1]}: Permission denied")
        size = sum(n.size for n in src_node.fs.walk(src) if isinstance(n, File))
        if dst_node.kind == "gateway":
            cap = store.DISK_SIZE[ctx.game.state.hw["disk"]]
            if dfs.used_bytes() + size > cap:
                raise FSError("No space left on device (buy more storage)")
    except FSError as e:
        ctx.err(str(e))
        return 1
    for c in conns:
        ctx.game.open_conn(c)
    try:
        speed = store.NIC_SPEED[ctx.game.state.hw["nic"]] * 1_000_000
        seconds = max(0.4, min(90.0, size / speed))
        label = src.name[:28]

        def render(frac: float) -> str:
            done = int(size * frac)
            secs = int(seconds * frac)
            return (f"{label:<28} {int(frac * 100):3d}% {human_size(done):>6}  "
                    f"{human_size(int(speed))}/s  00:{secs:02d} {bar(frac, 16)}")
        await ctx.sleep(seconds, render=render)
        copy = src.clone(name)
        copy.mtime = ctx.game.now
        parent.add(copy)
        for n in dfs.walk(copy):
            n.owner = n.group = dst_id.user
        ctx.write(f"{label:<28} 100% {human_size(size):>6}  {human_size(int(speed))}/s  "
                  f"00:{int(seconds):02d}")
    finally:
        for c in conns:
            ctx.game.close_conn(c)
    return 0


# ====================================================================== runner tools
@cmd("route", "manage your bounce route", "route [add|del|clear] [relay]",
     "Your route is the list of public relays your connections bounce through\n"
     "when you start them from your gateway. Every hop makes a trace slower.\n"
     "  route                 show the route\n"
     "  route add osaka       append a relay\n"
     "  route del osaka       remove a relay (or: route del 2)\n"
     "  route clear           remove all relays\n"
     "See 'cat ~/relays.txt' for relays, or use 'map'.", group="game")
async def c_route(ctx: Ctx) -> int:
    s = ctx.game.state
    world = ctx.game.world
    if not ctx.args:
        if not s.route:
            ctx.write("Route is empty: connections go DIRECT from your gateway. (route add <relay>)", "warn")
            return 0
        ctx.write(f"Route ({len(s.route)} hop{'s' if len(s.route) != 1 else ''}):")
        ctx.write(f"  gateway ({world.nodes[GATEWAY].ip})")
        for i, h in enumerate(s.route, 1):
            n = world.nodes[h]
            ctx.write(f"  {i}. {n.hostname:<22} {n.ip:<16} {n.title}")
        ctx.write("  -> target")
        return 0
    sub, rest = ctx.args[0], ctx.args[1:]
    if sub == "add":
        if not rest:
            ctx.err("usage: route add <relay>")
            return 1
        for name in rest:
            node = ctx.game.node(name) or ctx.game.node(name + ".relay")
            if node is None or not node.public:
                ctx.err(f"{name}: not a public relay")
                return 1
            if node.hostname in s.route:
                ctx.err(f"{node.hostname} is already in your route")
                return 1
            if len(s.route) >= 8:
                ctx.err("route is full (max 8 hops)")
                return 1
            s.route.append(node.hostname)
            ctx.write(f"Added {node.hostname} (hop {len(s.route)})")
        ctx.game.flag("route")
        return 0
    if sub in ("del", "rm", "remove"):
        for name in rest:
            if name.isdigit() and 1 <= int(name) <= len(s.route):
                ctx.write(f"Removed {s.route.pop(int(name) - 1)}")
                continue
            node = ctx.game.node(name) or ctx.game.node(name + ".relay")
            if node and node.hostname in s.route:
                s.route.remove(node.hostname)
                ctx.write(f"Removed {node.hostname}")
            else:
                ctx.err(f"{name}: not in route")
        return 0
    if sub == "clear":
        s.route.clear()
        ctx.write("Route cleared.")
        return 0
    ctx.err(f"unknown subcommand '{sub}' (add, del, clear)")
    return 1


@cmd("probe", "inspect a node's ICE", "probe host",
     "Shows a node's ICE layers and whether your programs can break them.", group="game")
async def c_probe(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.err("usage: probe host")
        return 1
    node = ctx.game.node(ctx.args[0])
    if node is None:
        ctx.err(f"Could not resolve hostname {ctx.args[0]}")
        return 1
    await ctx.sleep(1.2, f"Probing {node.hostname}")
    ctx.game.state.known.add(node.hostname)
    s = ctx.game.state
    ctx.write(f"{node.hostname}  ({node.ip})", "title")
    ctx.write(f"  Type:     {node.title}")
    if node.corp:
        ctx.write(f"  Owner:    {ctx.game.world.corps[node.corp].name}")
    if node.parent:
        ctx.write(f"  Access:   only reachable from {node.parent}")
        s.known.add(node.parent)
    if s.sw.get("probe", 1) >= 2 and node.layers:
        path = _base_path(ctx) + [node.hostname]
        ctx.write(f"  Security: {'★' * node.sec}{'☆' * (5 - node.sec)}")
        ctx.write(f"  Trace:    ~{int(ctx.game.trace_seconds(node, path))}s with your current route")
    if not node.layers:
        ctx.write("  ICE:      none")
        ctx.game.flag(f"probe:{node.hostname}")
        return 0
    ctx.write("  ICE layers:")
    total = 0.0
    ok = True
    for kind, strength, ver, secs in ctx.game.breach_plan(node):
        prog = {"firewall": "bypass", "cipher": "decrypt", "gatekeeper": "spoof"}[kind]
        desc = LAYER_DESC[kind]
        if secs < 0:
            ok = False
            why = f"need {prog} v{1 if strength <= 2 else 2 if strength <= 4 else 3}"
            ctx.write(f"    {desc}  strength {strength}   ✗ {why}", "error")
        else:
            total += secs
            ctx.write(f"    {desc}  strength {strength}   ✓ {prog} v{ver} (~{secs:.0f}s)", "good")
    if ok:
        ctx.write(f"  Breach time: ~{total:.0f}s.  Run: breach {node.short}", "good")
    else:
        ctx.write("  You can't breach this yet. Upgrade at the agency store.", "warn")
    if node.is_open(ctx.game.now):
        ctx.write("  Status:   ICE is DOWN (breached) - you can ssh in", "good")
    ctx.game.flag(f"probe:{node.hostname}")
    return 0


@cmd("breach", "break a node's ICE", "breach host",
     "Runs your breach programs (bypass, decrypt, spoof) against each ICE\n"
     "layer in turn. The node starts tracing you as soon as you begin.\n"
     "When all layers are down the node stays open for a while: ssh in.", group="game")
async def c_breach(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.err("usage: breach host")
        return 1
    try:
        node, path = _reach(ctx, ctx.args[0])
    except FSError as e:
        ctx.err(str(e))
        return 1
    if not node.layers:
        ctx.write(f"{node.hostname} has no ICE.")
        return 0
    if node.is_open(ctx.game.now):
        ctx.write(f"{node.hostname} is already open. ssh {node.short}")
        return 0
    plan = ctx.game.breach_plan(node)
    missing = [(k, st) for k, st, v, secs in plan if secs < 0]
    if missing:
        for k, st in missing:
            prog = {"firewall": "bypass", "cipher": "decrypt", "gatekeeper": "spoof"}[k]
            ctx.err(f"{k.upper()} (strength {st}): your {prog} can't break it")
        ctx.write("Probe the node and upgrade at the agency store.", "dim")
        return 1
    ctx.game.state.known.add(node.hostname)
    conn = ctx.game.open_conn(Conn(node.hostname, path, "breach"))
    try:
        ctx.game.start_trace(node, "breach detected")
        for kind, strength, ver, secs in plan:
            prog = {"firewall": "bypass", "cipher": "decrypt", "gatekeeper": "spoof"}[kind]
            await ctx.sleep(secs, f"{kind.upper():<10} {prog} v{ver}")
            ctx.write(f"  {kind.upper():<10} strength {strength} .... BROKEN", "good")
    finally:
        ctx.game.close_conn(conn)
    ctx.game.breached(node, len(path) - 2)
    ctx.write(f"ICE down. {node.hostname} is open - connect with: ssh {node.short}", "good")
    return 0


@cmd("scrub", "remove your footprint from this node", "scrub",
     "Run on a node you are connected to. Erases the evidence of your visit\n"
     "so the owner has nothing to follow when they review the node later.", group="game")
async def c_scrub(ctx: Ctx) -> int:
    if ctx.at_gateway:
        ctx.write("Nothing to scrub on your own gateway. Run this on a target node.")
        return 1
    node = ctx.game.world.nodes[ctx.frame.node]
    if node.footprint <= 0:
        ctx.write("No footprint here. You're clean.")
        ctx.game.flag(f"scrub:{node.hostname}")
        return 0
    secs = ctx.game.scrub_seconds(node)
    start = node.footprint
    await ctx.sleep(secs, render=lambda f: f"Scrubbing {bar(f)} footprint {int(start * (1 - f))}%")
    node.footprint = 0.0
    ctx.write(f"Footprint on {node.hostname} erased.", "good")
    ctx.game.flag(f"scrub:{node.hostname}")
    return 0


@cmd("map", "open the network map", group="game")
async def c_map(ctx: Ctx) -> int:
    await ctx.ui.open_view("map")
    return 0


@cmd("mail", "read your inbox, or send mail", "mail | mail -s SUBJECT [-A FILE] ADDRESS...",
     "Without arguments: opens your inbox (r replies, c composes a new mail).\n"
     "With -s it sends a mail, like the classic mailx:\n"
     "  -s SUBJECT   the subject (quote it if it has spaces)\n"
     "  -A FILE      attach a file from your gateway (repeat for more)\n"
     "The message body is read from standard input, so pipe it in:\n"
     "  echo 'all done' | mail -s 'C012 done' client@quietmail.net\n"
     "or type it after the command and end with a line containing only '.'\n"
     "(or Ctrl+D). Mail can only be sent from your gateway.", group="game")
async def c_mail(ctx: Ctx) -> int:
    if not ctx.args:
        await ctx.ui.open_view("mail")
        ctx.game.flag("mail")
        return 0
    args = list(ctx.args)
    subject, attach, to = "", [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-s", "--subject") and i + 1 < len(args):
            subject = args[i + 1]
            i += 2
        elif a in ("-A", "-a", "--attach") and i + 1 < len(args):
            attach.append(args[i + 1])
            i += 2
        elif a.startswith("-"):
            ctx.err(f"invalid option -- '{a.lstrip('-')[:1]}'")
            return 1
        else:
            to.append(a)
            i += 1
    if not to:
        ctx.err("no recipients specified")
        return 1
    if not ctx.at_gateway:
        ctx.err("no mail transport on this node - send mail from your gateway")
        return 1
    for addr in to:
        if "@" not in addr:
            ctx.err(f"{addr}: invalid address (expected name@domain)")
            return 1
    files = []
    for path in attach:
        try:
            node = ctx.resolve(path, want="file")
            ctx.need(node, "r", path)
        except FSError as e:
            ctx.err(f"{e}\n{path}: attachment failed, message not sent")
            return 1
        files.append(node)
    if ctx.stdin is not None:
        body = ctx.stdin
    elif ctx.background:
        body = ""
    else:
        ctx.write("(type your message; finish with a line containing only '.' or press Ctrl+D)", "dim")
        lines = []
        while True:
            line = await ctx.ui.prompt("")
            if line in (".", "\x04"):
                break
            lines.append(line)
        body = "\n".join(lines) + ("\n" if lines else "")
    if not body.strip():
        ctx.write("Null message body; hope that's ok", "dim")
    if not subject:
        ctx.write("(no subject)", "dim")
    ctx.game.send_mail(to, subject, body, files)
    ctx.write(f"mail: sent to {', '.join(to)}"
              + (f" with {len(files)} attachment{'s' if len(files) != 1 else ''}" if files else ""),
              "dim")
    return 0


@cmd("contracts", "list your accepted contracts", "contracts [id]", group="game")
async def c_contracts(ctx: Ctx) -> int:
    s = ctx.game.state
    if ctx.args:
        c = next((c for c in s.contracts if c.id.lower() == ctx.args[0].lower()), None)
        if not c or c.status == "open":
            ctx.err(f"no accepted contract {ctx.args[0]}")
            return 1
        ctx.write(f"{c.id} - {c.title}  [{c.status}]", "title")
        ctx.write(f"Pay ¢{c.pay:,}   Deadline {clock.fmt_short(c.deadline)}")
        ctx.write(c.brief)
        return 0
    mine = [c for c in s.contracts if c.status == "accepted"]
    if not mine:
        ctx.write(f"No active contracts. Find work at the agency: ssh {AGENCY}")
        return 0
    for c in mine:
        left = clock.fmt_duration(c.deadline - ctx.game.now)
        ctx.write(f"  {c.id:<6} {c.label:<9} ¢{c.pay:>7,}  {left:>7} left  {c.title}")
    ctx.write("\n'contracts <id>' shows the briefing.", "dim")
    return 0


@cmd("tutorial", "show the current tutorial objective", "tutorial [skip]", group="game")
async def c_tutorial(ctx: Ctx) -> int:
    s = ctx.game.state
    if ctx.args and ctx.args[0] == "skip":
        s.tutorial_done = True
        ctx.write("Tutorial skipped. 'help' lists all commands.")
        return 0
    step = tutorial.current(ctx.game)
    if step is None:
        ctx.write("Tutorial complete. Contracts are on the agency BBS (ssh blackrelay.net).")
        return 0
    ctx.write(f"Tutorial {s.tutorial_step + 1}/{len(tutorial.STEPS)}: {step.title}", "title")
    for line in step.text.splitlines():
        ctx.write("  " + line)
    return 0


@cmd("status", "show your money, rating and gear", group="game")
async def c_status(ctx: Ctx) -> int:
    s = ctx.game.state
    ctx.write(f"Handle:   {s.handle}")
    ctx.write(f"Credits:  ¢{s.money:,}")
    ctx.write(f"Rating:   {s.rating_title} ({s.rating})")
    ctx.write(f"Strikes:  {s.strikes}/3")
    ctx.write("Software: " + ", ".join(f"{k} v{v}" for k, v in s.sw.items() if v))
    ctx.write("Hardware: " + ", ".join(f"{k} mk{v}" for k, v in s.hw.items()))
    return 0


@cmd("sleep", "wait, or let game time pass", "sleep NUMBER[s|m|h|d]",
     "Like the real sleep, 'sleep 10' or 'sleep 10s' waits ten real seconds\n"
     "(handy for practising: 'sleep 600 &' gives you a background job).\n"
     "With m, h or d it fast-forwards the GAME clock instead, e.g. 'sleep 2h'.\n"
     "Fast-forward only works on your gateway with no open connections.", group="process")
async def c_sleep(ctx: Ctx) -> int:
    if not ctx.args:
        ctx.err("missing operand")
        return 1
    arg = ctx.args[0].strip().lower()
    mins = clock.parse_duration(arg)
    if mins is None:
        ctx.err(f"invalid time interval '{ctx.args[0]}'")
        return 1
    if not arg[-1:] in ("m", "h", "d"):       # plain number or 's': a real wait
        await asyncio.sleep(mins)
        return 0
    if ctx.background:
        ctx.err("fast-forwarding time can't run in the background")
        return 1
    if not ctx.at_gateway or ctx.game.conns:
        ctx.err("you can only fast-forward on your gateway with no open connections")
        return 1
    mins = min(mins, 24 * 60)
    while mins > 0 and not ctx.game.state.game_over:
        step = min(5.0, mins)
        ctx.game.tick(step)
        mins -= step
    ctx.write(f"You wake up at {clock.fmt_status(ctx.game.now)}.")
    return 0


@cmd("save", "save the game", group="game")
async def c_save(ctx: Ctx) -> int:
    if ctx.game.conns or not ctx.at_gateway:
        ctx.err("disconnect first - you can only save on your gateway")
        return 1
    path = save_state(ctx.game.state)
    ctx.write(f"Game saved ({path.name}).")
    return 0


@cmd("quit", "save and quit the game", group="game")
async def c_quit(ctx: Ctx) -> int:
    ctx.ui.quit()
    return 0
