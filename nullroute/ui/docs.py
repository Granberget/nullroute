"""Help articles shown on the agency BBS (Markdown)."""

DOCS: dict[str, str] = {
    "Getting started": """\
# Getting started

You are a freelance **runner**. Corporations keep their secrets on nodes
protected by **ICE**. Clients pay Blackrelay to get things done on those
nodes, and Blackrelay passes the work to you.

**A typical job**

1. Accept a contract here on the board. The briefing is saved to
   `~/contracts/<id>.txt` on your gateway and sent to your mail.
2. `probe <node>` to see its ICE layers.
3. Set up a bounce route: `route add <relay>` (see `~/relays.txt`).
4. `breach <node>` - the node starts **tracing** you now.
5. `ssh <node>` and do the job with ordinary commands.
6. `scrub` to erase your footprint, then `exit`.

Type `tutorial` in your terminal for a guided first job. Even better: press
**Ctrl+N** for a second terminal and run `tutorial -f` there - the guide then
stays on screen and updates by itself while you work in the other one.
""",
    "ICE and breaching": """\
# ICE and breaching

Each node has one or more ICE layers. Every layer type needs a program:

| Layer       | Program   |
|-------------|-----------|
| FIREWALL    | `bypass`  |
| CIPHER      | `decrypt` |
| GATEKEEPER  | `spoof`   |

Program versions break layers up to a given strength:

| Version | Max strength |
|---------|--------------|
| v1      | 2            |
| v2      | 4            |
| v3      | 5            |

A faster **CPU** makes every layer break faster. `probe` tells you exactly
what you are missing.

After a successful breach the node stays open for about two hours of game
time (two real minutes), so connect right away.

**Core nodes** only accept connections from their corporation's intranet
node (`intra.<corp>`). Breach and `ssh` into the intranet node first, then run
`breach core.<corp>` and `ssh core.<corp>` from there.
""",
    "Trace and routes": """\
# Trace and routes

The moment you start a breach, the node starts tracing you. The trace
keeps running while you are connected to that node (breaching, logged in
or transferring files). If it reaches 100% you are **burned**: you are
disconnected, fined, and get a strike. Three strikes ends your career.

Disconnecting pauses the trace, but the node remembers it for a while.
If you come straight back, the trace picks up where it left off.

**Making traces slower**

* Every relay in your route adds time. `route add osaka`.
* Higher security nodes trace faster.
* `tracemon` shows the trace in your status bar. v2 shows the
  percentage, v3 shows the seconds left.

Time in the game runs at one game minute per real second.
""",
    "Footprints": """\
# Footprints

Breaching a node leaves a **footprint**: evidence that someone was there.
A few hours after you disconnect, the owner reviews the node. If your
footprint is still there they may follow it back to you, and that counts
as a strike.

* `scrub` (run while connected) erases your footprint on that node.
* Long routes make footprints much harder to follow, even if you forget.
""",
    "Brute-forcing logins": """\
# Brute-forcing logins

`hydra` is a parallelised login cracker. It throws a wordlist of passwords
at a service until one of them logs in, then saves what it found to
`~/loot/`. Buy a licence in the Store and install it with apt:

    sudo apt update && sudo apt install hydra

That also drops wordlists into `/usr/share/wordlists/` (`common.txt`,
`users.txt`). Then point it at a target:

    hydra -l admin -P /usr/share/wordlists/common.txt intra.acme.corp ssh
    hydra -L /usr/share/wordlists/users.txt -P /usr/share/wordlists/common.txt ssh://core.acme.corp

* `-l USER` tries one login; `-L FILE` tries a whole list of logins.
* `-p PASS` tries one password; `-P FILE` reads a wordlist.
* `-f` stops at the first login that works.

**The port has to be open.** Live ICE filters the port, so hydra can't
even connect - run `breach` first, then brute-force. A brute-force is as
loud as a breach: the node traces you and you leave a footprint, so route
through relays and `scrub` when you're done.

A better wordlist cracks more. The shipped `common.txt` finds anything;
a small list may miss. Higher hydra versions add more service modules
(telnet, http-form, mysql, ...) and crack faster.
""",
    "Contracts": """\
# Contracts

| Type     | What to do |
|----------|------------|
| Retrieve | Copy a file home, then mail it to the client as an attachment |
| Wipe     | Delete a file (and its backups), then mail the client to confirm |
| Modify   | Change one value in a data file, then mail the client to confirm |
| Plant    | Upload a file from `~/contracts/<id>/` to a given directory |
| Find     | Find a passphrase and mail it to the client (or submit it here) |

The client's address is in the briefing. Mail is sent from your gateway:

    scp report.dat gateway:~/downloads/                (on the node)
    mail -A ~/downloads/report.dat ADDRESS             (on your gateway)
    echo done | mail ADDRESS                           (a confirmation)

If the job isn't actually done the client writes back and tells you so.
Plant contracts complete by themselves. Higher security pays more but
needs a better rating. Missing a deadline costs rating.

You can have three contracts active at a time.
""",
    "Your gateway: sudo & apt": """\
# Your gateway: sudo & apt

On your own gateway you are a **normal user**, not root. You own your home
directory (`~`), but system files in `/etc`, `/usr` and `/root` belong to
root. That is how every real Linux box works.

**sudo** runs one command as root after asking for *your* password:

    sudo apt install cowsay
    sudo nano /etc/hosts
    sudo !!          # repeat the last command, this time with sudo

**apt** is the package manager. Tools you buy in the Store become
available in the Blackrelay repository:

    sudo apt update            # fetch the latest package lists
    sudo apt install decrypt   # install a tool
    sudo apt upgrade           # upgrade everything you have
    apt list --installed       # what's installed (no sudo needed to look)

Hardware is installed immediately; software has to be installed with apt.
A few free classics live in the repository too: `cowsay`, `fortune`,
`figlet`, `sl`, `htop`.

**Permissions** show up in `ls -l` as `-rwxr-xr-x`: owner, group, others.
`chmod` changes them, `chown` (root only) changes the owner.
""",
    "Learning Linux": """\
# Learning Linux

This game runs a real-ish Linux shell, so you can learn a lot by playing.

* `learn` - ten short lessons with exercises the game checks for you
  (and pays you a little for).
* `man COMMAND` - every manual page has an EXAMPLES section.
* `achievements` - a checklist of skills worth picking up.
* Tips pop up when you do something that has a better way.
  `tips off` turns them off.

**Watching logs** is a real admin skill:

    tail -f /var/log/syslog        # follow the system log, Ctrl+C stops
    tail -f /var/log/syslog &      # ...in the background
    journalctl -u mail             # only lines from one service

**Jobs and processes**

    sleep 600 &     # start a background job
    jobs            # list your jobs
    ps aux          # every process
    kill %1         # stop job 1    (kill PID works too)
    top             # live view, q quits
""",
    "Command cheat sheet": """\
# Command cheat sheet

| Command | What it does |
|---------|--------------|
| `ls -la`, `cd`, `pwd`, `tree` | look around |
| `cat`, `less`, `head`, `tail` | read files |
| `grep -ri word /path` | search inside files |
| `find / -name '*.dat'` | search for files by name |
| `cp`, `mv`, `rm -r`, `mkdir` | manage files |
| `nano file` | edit a text file |
| `ssh node`, `exit` | connect / disconnect |
| `scp src dst` | copy between nodes (`host:path`) |
| `probe`, `breach`, `hydra`, `scrub` | runner tools |
| `route`, `map` | bounce route and network map |
| `mail`, `contracts`, `status` | your stuff |
| `contracts -f` | live job checklist - run it in a second terminal (Ctrl+N) |
| `sleep 2h` | let time pass (on your gateway) |

Pipes and redirects work: `grep -r vault /home | head -3 > notes.txt`.
Tab completes commands, files and host names. Ctrl+C stops a command.
""",
}
