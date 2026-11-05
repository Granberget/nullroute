import asyncio

from nullroute.game.world import DROP, SANDBOX
from nullroute.shell.parser import parse


def test_parse_pipeline_and_redirect():
    pls = parse("cat a.txt | grep -i foo > out.txt && echo done")
    assert len(pls) == 2
    assert pls[0].op == "&&"
    assert [w.text for w in pls[0].commands[1].words] == ["grep", "-i", "foo"]
    assert pls[0].commands[1].stdout == "out.txt"


def test_basic_fs(h):
    out = h.run("ls")
    assert "README.txt" in out and "contracts/" in out
    h.run("mkdir -p a/b && echo hello > a/b/x.txt")
    assert h.run("cat a/b/x.txt") == "hello"
    assert h.run("cat a/b/x.txt | grep -c hel") == "1"
    h.run("cp a/b/x.txt y.txt; mv y.txt z.txt")
    assert "z.txt" in h.run("ls")
    h.run("rm -r a")
    assert "a/" not in h.run("ls")
    assert "No such file" in h.run("cat nope")


def test_glob_and_find(h):
    h.run("touch one.log two.log")
    out = h.run("ls *.log")
    assert "one.log" in out and "two.log" in out
    assert "relays.txt" in h.run("find . -name '*.txt'")


def test_tutorial_flow(h):
    h.run("mail")
    h.run(f"ssh blackrelay.net")
    assert h.ui.views == ["mail", "bbs"]
    out = h.run(f"probe {SANDBOX}")
    assert "FIREWALL" in out
    h.run("route add tallinn.relay")
    h.run("route add osaka")
    assert len(h.state.route) == 2
    out = h.run("ssh sandbox")
    assert "Connection refused by ICE" in out
    out = h.run("breach sandbox")
    assert "ICE down" in out, out
    out = h.run("ssh sandbox")
    assert "Connected" in out, out
    assert h.shell.frame.node == SANDBOX
    out = h.run("find / -name '*.dat'")
    assert "/data/vault/training_payload.dat" in out
    h.run("cd /data/vault")
    out = h.run("scp training_payload.dat gateway:~/downloads/")
    assert "100%" in out, out
    assert h.state.tutorial_step == 8, h.state.tutorial_step
    h.run("scrub")
    assert h.game.world.nodes[SANDBOX].footprint == 0
    h.run("exit")
    out = h.run("echo here | mail -s T0 -A ~/downloads/training_payload.dat vex@blackrelay.net")
    assert "1 attachment" in out, out
    t0 = next(c for c in h.state.contracts if c.id == "T0")
    assert t0.status == "done"
    assert h.state.tutorial_step == 11, h.state.tutorial_step
    from nullroute.game import store
    item = next(i for i in store.CATALOG if i.key == "decrypt" and i.level == 1)
    assert "Purchased" in h.game.buy(item)
    h.ui.answers = ["hunter2"]
    out = h.run("sudo apt update && sudo apt install decrypt")
    assert "Setting up decrypt" in out, out
    assert h.state.sw["decrypt"] == 1
    assert h.state.tutorial_done, h.state.tutorial_step


def test_tutorial_messages_carry_next_step(h):
    assert h.state.tutorial_step == 0
    h.run("mail")                          # skips the optional split step too
    assert h.state.tutorial_step == 2
    note = h.notes[-1]
    assert note.startswith("Objective done: Read your mail.")
    assert "ssh blackrelay.net" in note    # full instructions, no need to type 'tutorial'
    syslog = h.game.world.nodes["gateway"].fs.get("/var/log/syslog").content
    assert "Objective done: Read your mail." in syslog
    assert "Contracts tab" not in syslog   # only the one-line summary is logged


def test_tutorial_follow(h):
    async def go():
        task = asyncio.ensure_future(h.shell.run_line("tutorial -f"))
        await asyncio.sleep(0.05)
        assert h.ui.tutorial_follow
        assert h.state.tutorial_step == 1   # split step done
        assert "TUTORIAL 2/" in h.ui.text and "[x] Split the screen" in h.ui.text
        h.game.flag("mail")
        await asyncio.sleep(0.4)
        assert "TUTORIAL 3/" in h.ui.text and "[>] Visit the agency" in h.ui.text
        assert "TUTORIAL 2/" not in h.ui.text  # redrawn, not appended
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(go())
    assert not h.ui.tutorial_follow
    assert "needs a terminal" in h.run("tutorial -f | cat")


def test_old_save_tutorial_step_migrates(h):
    from nullroute.game.state import migrate
    h.state.tutorial_step = 3
    del h.state.__dict__["tutorial_rev"]
    migrate(h.state)
    assert h.state.tutorial_step == 4 and h.state.tutorial_rev == 1
    migrate(h.state)
    assert h.state.tutorial_step == 4


def test_trace_catches_slow_runner(h):
    h.run("breach sandbox")
    h.run("ssh sandbox")
    for _ in range(400):
        h.game.tick(0.5)
        if h.state.strikes:
            break
    assert h.state.strikes == 1
    assert h.shell.frame.node == "gateway"


def test_contracts_generated_and_acceptable(h):
    open_c = [c for c in h.state.contracts if c.status == "open"]
    assert open_c
    c = next(c for c in open_c if c.min_rating == 0)
    msg = h.game.accept(c)
    assert "accepted" in msg
    assert c.id in h.run("ls contracts")
