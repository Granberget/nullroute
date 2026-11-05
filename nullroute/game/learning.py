"""Learning support: achievements, contextual tips and 'learn' lessons."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

# ====================================================================== achievements
ACHIEVEMENTS: dict[str, tuple[str, str]] = {
    "first_pipe": ("Plumber", "Connect two commands with a pipe: ls | grep txt"),
    "long_pipe": ("Pipe dream", "Chain three pipes in one command line"),
    "redirect": ("Redirector", "Save output to a file with > or >>"),
    "sudo": ("With great power", "Run a command with sudo"),
    "apt": ("Package manager", "Install a package with apt"),
    "chmod": ("Mode switch", "Change file permissions with chmod"),
    "background": ("Multitasker", "Start a background job with &"),
    "fg": ("Job control", "Bring a background job back with fg"),
    "kill": ("Process reaper", "Stop a process with kill"),
    "tail_f": ("Log watcher", "Follow a log file live with tail -f"),
    "ping": ("Echo request", "Ping a host"),
    "traceroute": ("Pathfinder", "Trace the path to a host with traceroute"),
    "dns": ("Name resolver", "Look up a host name with host, dig or nslookup"),
    "port_scan": ("Port scanner", "Scan a host's ports with nmap (sudo apt install nmap)"),
    "mail_attach": ("Special delivery", "Send a mail with an attachment"),
    "split": ("Multiplexer", "Work in two terminals at once (Ctrl+N or split)"),
    "grep_r": ("Needle in a haystack", "Search a directory tree with grep -r"),
    "find": ("Finder", "Find files by name with find -name"),
    "top": ("Overseer", "Watch running processes in top or htop"),
    "man10": ("RTFM", "Read 10 different man pages"),
    "nano_save": ("Editor", "Save a file in nano"),
    "history_bang": ("Deja vu", "Repeat a command with !! (try: sudo !!)"),
    "first_contract": ("Hired gun", "Complete your first real contract"),
    "untraceable": ("Untraceable", "Complete a contract with 4+ relays in your route"),
    "lessons_all": ("Graduate", "Finish every lesson in 'learn'"),
}


def award(game, key: str) -> None:
    s = game.state
    if key in s.achievements or key not in ACHIEVEMENTS:
        return
    s.achievements[key] = game.now
    title, desc = ACHIEVEMENTS[key]
    game.notify(f"Achievement unlocked: {title} - {desc}", "achievement")


# ====================================================================== observing commands
@dataclass
class CmdInfo:
    name: str                 # command name (after sudo)
    words: list[str]          # raw words
    quoted: list[bool]
    sudo: bool
    redirect: bool


def _commands(pipelines) -> list[CmdInfo]:
    out = []
    for pl in pipelines:
        for c in pl.commands:
            words = [w.text for w in c.words]
            quoted = [w.quoted for w in c.words]
            sudo = bool(words) and words[0] == "sudo"
            if sudo:
                words, quoted = words[1:], quoted[1:]
                while words and words[0].startswith("-"):
                    words, quoted = words[1:], quoted[1:]
            if words:
                out.append(CmdInfo(words[0], words, quoted, sudo, c.stdout is not None))
    return out


def _has_flag(words: list[str], ch: str) -> bool:
    return any(w.startswith("-") and not w.startswith("--") and ch in w[1:] for w in words[1:])


TIPS: list[tuple[str, Callable, str]] = []


def tip(key: str, text: str):
    def deco(fn):
        TIPS.append((key, fn, text))
        return fn
    return deco


@tip("useless_cat", "grep can read files on its own: grep PATTERN FILE. No cat needed.")
def _t1(cmds, line, status, shell):
    return len(cmds) >= 2 and cmds[0].name == "cat" and len(cmds[0].words) == 2 and cmds[1].name == "grep"


@tip("ls_h", "ls -lh shows sizes as 4.0K or 1.2M instead of raw bytes.")
def _t2(cmds, line, status, shell):
    return any(c.name == "ls" and _has_flag(c.words, "l") and not _has_flag(c.words, "h") for c in cmds)


@tip("find_quote", "Quote find patterns: find . -name '*.txt'. Without quotes the shell "
                   "expands the * before find ever sees it.")
def _t3(cmds, line, status, shell):
    for c in cmds:
        if c.name == "find" and "-name" in c.words:
            i = c.words.index("-name")
            if i + 1 < len(c.words) and not c.quoted[i + 1] and "*" in c.words[i + 1]:
                return True
    return False


@tip("sudo_redirect", "The > redirect is done by YOUR shell, not by sudo, so it has no root "
                      "rights. Use tee instead: echo text | sudo tee /path/file")
def _t4(cmds, line, status, shell):
    return status != 0 and any(c.sudo and c.redirect for c in cmds)


@tip("apt_sudo", "Installing software changes the system, so apt needs root: "
                 "sudo apt install NAME  (or type: sudo !!  to repeat the last command with sudo)")
def _t5(cmds, line, status, shell):
    return status != 0 and any(c.name in ("apt", "apt-get") and not c.sudo and len(c.words) > 1
                               and c.words[1] in ("install", "remove", "update", "upgrade")
                               for c in cmds)


@tip("grep_dir", "grep reads files, not directories. grep -r PATTERN DIR searches a whole tree.")
def _t6(cmds, line, status, shell):
    return status == 2 and any(c.name == "grep" and not _has_flag(c.words, "r") for c in cmds)


@tip("rm_rf", "rm -rf deletes without asking and there is no undo or trash. "
              "Run ls on the same path first to see what you are about to delete.")
def _t7(cmds, line, status, shell):
    return any(c.name == "rm" and _has_flag(c.words, "r") and _has_flag(c.words, "f") for c in cmds)


@tip("ping_c", "ping keeps going until you press Ctrl+C. ping -c 4 HOST sends just four packets.")
def _t8(cmds, line, status, shell):
    return any(c.name == "ping" and "-c" not in c.words for c in cmds)


@tip("history_up", "Press ↑ to bring back earlier commands, or type !! to run the last one again.")
def _t9(cmds, line, status, shell):
    h = shell.history
    return len(h) >= 2 and h[-1] == h[-2]


@tip("tail_bg", "Put & at the end to keep watching in the background: tail -f /var/log/syslog &  "
                "('jobs' lists it, 'kill %1' stops it).")
def _t10(cmds, line, status, shell):
    return any(c.name == "tail" and ("-f" in c.words or "-F" in c.words) for c in cmds) and \
        not line.rstrip().endswith("&")


@tip("wc_count", "Nice. wc -l counts lines, so 'ls | wc -l' counts files and "
                 "'grep -c x file' counts matches.")
def _t11(cmds, line, status, shell):
    return len(cmds) >= 2 and cmds[-1].name == "wc" and _has_flag(cmds[-1].words, "l")


@tip("ps_grep", "ps aux | grep NAME is the classic way to find a process. pgrep NAME prints just the PIDs.")
def _t12(cmds, line, status, shell):
    return len(cmds) >= 2 and cmds[0].name == "ps" and cmds[1].name == "grep"


def observe(game, shell, line: str, pipelines, status: int) -> None:
    cmds = _commands(pipelines)
    if not cmds:
        return
    pipes = sum(len(pl.commands) - 1 for pl in pipelines)
    if pipes >= 1:
        award(game, "first_pipe")
    if pipes >= 3:
        award(game, "long_pipe")
    if any(c.stdout is not None for pl in pipelines for c in pl.commands):
        award(game, "redirect")
    if any(pl.background for pl in pipelines):
        award(game, "background")
    ok = status == 0
    for c in cmds:
        if c.sudo and ok:
            award(game, "sudo")
        if c.name in ("ping",):
            award(game, "ping")
        if c.name in ("traceroute", "tracepath") and ok:
            award(game, "traceroute")
        if c.name in ("host", "dig", "nslookup") and ok:
            award(game, "dns")
        if c.name == "grep" and (_has_flag(c.words, "r") or _has_flag(c.words, "R")):
            award(game, "grep_r")
        if c.name == "find" and ("-name" in c.words or "-iname" in c.words) and ok:
            award(game, "find")
        if c.name == "chmod" and ok:
            award(game, "chmod")
    s = game.state
    if s.tips_enabled:
        for key, check, text in TIPS:
            if key in s.tips_seen:
                continue
            try:
                hit = check(cmds, line, status, shell)
            except Exception:  # noqa: BLE001
                hit = False
            if hit:
                s.tips_seen.add(key)
                game.notify("Tip: " + text, "tip")
                break


# ====================================================================== lessons
@dataclass
class Lesson:
    title: str
    intro: str
    task: str
    hint: str
    setup: Callable
    check: Callable          # (game, answer|None) -> (ok, message)
    needs_answer: bool = False


def _home(game) -> str:
    return game.state.home


def _put(game, path: str, content: str = "", mode: int = 0o644):
    fs = game.world.nodes["gateway"].fs
    h = game.state.handle
    parent = path.rsplit("/", 1)[0]
    d = fs.mkdir_p(parent)
    cur = d
    while cur is not None and cur.path().startswith(_home(game)) and cur.owner != h:
        cur.owner = cur.group = h
        cur = cur.parent
    f = fs.put(path, content, mode=mode)
    f.owner = f.group = h
    return f


def _mkdir(game, path: str):
    fs = game.world.nodes["gateway"].fs
    d = fs.mkdir_p(path)
    for n in fs.walk(fs.get(_home(game) + "/learn")):
        n.owner = n.group = game.state.handle
    return d


def _rng(game, n: int) -> random.Random:
    return random.Random(game.state.seed * 31 + n)


def _wipe(game, num: int) -> str:
    fs = game.world.nodes["gateway"].fs
    base = f"{_home(game)}/learn/{num:02d}"
    node = fs.get(base)
    if node is not None and node.parent is not None:
        del node.parent.children[node.name]
    _mkdir(game, base)
    return base


# 1 ---------------------------------------------------------------
def _s1(game):
    _wipe(game, 1)


def _c1(game, answer):
    fs = game.world.nodes["gateway"].fs
    f = fs.get(f"{_home(game)}/learn/01/projects/2031/notes.txt")
    if f is None:
        return False, "~/learn/01/projects/2031/notes.txt doesn't exist yet."
    if f.is_dir:
        return False, "notes.txt is a directory - it should be a file (touch makes files)."
    return True, "Directory tree and file are in place."


# 2 ---------------------------------------------------------------
def _s2(game):
    base = _wipe(game, 2)
    rng = _rng(game, 2)
    count = 0
    for d in ["", "/app", "/app/old", "/web", "/web/2030", "/web/2031", "/db"]:
        for _ in range(rng.randint(1, 4)):
            ext = rng.choice([".log", ".log", ".txt", ".conf", ".log.gz"])
            name = f"{rng.choice(['error', 'access', 'debug', 'audit', 'boot', 'cron'])}{rng.randint(1, 99)}{ext}"
            path = f"{base}{d}/{name}"
            if game.world.nodes["gateway"].fs.get(path) is None:
                _put(game, path, "log line\n" * rng.randint(1, 5))
                count += ext == ".log"
    game.state.counters["lesson2"] = count


def _c2(game, answer):
    want = game.state.counters.get("lesson2", -1)
    if (answer or "").strip() == str(want):
        return True, f"Yes, {want} files end in .log (the .log.gz ones don't count)."
    return False, "Not quite. Make sure you count names that END in .log."


# 3 ---------------------------------------------------------------
WORDS = ["apple", "river", "stone", "cloud", "ember", "forest", "glass", "harbor",
         "iron", "jungle", "kettle", "lemon", "marble", "north", "orbit", "pepper"]


def _s3(game):
    base = _wipe(game, 3)
    rng = _rng(game, 3)
    target = rng.randint(0, 24)
    for i in range(25):
        lines = [" ".join(rng.choice(WORDS) for _ in range(8)) for _ in range(12)]
        if i == target:
            lines.insert(rng.randint(0, 11), "the falcon lands at midnight")
        _put(game, f"{base}/memo_{i:02d}.txt", "\n".join(lines) + "\n")
    game.state.counters["lesson3"] = target


def _c3(game, answer):
    want = f"memo_{game.state.counters.get('lesson3', -1):02d}.txt"
    got = (answer or "").strip().rsplit("/", 1)[-1]
    if got == want:
        return True, f"Found it: {want}."
    return False, "That's not the file. grep can list file names for you (look at -l)."


# 4 ---------------------------------------------------------------
def _s4(game):
    base = _wipe(game, 4)
    rng = _rng(game, 4)
    pool = [f"10.0.{rng.randint(0, 9)}.{rng.randint(2, 250)}" for _ in range(rng.randint(14, 23))]
    pool = sorted(set(pool))
    lines = [rng.choice(pool) for _ in range(150)] + pool
    rng.shuffle(lines)
    _put(game, f"{base}/visitors.txt", "\n".join(lines) + "\n")
    game.state.counters["lesson4"] = len(pool)


def _c4(game, answer):
    want = game.state.counters.get("lesson4", -1)
    if (answer or "").strip() == str(want):
        return True, f"Correct, {want} unique addresses."
    return False, "Not right. uniq only removes duplicates that are next to each other - sort first."


# 5 ---------------------------------------------------------------
def _s5(game):
    _wipe(game, 5)


def _c5(game, answer):
    fs = game.world.nodes["gateway"].fs
    f = fs.get(f"{_home(game)}/learn/05/etc.txt")
    if f is None or f.is_dir:
        return False, "~/learn/05/etc.txt doesn't exist yet."
    want = sorted(fs.get("/etc").children)
    got = [l.strip().rstrip("/") for l in f.content.split() if l.strip()]
    if sorted(got) == want:
        return True, "The file holds the listing of /etc."
    return False, "The file exists, but it doesn't contain exactly the output of 'ls /etc'."


# 6 ---------------------------------------------------------------
def _s6(game):
    base = _wipe(game, 6)
    _put(game, f"{base}/run.sh", "#!/bin/bash\necho 'hello from run.sh'\n", mode=0o644)


def _c6(game, answer):
    f = game.world.nodes["gateway"].fs.get(f"{_home(game)}/learn/06/run.sh")
    if f is None:
        return False, "run.sh is gone - run 'learn 6' to recreate it."
    mode = f.mode & 0o777
    if mode == 0o700:
        return True, "rwx------ : you can read, write and run it, nobody else can touch it."
    return False, f"Mode is {mode:03o} ({_perm(mode)}). You want 700 (rwx------)."


def _perm(mode: int) -> str:
    return "".join(c if mode & (1 << (8 - i)) else "-" for i, c in enumerate("rwxrwxrwx"))


# 7 ---------------------------------------------------------------
def _s7(game):
    pass


def _c7(game, answer):
    if "cowsay" in game.state.extra_pkgs:
        return True, "cowsay is installed. Try: cowsay moo"
    return False, "cowsay isn't installed yet."


# 8 ---------------------------------------------------------------
def _s8(game):
    game.state.flags.discard("killed_by_pid")


def _c8(game, answer):
    if "killed_by_pid" in game.state.flags:
        return True, "You found the PID and killed the process."
    return False, "Not done yet: start 'sleep 600 &', find its PID with ps, then kill PID."


# 9 ---------------------------------------------------------------
def _s9(game):
    game.state.flags.discard("tail_f_syslog")


def _c9(game, answer):
    if "tail_f_syslog" in game.state.flags:
        return True, "You watched the system log live."
    return False, "Follow /var/log/syslog with tail -f first (Ctrl+C stops it)."


# 10 --------------------------------------------------------------
def _s10(game):
    pass


def _c10(game, answer):
    want = game.world.nodes["osaka.relay"].ip
    if (answer or "").strip() == want:
        return True, f"osaka.relay is {want}. Computers talk in numbers, DNS gives them names."
    return False, "That's not the address of osaka.relay."


LESSONS: list[Lesson] = [
    Lesson("Moving around",
           "Your shell always has a current directory. pwd prints it, ls lists it and\n"
           "cd changes it. mkdir creates directories (-p creates the parents too) and\n"
           "touch creates an empty file. ~ is short for your home directory.",
           "Create the file  ~/learn/01/projects/2031/notes.txt",
           "mkdir -p ~/learn/01/projects/2031  then  touch ~/learn/01/projects/2031/notes.txt",
           _s1, _c1),
    Lesson("Finding files",
           "find walks a directory tree and prints every match. Combine it with wc -l,\n"
           "which counts lines, to count files.",
           "How many files whose names END in .log are there under ~/learn/02 ?\n"
           "Answer with:  learn answer <number>",
           "find ~/learn/02 -name '*.log' | wc -l", _s2, _c2, True),
    Lesson("Searching inside files",
           "grep searches file contents. -r searches a whole directory, -l prints only\n"
           "the names of matching files, -i ignores case.",
           "One of the memos in ~/learn/03 mentions a falcon. Which file?\n"
           "Answer with:  learn answer <filename>",
           "grep -rl falcon ~/learn/03", _s3, _c3, True),
    Lesson("Pipes",
           "A pipe | sends one command's output into the next command. sort sorts\n"
           "lines, uniq drops repeated neighbours, wc -l counts.",
           "~/learn/04/visitors.txt lists IP addresses, many repeated.\n"
           "How many DIFFERENT addresses are there?   learn answer <number>",
           "sort ~/learn/04/visitors.txt | uniq | wc -l      (or: sort -u ... | wc -l)",
           _s4, _c4, True),
    Lesson("Redirection",
           "> sends output into a file (overwriting it), >> appends to it, and 2> sends\n"
           "error messages somewhere else (2>/dev/null throws them away).",
           "Save the output of  ls /etc  into  ~/learn/05/etc.txt   then: learn check",
           "ls /etc > ~/learn/05/etc.txt", _s5, _c5),
    Lesson("Permissions",
           "ls -l shows permissions like -rw-r--r--: owner, group, others, each with\n"
           "r(ead) w(rite) x(ecute). chmod changes them, with numbers (r=4 w=2 x=1, so\n"
           "7=rwx, 6=rw-, 5=r-x, 4=r--) or letters (u+x, go-r, a+r).",
           "Make ~/learn/06/run.sh readable, writable and executable for you only,\n"
           "and nothing for anyone else.  Then: learn check",
           "chmod 700 ~/learn/06/run.sh      (check with ls -l ~/learn/06)", _s6, _c6),
    Lesson("sudo and apt",
           "Normal users can't change the system. sudo runs ONE command as root after\n"
           "asking for your own password. apt installs software: 'apt search' finds\n"
           "packages, 'sudo apt install NAME' installs one.",
           "Install the package 'cowsay', then try it.  Then: learn check",
           "sudo apt install cowsay   and then   cowsay hello", _s7, _c7),
    Lesson("Processes and jobs",
           "Every running program is a process with a PID (process ID). & starts a\n"
           "command in the background, jobs lists your background jobs, ps shows\n"
           "processes and kill PID stops one.",
           "Start  sleep 600 &  then find its PID with ps and stop it with  kill <PID>\n"
           "Then: learn check",
           "sleep 600 &     ps     kill 4123   (use the PID that ps shows for sleep)",
           _s8, _c8),
    Lesson("Logs",
           "Linux writes what happens to log files in /var/log. tail shows the end of\n"
           "a file, and tail -f keeps it open and prints new lines as they arrive.\n"
           "Ctrl+C stops it.",
           "Follow the system log live:  tail -f /var/log/syslog\n"
           "Watch a few lines appear, stop it with Ctrl+C, then: learn check",
           "tail -f /var/log/syslog", _s9, _c9),
    Lesson("Networking",
           "Every host has an IP address. ping checks if a host answers, host/dig/\n"
           "nslookup turn names into addresses, and traceroute shows the hops a\n"
           "connection goes through.",
           "What is the IP address of osaka.relay?   learn answer <ip>",
           "host osaka.relay    (or: ping -c 1 osaka.relay)", _s10, _c10, True),
]

LESSON_REWARD = 150
