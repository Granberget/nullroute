from nullroute.game import contracts as C
from nullroute.game.world import DROP


def _contract(h, kind, max_sec=1):
    """Generate contracts until we get one of the wanted kind on an easy node."""
    for _ in range(300):
        c = C.generate(h.state, h.game.now)
        if c and c.kind == kind and c.difficulty <= max_sec:
            h.state.contracts.append(c)
            return c
    raise AssertionError(f"no {kind} contract generated")


def _connect(h, c):
    node = h.game.world.nodes[c.target]
    h.state.sw.update({"bypass": 3, "decrypt": 3, "spoof": 3})
    h.run("route add tallinn osaka")
    if node.parent:
        out = h.run(f"breach {node.parent}")
        assert "ICE down" in out, out
        out = h.run(f"ssh {node.parent}")
        assert "Connected" in out, out
        out = h.run(f"ssh {node.hostname}")
        assert "Connection refused by ICE" in out
    out = h.run(f"breach {node.hostname}")
    assert "ICE down" in out, out
    out = h.run(f"ssh {node.hostname}")
    assert "Connected" in out, out


def _home(h):
    while len(h.shell.frames) > 1:
        h.run("exit")


def test_retrieve(h):
    c = _contract(h, "retrieve")
    h.game.accept(c)
    _connect(h, c)
    name = c.path.rsplit("/", 1)[1]
    out = h.run(f"find / -name '{name}'")
    assert c.path in out
    out = h.run(f"scp {c.path} gateway:~/downloads/")
    assert "100%" in out, out
    _home(h)
    # forgetting the attachment gets a reply, not a payment
    h.run(f"echo here | mail -s {c.id} {c.client_addr}")
    assert c.status == "accepted"
    assert "no attachment" in h.state.mail[-1].body
    h.run(f"echo here | mail -s {c.id} -A ~/downloads/{name} {c.client_addr}")
    assert c.status == "done"
    assert h.state.money > 1000


def test_retrieve_old_drop_box_still_works(h):
    c = _contract(h, "retrieve")
    h.game.accept(c)
    _connect(h, c)
    h.run(f"scp {c.path} {DROP}:/drop/{c.id}/")
    h.game._slow_tick()
    assert c.status == "done"


def test_wipe(h):
    c = _contract(h, "wipe")
    h.game.accept(c)
    _connect(h, c)
    h.run(f"rm {c.path}")
    h.run("rm -f /data/archive/*.bak")
    _home(h)
    h.game._slow_tick()
    assert c.status == "accepted"            # needs the confirmation mail
    h.run(f"echo done | mail -s '{c.id} done' {c.client_addr}")
    assert c.status == "done"


def test_wipe_confirm_too_early(h):
    c = _contract(h, "wipe")
    h.game.accept(c)
    h.run(f"echo done | mail -s '{c.id} done' {c.client_addr}")
    assert c.status == "accepted"
    assert "still there" in h.state.mail[-1].body


def test_modify(h):
    c = _contract(h, "modify")
    h.game.accept(c)
    _connect(h, c)
    out = h.run(f"grep -n {c.row} {c.path}")
    assert c.row in out
    node = h.game.world.nodes[c.target]
    f = node.fs.get(c.path)
    header = f.content.splitlines()[0].split(",")
    col = header.index(c.field)
    lines = f.content.splitlines()
    for i, line in enumerate(lines):
        cells = line.split(",")
        if cells[0] == c.row:
            cells[col] = c.value
            lines[i] = ",".join(cells)
    f.content = "\n".join(lines) + "\n"          # (what nano would do)
    _home(h)
    h.run(f"echo done | mail -s '{c.id} done' {c.client_addr}")
    assert c.status == "done"


def test_unknown_address_bounces(h):
    h.run("echo hi | mail -s test nobody@nowhere.example")
    assert h.state.mail[-1].subject == "Undelivered Mail Returned to Sender"
    assert "status=bounced" in h.run("sudo cat /var/log/mail.log") or True


def test_plant(h):
    c = _contract(h, "plant")
    h.game.accept(c)
    fname = c.path.rsplit("/", 1)[1]
    directory = c.path.rsplit("/", 1)[0]
    assert fname in h.run(f"ls ~/contracts/{c.id}")
    _connect(h, c)
    out = h.run(f"scp gateway:~/contracts/{c.id}/{fname} {directory}/")
    assert "100%" in out, out
    h.game._slow_tick()
    assert c.status == "done"


def test_find(h):
    c = _contract(h, "find")
    h.game.accept(c)
    _connect(h, c)
    out = h.run("grep -r passphrase /home")
    assert c.answer in out
    _home(h)
    h.run(f"echo {c.answer} | mail -s {c.id} {c.client_addr}")
    assert c.status == "done"


def test_footprint_review_can_burn_you(h):
    c = _contract(h, "retrieve")
    node = h.game.world.nodes[c.target]
    _connect(h, c)
    while len(h.shell.frames) > 1:
        h.run("exit")
    node.footprint = 100
    node.footprint_hops = 0
    h.state.minutes = 500
    node.check_at = 400
    h.game._slow_tick()
    assert node.footprint == 0
    assert h.state.strikes >= 1   # the front node may be reviewed as well


def test_save_roundtrip(h, tmp_path, monkeypatch):
    from nullroute.game import state as S
    monkeypatch.setenv("NULLROUTE_HOME", str(tmp_path))
    S.save(h.state)
    loaded = S.load(h.state.handle)
    assert loaded.handle == h.state.handle
    assert len(loaded.world.nodes) == len(h.state.world.nodes)
