"""sudo, permissions, apt, jobs, network, logs and learning."""

from nullroute.game import learning, store


def test_gateway_permissions(h):
    assert "Permission denied" in h.run("touch /etc/evil")
    assert "Permission denied" in h.run("cat /etc/sudoers")
    assert "Permission denied" in h.run("ls /root")
    h.run("touch mine.txt")
    out = h.run("ls -l mine.txt")
    assert "tester tester" in out
    # the classic: sudo does not apply to the redirect
    h.ui.answers = ["hunter2"]
    out = h.run("sudo echo hi > /etc/motd")
    assert "Permission denied" in out
    out = h.run("echo hi | sudo tee /etc/motd")      # password is cached now
    assert h.game.world.nodes["gateway"].fs.get("/etc/motd").content == "hi\n"


def test_sudo_password(h):
    h.ui.answers = ["wrong", "wrong", "wrong"]
    out = h.run("sudo ls /root")
    assert "3 incorrect password attempts" in out
    h.ui.answers = ["hunter2"]
    out = h.run("sudo whoami")
    assert out.strip().endswith("root")
    assert h.run("whoami").strip() == "tester"
    # root shell
    h.run("sudo -i")
    assert h.shell.prompt().startswith("root@gateway")
    h.run("exit")
    assert h.shell.prompt().startswith("tester@gateway")


def test_su_root_fails(h):
    h.ui.answers = ["anything"]
    out = h.run("su")
    assert "Authentication failure" in out


def test_chmod(h):
    h.run("touch run.sh")
    h.run("chmod 700 run.sh")
    assert "-rwx------" in h.run("ls -l run.sh")
    h.run("chmod go+r,u-w run.sh")
    assert "-r-xr--r--" in h.run("ls -l run.sh")
    h.run("chmod -x run.sh")
    assert "-r--r--r--" in h.run("ls -l run.sh")
    assert "Operation not permitted" in h.run("chmod 777 /etc/passwd")
    assert "Operation not permitted" in h.run("chown root run.sh")


def test_apt_flow(h):
    out = h.run("apt install cowsay")
    assert "are you root?" in out
    h.ui.answers = ["hunter2"]
    out = h.run("sudo apt install cowsay")
    assert "Setting up cowsay" in out
    assert "< moo >" in h.run("cowsay moo")
    assert "/usr/bin/cowsay" in h.run("which cowsay")
    assert "[installed]" in h.run("apt list --installed")
    # licensed tools need a purchase and an apt update
    assert "Unable to locate package spoof" in h.run("sudo apt install spoof")
    h.state.money = 99999
    h.game.buy(next(i for i in store.CATALOG if i.key == "bypass" and i.level == 2))
    out = h.run("sudo apt update")
    assert "can be upgraded" in out
    out = h.run("sudo apt upgrade -y")
    assert "Unpacking bypass (2.0) over (1.0)" in out
    assert h.state.sw["bypass"] == 2


def test_not_installed_and_typo(h):
    assert "sudo apt install sl" in h.run("sl")
    assert "did you mean" in h.run("gerp foo bar")


def test_background_jobs_and_kill(h):
    out = h.session("sleep 600 &", "jobs", "ps")
    assert "[1]" in out and "sleep 600" in out
    pid = h.shell.jobs[0].pid if h.shell.jobs else None
    # each session is its own event loop, so do it all in one
    h2_out = h.session("sleep 600 &", 0.05, "ps")
    job = h.shell.jobs[-1] if h.shell.jobs else None
    out = h.session("sleep 600 &", 0.02, "ps", "kill %1", 0.05, "jobs")
    assert "Terminated" in out


def test_kill_by_pid_lesson(h):
    async def go():
        await h.shell.run_line("sleep 600 &")
        await asyncio.sleep(0.01)
        pid = h.shell.jobs[-1].pid
        await h.shell.run_line(f"kill {pid}")
        await asyncio.sleep(0.05)
    import asyncio
    asyncio.run(go())
    assert "killed_by_pid" in h.state.flags


def test_tail_follow(h):
    import asyncio

    async def go():
        await h.shell.run_line("tail -f /var/log/syslog &")
        await asyncio.sleep(0.05)
        h.game.syslog("testd", "hello from the test")
        await asyncio.sleep(0.4)
        await h.shell.run_line("kill %1")
        await asyncio.sleep(0.05)
    h.ui.lines.clear()
    asyncio.run(go())
    assert "hello from the test" in h.ui.text
    assert "tail_f_syslog" in h.state.flags


def test_network_tools(h):
    import asyncio

    async def go():
        await h.shell.run_line("ping -c 2 osaka.relay")
        await h.shell.run_line("host osaka.relay")
        await h.shell.run_line("dig +short osaka.relay")
        await h.shell.run_line("ping -c 1 sandbox.blackrelay.net")
        await h.shell.run_line("route add tallinn")
        await h.shell.run_line("traceroute osaka.relay")
        await h.shell.run_line("ip a")
    h.ui.lines.clear()
    asyncio.run(go())
    out = h.ui.text
    ip = h.game.world.nodes["osaka.relay"].ip
    assert f"64 bytes from osaka.relay ({ip})" in out
    assert f"osaka.relay has address {ip}" in out
    assert "100% packet loss" in out                  # ICE drops ping
    assert "tallinn.relay" in out
    assert "eth0" in out


def test_nmap(h):
    assert "sudo apt install nmap" in h.run("nmap osaka.relay")
    h.ui.answers = ["hunter2"]
    h.run("sudo apt install nmap")
    out = h.run("nmap -sV osaka.relay")
    assert "22/tcp" in out and "open" in out and "relayd" in out
    out = h.run("nmap sandbox.blackrelay.net")
    assert "Host seems down" in out
    out = h.run("nmap -Pn sandbox.blackrelay.net")
    assert "filtered" in out
    h.run("breach sandbox")
    out = h.run("nmap -p 22,80 sandbox")
    assert "80/tcp" in out and "Not shown" not in out
    assert "port_scan" in h.state.achievements


def test_learn_lessons(h):
    out = h.run("learn")
    assert "Moving around" in out
    h.run("learn 1")
    h.run("mkdir -p ~/learn/01/projects/2031 && touch ~/learn/01/projects/2031/notes.txt")
    assert "complete" in h.run("learn check")
    h.run("learn 2")
    want = h.state.counters["lesson2"]
    out = h.run("find ~/learn/02 -name '*.log' | wc -l")
    assert out.strip() == str(want)
    assert "complete" in h.run(f"learn answer {want}")
    h.run("learn 4")
    out = h.run("sort ~/learn/04/visitors.txt | uniq | wc -l")
    assert "complete" in h.run(f"learn answer {out.strip()}")
    h.run("learn 6")
    h.run("chmod 700 ~/learn/06/run.sh")
    assert "complete" in h.run("learn check")
    assert h.state.money >= 1000 + 4 * learning.LESSON_REWARD


def test_achievements_and_tips(h):
    h.run("cat relays.txt | grep osaka")
    assert "first_pipe" in h.state.achievements
    assert "useless_cat" in h.state.tips_seen
    assert "Plumber" in h.run("achievements")


def test_man_has_examples(h):
    out = h.run("man grep")
    assert "EXAMPLES" in out and "grep -rn" in out


def test_ls_pipe_one_per_line(h):
    assert h.run("ls | grep txt").split() == ["README.txt", "relays.txt"]
