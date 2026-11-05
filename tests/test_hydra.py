"""The hydra login brute-forcer: install, gating, and a full crack."""

from nullroute.game import creds, store


def _install_hydra(h, level: int = 1) -> None:
    h.state.money = 999_999
    for lvl in range(1, level + 1):
        h.game.buy(next(i for i in store.CATALOG if i.key == "hydra" and i.level == lvl))
    h.ui.answers = ["hunter2"]
    h.run("sudo apt update")
    h.run("sudo apt install hydra")


COMMON = "/usr/share/wordlists/common.txt"
USERS = "/usr/share/wordlists/users.txt"


def test_hydra_needs_install(h):
    assert "sudo apt install hydra" in h.run("hydra -l admin -P x intra.foo.corp ssh")


def test_install_brings_wordlists(h):
    _install_hydra(h)
    out = h.run("sudo apt install hydra")        # already installed path is fine; check files
    fs = h.game.world.nodes["gateway"].fs
    assert fs.get(COMMON) is not None
    assert fs.get(USERS) is not None
    assert "/usr/bin/hydra" in h.run("which hydra")
    # the node's real password really is in the shipped list
    node = h.game.world.nodes["sandbox.blackrelay.net"]
    _, pw = h.game.node_credentials(node)
    assert pw in fs.get(COMMON).content.split()


def test_usage_errors(h):
    _install_hydra(h)
    assert "must supply a login" in h.run(f"hydra -P {COMMON} sandbox ssh")
    assert "must supply passwords" in h.run("hydra -l admin sandbox ssh")
    assert "not both" in h.run(f"hydra -l a -L {USERS} -P {COMMON} sandbox ssh")


def test_filtered_port_before_breach(h):
    _install_hydra(h)
    out = h.run(f"hydra -L {USERS} -P {COMMON} sandbox ssh")
    assert "Connection refused" in out
    assert "breach" in out.lower()


def test_version_gates_service(h):
    _install_hydra(h, level=1)
    assert "needs hydra v3" in h.run(f"hydra -l root -P {COMMON} sandbox mysql")
    _install_hydra(h, level=3)
    # mysql module is now unlocked (it still refuses because the port is filtered)
    out = h.run(f"hydra -l root -P {COMMON} sandbox mysql")
    assert "needs hydra" not in out


def test_crack_and_loot(h):
    _install_hydra(h)
    h.run("breach sandbox")
    node = h.game.world.nodes["sandbox.blackrelay.net"]
    login, pw = h.game.node_credentials(node)
    out = h.run(f"hydra -L {USERS} -P {COMMON} sandbox ssh")
    assert "1 valid password found" in out
    assert f"login: {login}" in out and f"password: {pw}" in out
    # loot saved to the gateway
    loot = h.game.world.nodes["gateway"].fs.get(f"{h.state.home}/loot/sandbox.txt")
    assert loot is not None and pw in loot.content
    assert loot.owner == "tester"
    assert "brute_force" in h.state.achievements
    # a brute-force is loud: it trips the trace and leaves a footprint
    assert node.trace_active
    assert node.footprint > 0


def test_wrong_wordlist_finds_nothing(h):
    _install_hydra(h)
    h.run("breach sandbox")
    h.run("echo notthepassword > tiny.txt")
    out = h.run("hydra -l admin -P tiny.txt sandbox ssh")
    assert "0 valid passwords found" in out
    assert h.game.world.nodes["gateway"].fs.get(f"{h.state.home}/loot/sandbox.txt") is None


def test_single_guess_hit(h):
    _install_hydra(h)
    h.run("breach sandbox")
    node = h.game.world.nodes["sandbox.blackrelay.net"]
    login, pw = h.game.node_credentials(node)
    out = h.run(f"hydra -l {login} -p {pw} sandbox ssh")
    assert "1 valid password found" in out
