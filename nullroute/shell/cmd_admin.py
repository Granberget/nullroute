"""Users, permissions and packages: sudo, su, passwd, id, chmod, chown,
stat, tee, which, apt, dpkg - and a few classic fun packages."""

from __future__ import annotations

import asyncio
import random
import textwrap

from ..game import clock, packages as P, store
from ..game.vfs import File, FSError, human_size, mode_string
from ..game.vfs import allowed as vfs_allowed
from ..game.world import GATEWAY
from .commands import cmd, split_flags
from .core import Ctx, Frame

SUDO_CACHE_MIN = 300          # game minutes (5 real minutes)
BUILTINS = {"cd", "exit", "history", "jobs", "fg", "bg", "help", "logout"}
USERS = {"root": 0, "daemon": 1, "syslog": 104}
GROUPS = {"root": 0, "adm": 4, "sudo": 27, "syslog": 110}


def _auth_log(ctx: Ctx, text: str) -> None:
    ctx.game.syslog("sudo", text, path="/var/log/auth.log")


async def authenticate(ctx: Ctx) -> bool:
    """Ask for the user's password like sudo does. Returns True on success."""
    shell = ctx.shell
    state = ctx.game.state
    if ctx.is_root or not ctx.at_gateway:
        return True
    if shell.sudo_until > ctx.game.now:
        return True
    if not state.password:
        ctx.write(f"sudo: no password is set for {ctx.user}. Choose one first with: passwd", "error")
        return False
    if ctx.background:
        ctx.err("a terminal is required to read the password")
        return False
    for attempt in range(3):
        pw = await ctx.ui.prompt(f"[sudo] password for {ctx.user}: ", secret=True)
        if pw == state.password:
            shell.sudo_until = ctx.game.now + SUDO_CACHE_MIN
            return True
        if attempt < 2:
            ctx.write("Sorry, try again.")
    ctx.write("sudo: 3 incorrect password attempts", "error")
    _auth_log(ctx, f"{ctx.user} : 3 incorrect password attempts ; TTY=pts/0 ; PWD={ctx.cwd} ; USER=root")
    return False


# ====================================================================== sudo / su / passwd
@cmd("sudo", "run a command as root (the superuser)", "sudo COMMAND [ARGS] | sudo -i | sudo -l",
     "Runs ONE command with root rights after asking for YOUR password\n"
     "(the one you chose when you started; change it with 'passwd').\n"
     "After a correct password sudo trusts you for a few minutes.\n"
     "  sudo -l     list what you are allowed to do\n"
     "  sudo -i     open a root shell (exit to leave it) - use sparingly\n"
     "  sudo -k     forget the cached password\n"
     "  sudo !!     re-run your previous command with sudo\n"
     "Note: 'sudo echo x > file' fails, because the redirect is done by your\n"
     "own shell before sudo runs. Use 'echo x | sudo tee file' instead.", group="admin")
async def c_sudo(ctx: Ctx) -> int:
    args = list(ctx.args)
    if not args:
        ctx.write("usage: sudo -h | -K | -k | -l | -i | command")
        return 1
    if args[0] in ("-k", "-K"):
        ctx.shell.sudo_until = -1
        return 0
    if args[0] == "-l":
        if not await authenticate(ctx):
            return 1
        ctx.write(f"User {ctx.user} may run the following commands on {ctx.frame.node}:")
        ctx.write("    (ALL : ALL) ALL")
        return 0
    want_shell = args[0] in ("-i", "-s") or args[:1] == ["su"] or args[:1] == ["bash"]
    if args[0] in ("-u",) and len(args) > 2:
        args = args[2:]
    if not want_shell and args[0].startswith("-"):
        ctx.err(f"invalid option -- '{args[0].lstrip('-')[:1]}'")
        return 1
    if not await authenticate(ctx):
        return 1
    cmdline = " ".join(args)
    if ctx.at_gateway and not ctx.is_root:
        _auth_log(ctx, f"{ctx.user} : TTY=pts/0 ; PWD={ctx.cwd} ; USER=root ; COMMAND=/usr/bin/{cmdline}")
    if want_shell:
        if ctx.is_root:
            ctx.write("You are already root.", "dim")
            return 0
        if ctx.background:
            return 1
        home = "/root" if ctx.at_gateway else "/"
        ctx.shell.frames.append(Frame(ctx.frame.node, home, ctx.frame.conn, user="root"))
        ctx.write("Root shell. Be careful in here - type 'exit' to go back.", "warn")
        return 0
    return await ctx.shell.dispatch(args, ctx.stdin, ctx._sink, ctx._err, piped=ctx.piped,
                                    user="root", background=ctx.background, frame=ctx.frame)


@cmd("su", "switch user", "su [-] [USER]",
     "Becomes another user. On NullrouteOS (like Ubuntu) the root account has no\n"
     "password, so 'su' to root always fails - use 'sudo -i' instead.", group="admin")
async def c_su(ctx: Ctx) -> int:
    args = [a for a in ctx.args if a not in ("-", "-l", "--login")]
    target = args[0] if args else "root"
    if target not in (ctx.shell.handle, "root"):
        ctx.err(f"user {target} does not exist or the user entry does not contain all the required fields")
        return 1
    if ctx.is_root:
        if target == "root":
            return 0
        ctx.shell.frames.append(Frame(ctx.frame.node, ctx.game.state.home if ctx.at_gateway else "/",
                                      ctx.frame.conn, user=target))
        return 0
    if ctx.background:
        return 1
    pw = await ctx.ui.prompt("Password: ", secret=True)
    await asyncio.sleep(1.0)
    if target == ctx.user and pw == ctx.game.state.password and pw:
        return 0
    ctx.err("Authentication failure")
    if target == "root":
        ctx.write("(root has no password here. Use 'sudo -i' for a root shell, or better:\n"
                  " 'sudo COMMAND' for just the one command that needs it.)", "dim")
    return 1


@cmd("passwd", "change your password", "passwd", group="admin")
async def c_passwd(ctx: Ctx) -> int:
    state = ctx.game.state
    if not ctx.at_gateway:
        ctx.err("Authentication token manipulation error")
        return 1
    if ctx.is_root and not ctx.args:
        ctx.write("passwd: the root account stays locked on NullrouteOS (use sudo).")
        return 1
    if ctx.background:
        return 1
    ctx.write(f"Changing password for {ctx.shell.handle}.")
    if state.password and not ctx.is_root:
        cur = await ctx.ui.prompt("Current password: ", secret=True)
        if cur != state.password:
            ctx.err("Authentication token manipulation error\npasswd: password unchanged")
            return 1
    new = await ctx.ui.prompt("New password: ", secret=True)
    again = await ctx.ui.prompt("Retype new password: ", secret=True)
    if not new:
        ctx.write("No password has been supplied.\npasswd: Authentication token manipulation error\n"
                  "passwd: password unchanged", "error")
        return 1
    if new != again:
        ctx.write("Sorry, passwords do not match.\npasswd: Authentication token manipulation error\n"
                  "passwd: password unchanged", "error")
        return 1
    state.password = new
    ctx.shell.sudo_until = -1
    ctx.write("passwd: password updated successfully")
    return 0


@cmd("id", "print user and group IDs", "id [USER]", group="admin")
async def c_id(ctx: Ctx) -> int:
    user = ctx.args[0] if ctx.args else ctx.user
    if user == "root":
        ctx.write("uid=0(root) gid=0(root) groups=0(root)")
    elif user == ctx.shell.handle:
        ctx.write(f"uid=1000({user}) gid=1000({user}) groups=1000({user}),4(adm),27(sudo)")
    else:
        ctx.err(f"'{user}': no such user")
        return 1
    return 0


@cmd("groups", "print the groups a user is in", "groups [USER]", group="admin")
async def c_groups(ctx: Ctx) -> int:
    user = ctx.args[0] if ctx.args else ctx.user
    ctx.write("root" if user == "root" else f"{user} adm sudo")
    return 0


# ====================================================================== permissions
def _parse_mode(spec: str, current: int, is_dir: bool) -> int:
    if spec.isdigit() and all(c in "01234567" for c in spec):
        return int(spec, 8)
    mode = current
    for clause in spec.split(","):
        i = 0
        who = ""
        while i < len(clause) and clause[i] in "ugoa":
            who += clause[i]
            i += 1
        who = who or "a"
        if i >= len(clause) or clause[i] not in "+-=":
            raise ValueError(spec)
        while i < len(clause) and clause[i] in "+-=":
            op = clause[i]
            i += 1
            perms = ""
            while i < len(clause) and clause[i] in "rwxXst":
                perms += clause[i]
                i += 1
            bits = 0
            for p in perms:
                if p == "X" and not (is_dir or current & 0o111):
                    continue
                bits |= {"r": 4, "w": 2, "x": 1, "X": 1}.get(p, 0)
            mask = 0
            for w in ("ugo" if "a" in who else who):
                shift = {"u": 6, "g": 3, "o": 0}[w]
                mask |= bits << shift
                if op == "=":
                    mode &= ~(7 << shift)
            if "t" in perms:
                mask |= 0o1000
            if op == "-":
                mode &= ~mask
            else:
                mode |= mask
    return mode


@cmd("chmod", "change file permissions", "chmod [-Rv] MODE FILE...",
     "MODE is either octal or symbolic.\n"
     "Octal: one digit each for owner, group, others; r=4 w=2 x=1, add them up.\n"
     "  755 = rwxr-xr-x   644 = rw-r--r--   700 = rwx------   600 = rw-------\n"
     "Symbolic: who (u=owner g=group o=others a=all), + - or =, then r w x.\n"
     "  u+x  owner may execute     go-w  group and others may not write\n"
     "  a=r  everyone may only read      +x  same as a+x\n"
     "Only the file's owner (or root) may change its permissions.", group="admin")
async def c_chmod(ctx: Ctx) -> int:
    flags, args = split_flags([a for a in ctx.args if not (a.startswith("-") and len(a) > 1 and a[1] in "rwx")] , "Rvcf")
    mode_args = [a for a in ctx.args if a.startswith("-") and len(a) > 1 and a[1] in "rwx"]
    if mode_args:                       # chmod -x file
        args = [mode_args[0]] + args
    if len(args) < 2:
        ctx.err("missing operand")
        return 1
    spec, files = args[0], args[1:]
    status = 0
    for f in files:
        try:
            node = ctx.resolve(f)
        except FSError as e:
            ctx.err(f"cannot access {e}")
            status = 1
            continue
        targets = list(ctx.fs.walk(node)) if "R" in flags else [node]
        for n in targets:
            if not ctx.is_root and n.owner != ctx.user:
                ctx.err(f"changing permissions of '{f}': Operation not permitted")
                status = 1
                break
            try:
                new = _parse_mode(spec.lstrip("-") if spec.startswith("-") else spec, n.mode, n.is_dir) \
                    if not spec.startswith("-") else _parse_mode("a" + spec, n.mode, n.is_dir)
            except ValueError:
                ctx.err(f"invalid mode: '{spec}'")
                return 1
            old = n.mode
            n.mode = (new & 0o7777)
            if "v" in flags or ("c" in flags and old != n.mode):
                ctx.write(f"mode of '{n.path() if n is not node else f}' changed from "
                          f"{old & 0o7777:04o} ({mode_string(_tmp(old, n.is_dir))[1:]}) to "
                          f"{n.mode:04o} ({mode_string(n)[1:]})")
    return status


def _tmp(mode: int, is_dir: bool):
    class _N:
        pass
    n = _N()
    n.mode, n.is_dir = mode, is_dir
    return n


@cmd("chown", "change file owner and group", "chown [-R] USER[:GROUP] FILE...",
     "Only root can give files away, so you normally need sudo:\n"
     "  sudo chown root:root file      sudo chown -R USER:USER dir", group="admin")
async def c_chown(ctx: Ctx) -> int:
    flags, args = split_flags(ctx.args, "Rvcf")
    if len(args) < 2:
        ctx.err("missing operand")
        return 1
    spec, files = args[0], args[1:]
    user, _, group = spec.partition(":")
    valid_users = set(USERS) | {ctx.shell.handle}
    valid_groups = set(GROUPS) | {ctx.shell.handle}
    if user and user not in valid_users:
        ctx.err(f"invalid user: '{spec}'")
        return 1
    if group and group not in valid_groups:
        ctx.err(f"invalid group: '{spec}'")
        return 1
    status = 0
    for f in files:
        try:
            node = ctx.resolve(f)
        except FSError as e:
            ctx.err(f"cannot access {e}")
            status = 1
            continue
        if not ctx.is_root:
            ctx.err(f"changing ownership of '{f}': Operation not permitted")
            status = 1
            continue
        for n in (ctx.fs.walk(node) if "R" in flags else [node]):
            if user:
                n.owner = user
            if group:
                n.group = group
            elif spec.endswith(":") and user:
                n.group = user
    return status


@cmd("chgrp", "change group ownership", "chgrp GROUP FILE...", group="admin")
async def c_chgrp(ctx: Ctx) -> int:
    if len(ctx.args) < 2:
        ctx.err("missing operand")
        return 1
    ctx.args = [":" + ctx.args[0]] + ctx.args[1:]
    ctx.argv = ["chgrp"] + ctx.args
    return await c_chown(ctx)


@cmd("stat", "show detailed file information", "stat FILE...", group="admin")
async def c_stat(ctx: Ctx) -> int:
    for f in ctx.args:
        node = ctx.resolve(f)
        kind = "directory" if node.is_dir else ("regular empty file" if not node.size else "regular file")
        uid = 0 if node.owner == "root" else 1000 if node.owner == ctx.shell.handle else USERS.get(node.owner, 100)
        gid = GROUPS.get(node.group, 1000)
        ts = clock.to_dt(node.mtime).strftime("%Y-%m-%d %H:%M:%S.000000000 +0000")
        ctx.write(f"  File: {f}")
        ctx.write(f"  Size: {node.size:<15} Blocks: {max(8, node.size // 512):<10} IO Block: 4096   {kind}")
        ctx.write(f"Access: ({node.mode & 0o7777:04o}/{mode_string(node)})  Uid: ({uid:>5}/{node.owner:>8})"
                  f"   Gid: ({gid:>5}/{node.group:>8})")
        ctx.write(f"Modify: {ts}")
    return 0


@cmd("tee", "copy input to files and to the screen", "tee [-a] FILE...",
     "Reads standard input and writes it both to the screen and to FILEs.\n"
     "Because tee opens the files itself, 'echo x | sudo tee FILE' can write\n"
     "where 'sudo echo x > FILE' cannot.  -a appends instead of overwriting.", group="files")
async def c_tee(ctx: Ctx) -> int:
    flags, files = split_flags(ctx.args, "a")
    data = ctx.stdin or ""
    status = 0
    for f in files:
        try:
            node = ctx.fs.get(ctx.abspath(f))
            if isinstance(node, File):
                ctx.need(node, "w", f)
                node.content = node.content + data if "a" in flags else data
                node.binary, node.fake_size, node.mtime = False, None, ctx.game.now
            elif node is None:
                parent, name = ctx.parent_for_write(f)
                parent.add(ctx.new_file(name, data))
            else:
                raise FSError(f"{f}: Is a directory")
        except FSError as e:
            ctx.err(str(e))
            status = 1
    if data:
        ctx.write(data.rstrip("\n"))
    return status


@cmd("which", "show where a command lives", "which COMMAND...", group="admin")
async def c_which(ctx: Ctx) -> int:
    status = 0
    for name in ctx.args:
        pkg = P.COMMAND_PKG.get(name)
        if name in ctx.shell.commands and name not in BUILTINS and \
                (pkg is None or P.is_installed(ctx.game.state, pkg)):
            ctx.write(f"/usr/bin/{name}")
        else:
            status = 1
    return status


# ====================================================================== apt
LOCK_ERR = ("E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)\n"
            "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend), are you root?")


def _ver(state, name: str) -> str:
    return P.repo_version(state, name) or "?"


async def _progress(ctx: Ctx, kb: int) -> None:
    speed = store.NIC_SPEED[ctx.game.state.hw["nic"]] * 1000   # kB per second
    await ctx.sleep(max(0.5, min(6.0, kb / speed)), "Downloading")


def _apt_log(ctx: Ctx, cmdline: str, action: str, items: list[str]) -> None:
    fs = ctx.game.world.nodes[GATEWAY].fs
    when = clock.to_dt(ctx.game.now).strftime("%Y-%m-%d  %H:%M:%S")
    entry = (f"\nStart-Date: {when}\nCommandline: {cmdline}\nRequested-By: {ctx.shell.handle} (1000)\n"
             f"{action}: {', '.join(items)}\nEnd-Date: {when}\n")
    log = fs.get("/var/log/apt/history.log")
    if log is not None:
        log.content += entry
    dpkg = fs.get("/var/log/dpkg.log")
    if dpkg is not None:
        stamp = clock.to_dt(ctx.game.now).strftime("%Y-%m-%d %H:%M:%S")
        for it in items:
            dpkg.content += f"{stamp} status {'installed' if action != 'Remove' else 'not-installed'} {it}\n"


def _reading(ctx: Ctx) -> None:
    ctx.write("Reading package lists... Done")
    ctx.write("Building dependency tree... Done")
    ctx.write("Reading state information... Done")


async def _confirm(ctx: Ctx, yes: bool) -> bool:
    if yes or ctx.background:
        return True
    ans = await ctx.ui.prompt("Do you want to continue? [Y/n] ")
    if ans.strip().lower() in ("", "y", "yes", "j", "ja"):
        return True
    ctx.write("Abort.")
    return False


async def apt_main(ctx: Ctx, sub: str, rest: list[str], yes: bool, cmdline: str) -> int:
    state = ctx.game.state
    if not ctx.at_gateway:
        ctx.write("E: This node has no route to a package repository.", "error")
        return 100
    needs_root = sub in ("update", "upgrade", "install", "remove", "purge", "full-upgrade",
                         "dist-upgrade", "autoremove", "reinstall")
    if needs_root and not ctx.is_root:
        if sub == "update":
            ctx.write("Reading package lists... Done", None)
            ctx.write("E: Could not open lock file /var/lib/apt/lists/lock - open (13: Permission denied)\n"
                      "E: Unable to lock directory /var/lib/apt/lists/", "error")
        else:
            ctx.write(LOCK_ERR, "error")
        return 100

    if sub == "update":
        new = {k: v for k, v in state.pkgs_owned.items() if v > state.apt_index.get(k, 0)}
        ctx.write(f"Hit:1 {P.REPO} stable InRelease")
        await ctx.sleep(0.6, "Updating")
        if new:
            ctx.write(f"Get:2 {P.REPO} stable/main amd64 Packages [{4.1 + len(new):.1f} kB]")
        ctx.write(f"Fetched {4.1 + len(new):.1f} kB in 1s ({4.1 + len(new):.1f} kB/s)" if new
                  else "Fetched 0 B in 0s (0 B/s)")
        state.apt_index.update(state.pkgs_owned)
        _reading(ctx)
        up = P.upgradable(state)
        fresh = [k for k in new if not P.is_installed(state, k)]
        if up:
            ctx.write(f"{len(up)} package{'s' if len(up) != 1 else ''} can be upgraded. "
                      "Run 'apt list --upgradable' to see them.")
        else:
            ctx.write("All packages are up to date.")
        if fresh:
            ctx.write(f"New in the repository: {', '.join(fresh)}  (sudo apt install NAME)", "dim")
        return 0

    if sub in ("install", "reinstall"):
        if not rest:
            ctx.write("E: No packages specified... try: apt install NAME", "error")
            return 100
        _reading(ctx)
        todo_new, todo_up, already = [], [], []
        for name in rest:
            pkg = P.PACKAGES.get(name)
            if pkg is None or P.repo_version(state, name) is None:
                ctx.write(f"E: Unable to locate package {name}", "error")
                if pkg and pkg.tool and state.pkgs_owned.get(name):
                    ctx.write("   (you have a licence, but apt doesn't know yet: run 'sudo apt update')", "dim")
                elif pkg and pkg.tool:
                    ctx.write("   (licensed package - buy it in the agency store first)", "dim")
                return 100
            if not P.is_installed(state, name):
                todo_new.append(name)
            elif pkg.tool and state.apt_index.get(name, 0) > state.sw.get(name, 0):
                todo_up.append(name)
            elif sub == "reinstall":
                todo_up.append(name)
            else:
                already.append(name)
        for name in already:
            ctx.write(f"{name} is already the newest version ({_ver(state, name)}).")
        if not todo_new and not todo_up:
            ctx.write(f"0 upgraded, 0 newly installed, 0 to remove and {len(P.upgradable(state))} not upgraded.")
            return 0
        return await _do_install(ctx, todo_new, todo_up, yes or len(rest) == 1, cmdline)

    if sub in ("upgrade", "full-upgrade", "dist-upgrade"):
        _reading(ctx)
        ctx.write("Calculating upgrade... Done")
        up = P.upgradable(state)
        if not up:
            ctx.write("0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.")
            if P.pending_update(state):
                ctx.write("(You bought something since your last 'apt update' - run it first.)", "dim")
            return 0
        return await _do_install(ctx, [], up, yes, cmdline)

    if sub in ("remove", "purge", "autoremove"):
        if sub == "autoremove":
            _reading(ctx)
            ctx.write("0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.")
            return 0
        _reading(ctx)
        gone = []
        for name in rest:
            if name not in P.PACKAGES or not P.is_installed(state, name):
                ctx.write(f"Package '{name}' is not installed, so not removed")
                continue
            gone.append(name)
        if not gone:
            ctx.write("0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.")
            return 0
        ctx.write("The following packages will be REMOVED:")
        ctx.write("  " + " ".join(gone))
        ctx.write(f"0 upgraded, 0 newly installed, {len(gone)} to remove and 0 not upgraded.")
        if any(P.PACKAGES[g].tool for g in gone):
            ctx.write("WARNING: you are removing runner tools you may need for breaching.", "warn")
        if not await _confirm(ctx, yes):
            return 1
        ctx.write("(Reading database ... 23514 files and directories currently installed.)")
        for name in gone:
            ver = P.installed_version(state, name)
            ctx.write(f"Removing {name} ({ver}) ...")
            await asyncio.sleep(0.3)
            P.remove(state, name)
            bin_dir = ctx.game.world.nodes[GATEWAY].fs.get("/usr/bin")
            bin_dir.children.pop(name, None)
        _apt_log(ctx, cmdline, "Remove", [f"{g}:amd64" for g in gone])
        return 0

    if sub == "list":
        ctx.write("Listing... Done")
        only_inst = "--installed" in rest
        only_up = "--upgradable" in rest
        pats = [r for r in rest if not r.startswith("-")]
        for name in sorted(P.PACKAGES):
            pkg = P.PACKAGES[name]
            ver = P.repo_version(state, name)
            inst = P.is_installed(state, name)
            if ver is None and not inst:
                continue
            if pats and not any(_glob(name, p) for p in pats):
                continue
            if only_inst and not inst:
                continue
            up = name in P.upgradable(state)
            if only_up and not up:
                continue
            arch = "amd64" if pkg.tool else "all"
            tag = (f" [upgradable from: {P.installed_version(state, name)}]" if up
                   else " [installed]" if inst else "")
            ctx.write(f"{name}/stable {ver or P.installed_version(state, name)} {arch}{tag}")
        return 0

    if sub == "search":
        if not rest:
            ctx.write("E: You must give at least one search pattern", "error")
            return 100
        ctx.write("Sorting... Done\nFull Text Search... Done")
        term = rest[0].lower()
        for name in sorted(P.PACKAGES):
            pkg = P.PACKAGES[name]
            ver = P.repo_version(state, name)
            if ver is None:
                continue
            if term in name or term in pkg.summary.lower():
                tag = " [installed]" if P.is_installed(state, name) else ""
                ctx.write(f"{name}/stable {ver} {'amd64' if pkg.tool else 'all'}{tag}", "good")
                ctx.write(f"  {pkg.summary}\n")
        return 0

    if sub in ("show", "policy"):
        for name in rest:
            pkg = P.PACKAGES.get(name)
            if pkg is None or P.repo_version(state, name) is None:
                ctx.write(f"N: Unable to locate package {name}", "error")
                return 100
            if sub == "policy":
                ctx.write(f"{name}:\n  Installed: {P.installed_version(state, name) or '(none)'}\n"
                          f"  Candidate: {_ver(state, name)}\n  Version table:\n"
                          f"     {_ver(state, name)} 500\n        500 {P.REPO} stable/main amd64 Packages")
                continue
            ctx.write(f"Package: {name}\nVersion: {_ver(state, name)}\nPriority: optional\n"
                      f"Section: {pkg.section}\nMaintainer: Blackrelay Packaging <repo@blackrelay.net>\n"
                      f"Installed-Size: {pkg.size_kb} kB\nDownload-Size: {pkg.size_kb // 4} kB\n"
                      f"APT-Sources: {P.REPO} stable/main amd64 Packages\nDescription: {pkg.summary}\n")
        return 0

    ctx.err(f"invalid operation {sub}")
    return 1


def _glob(name: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatchcase(name, pattern)


async def _do_install(ctx: Ctx, new: list[str], up: list[str], yes: bool, cmdline: str) -> int:
    state = ctx.game.state
    if new:
        ctx.write("The following NEW packages will be installed:")
        ctx.write("  " + " ".join(new))
    if up:
        ctx.write("The following packages will be upgraded:")
        ctx.write("  " + " ".join(up))
    total = sum(P.PACKAGES[n].size_kb for n in new + up)
    ctx.write(f"{len(up)} upgraded, {len(new)} newly installed, 0 to remove and "
              f"{len([u for u in P.upgradable(state) if u not in up])} not upgraded.")
    ctx.write(f"Need to get {total // 4} kB of archives.")
    ctx.write(f"After this operation, {total} kB of additional disk space will be used.")
    if not await _confirm(ctx, yes):
        return 1
    for i, name in enumerate(new + up, 1):
        pkg = P.PACKAGES[name]
        ctx.write(f"Get:{i} {P.REPO} stable/main {'amd64' if pkg.tool else 'all'} {name} "
                  f"{_ver(state, name)} [{pkg.size_kb // 4} kB]")
    await _progress(ctx, total // 4)
    ctx.write(f"Fetched {total // 4} kB in 1s ({total // 4} kB/s)")
    fs = ctx.game.world.nodes[GATEWAY].fs
    for name in new + up:
        pkg = P.PACKAGES[name]
        old = P.installed_version(state, name)
        ver = _ver(state, name)
        if old is None:
            ctx.write(f"Selecting previously unselected package {name}.")
        ctx.write("(Reading database ... 23514 files and directories currently installed.)")
        ctx.write(f"Preparing to unpack .../{name}_{ver}_amd64.deb ...")
        ctx.write(f"Unpacking {name} ({ver})" + (f" over ({old})" if old else "") + " ...")
        await asyncio.sleep(0.25)
        P.install(state, name)
        fs.put(f"/usr/bin/{name}", "\x7fELF", size=pkg.size_kb * 1024, binary=True, mode=0o755,
               mtime=ctx.game.now)
        ctx.write(f"Setting up {name} ({ver}) ...")
        ctx.game.flag(f"installed:{name}")
    if any(P.PACKAGES[n].section != "games" for n in new + up):
        ctx.write("Processing triggers for man-db (2.12.0-4) ...")
    _apt_log(ctx, cmdline, "Upgrade" if up and not new else "Install",
             [f"{n}:amd64 ({_ver(state, n)})" for n in new + up])
    ctx.game.award("apt")
    return 0


def _apt_cmd(name: str):
    async def run(ctx: Ctx) -> int:
        args = list(ctx.args)
        yes = any(a in ("-y", "--yes", "--assume-yes") for a in args)
        args = [a for a in args if a not in ("-y", "--yes", "--assume-yes", "-q")]
        if not args:
            ctx.write(f"{name} 2.9.8 (amd64)\nUsage: {name} [options] command\n\n"
                      "Most used commands:\n  list - list packages\n  search - search in package descriptions\n"
                      "  show - show package details\n  install - install packages\n"
                      "  remove - remove packages\n  update - update list of available packages\n"
                      "  upgrade - upgrade the system by installing/upgrading packages")
            return 0
        sub, rest = args[0], args[1:]
        if name == "apt-cache" and sub not in ("search", "show", "policy"):
            ctx.err(f"invalid operation {sub}")
            return 100
        return await apt_main(ctx, sub, rest, yes, " ".join(ctx.argv))
    return run


_APT_MAN = ("Installs, upgrades and removes software packages.\n"
            "  apt update            refresh the list of available packages\n"
            "  apt upgrade           install newer versions of what you have\n"
            "  apt install NAME      install a package\n"
            "  apt remove NAME       uninstall a package\n"
            "  apt search WORD       search names and descriptions\n"
            "  apt show NAME         details about a package\n"
            "  apt list --installed  what is installed\n"
            "Changing the system needs root: put sudo in front.\n"
            "Runner tools appear in the repository once you buy a licence in the\n"
            "agency store (then: sudo apt update).")

cmd("apt", "install and manage software packages", "apt COMMAND [PACKAGE...]", _APT_MAN,
    group="admin")(_apt_cmd("apt"))
cmd("apt-get", "install and manage packages (older interface)", "apt-get COMMAND [PACKAGE...]",
    _APT_MAN, group="admin")(_apt_cmd("apt-get"))
cmd("apt-cache", "query the package cache", "apt-cache search|show|policy ...",
    group="admin")(_apt_cmd("apt-cache"))


@cmd("dpkg", "low-level package tool", "dpkg -l [PATTERN]", group="admin")
async def c_dpkg(ctx: Ctx) -> int:
    if not ctx.args or ctx.args[0] not in ("-l", "--list"):
        ctx.err("need an action option (try: dpkg -l)")
        return 2
    state = ctx.game.state
    ctx.write("Desired=Unknown/Install/Remove/Purge/Hold\n"
              "| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend\n"
              "||/ Name            Version              Architecture Description\n"
              "+++-===============-====================-============-=================================")
    for name in sorted(P.PACKAGES):
        if P.is_installed(state, name):
            pkg = P.PACKAGES[name]
            ctx.write(f"ii  {name:<15} {P.installed_version(state, name):<20} "
                      f"{'amd64' if pkg.tool else 'all':<12} {pkg.summary[:33]}")
    return 0


# ====================================================================== fun packages
FORTUNES = [
    "There are 10 kinds of people: those who understand binary and those who don't.",
    "It works on my machine.  -- every developer, ever",
    "A clean desk is a sign of an empty bash_history.",
    "Read the man page. Then read it again. Then grep it.",
    "Real runners pipe. Everyone else copies and pastes.",
    "The only thing worse than no logs is ten gigabytes of logs.",
    "To err is human. To really foul things up you need root.",
    "Have you tried turning it off and on again?",
    "rm -rf: because sometimes you really, really mean it.",
    "Your lucky numbers are 0644, 0755 and 0700.",
    "If at first you don't succeed, sudo !!",
    "Ctrl+C is not a sign of weakness.",
    "A journey of a thousand hops begins with route add.",
    "Today is a good day to tail -f something.",
    "Simplicity is prerequisite for reliability.",
    "Everything is a file. Even your problems.",
]


@cmd("fortune", "print a random fortune cookie", "fortune", group="learn")
async def c_fortune(ctx: Ctx) -> int:
    ctx.write(random.choice(FORTUNES))
    return 0


@cmd("cowsay", "a talking cow", "cowsay [TEXT]  (or: fortune | cowsay)", group="learn")
async def c_cowsay(ctx: Ctx) -> int:
    text = " ".join(ctx.args) if ctx.args else (ctx.stdin or "").strip() or "Moo."
    lines = textwrap.wrap(text, 40) or [""]
    width = max(len(l) for l in lines)
    out = [" " + "_" * (width + 2)]
    if len(lines) == 1:
        out.append(f"< {lines[0]:<{width}} >")
    else:
        for i, l in enumerate(lines):
            left, right = ("/", "\\") if i == 0 else ("\\", "/") if i == len(lines) - 1 else ("|", "|")
            out.append(f"{left} {l:<{width}} {right}")
    out.append(" " + "-" * (width + 2))
    out += ["        \\   ^__^", "         \\  (oo)\\_______", "            (__)\\       )\\/\\",
            "                ||----w |", "                ||     ||"]
    for l in out:
        ctx.write(l)
    return 0


_FONT = {  # 5 rows, 3 columns per character
    "A": ["###", "# #", "###", "# #", "# #"], "B": ["## ", "# #", "## ", "# #", "## "],
    "C": ["###", "#  ", "#  ", "#  ", "###"], "D": ["## ", "# #", "# #", "# #", "## "],
    "E": ["###", "#  ", "## ", "#  ", "###"], "F": ["###", "#  ", "## ", "#  ", "#  "],
    "G": ["###", "#  ", "# #", "# #", "###"], "H": ["# #", "# #", "###", "# #", "# #"],
    "I": ["###", " # ", " # ", " # ", "###"], "J": ["  #", "  #", "  #", "# #", "###"],
    "K": ["# #", "# #", "## ", "# #", "# #"], "L": ["#  ", "#  ", "#  ", "#  ", "###"],
    "M": ["# #", "###", "###", "# #", "# #"], "N": ["###", "# #", "# #", "# #", "# #"],
    "O": ["###", "# #", "# #", "# #", "###"], "P": ["###", "# #", "###", "#  ", "#  "],
    "Q": ["###", "# #", "# #", "###", "  #"], "R": ["###", "# #", "## ", "# #", "# #"],
    "S": ["###", "#  ", "###", "  #", "###"], "T": ["###", " # ", " # ", " # ", " # "],
    "U": ["# #", "# #", "# #", "# #", "###"], "V": ["# #", "# #", "# #", "# #", " # "],
    "W": ["# #", "# #", "###", "###", "# #"], "X": ["# #", "# #", " # ", "# #", "# #"],
    "Y": ["# #", "# #", " # ", " # ", " # "], "Z": ["###", "  #", " # ", "#  ", "###"],
    "0": ["###", "# #", "# #", "# #", "###"], "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"], "3": ["###", "  #", " ##", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"], "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"], "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"], "9": ["###", "# #", "###", "  #", "###"],
    " ": ["   "] * 5, "!": [" # ", " # ", " # ", "   ", " # "], ".": ["   "] * 4 + [" # "],
    "-": ["   ", "   ", "###", "   ", "   "], "?": ["###", "  #", " ##", "   ", " # "],
}


@cmd("figlet", "print text in big letters", "figlet TEXT", group="learn")
async def c_figlet(ctx: Ctx) -> int:
    text = (" ".join(ctx.args) if ctx.args else (ctx.stdin or "")).upper().strip()[:16]
    for row in range(5):
        line = " ".join(_FONT.get(ch, _FONT["?"])[row] for ch in text)
        ctx.write(line.replace("#", "█").rstrip())
    return 0


TRAIN = [
    r"        o O o o                                  ",
    r"       o      ___                                 ",
    r"     _][__|o_|   |______  _______________         ",
    r"    |  NULL  |   | ROUTE| | ~~ ~~ ~~ ~~ |         ",
    r"    |________|___|______|=|_____________|         ",
    r"    /oo--OOO--oo\   \oo/   \oo-------oo/          ",
]


@cmd("sl", "steam locomotive (for when you type sl instead of ls)", "sl", group="learn")
async def c_sl(ctx: Ctx) -> int:
    width = 100
    for offset in range(width, -len(TRAIN[0]), -3):
        frame = []
        for row in TRAIN:
            line = (" " * max(0, offset) + row[max(0, -offset):])[:width]
            frame.append(line)
        ctx.ui.progress("\n".join(frame))
        await asyncio.sleep(0.04)
    ctx.ui.progress(None)
    return 0
