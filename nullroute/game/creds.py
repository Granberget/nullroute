"""Login credentials for nodes, and the wordlists hydra brute-forces with.

Every attackable node has one deterministic login/password pair, derived from
the world seed and the host name so it's stable across a save. The shipped
`/usr/share/wordlists/common.txt` and `users.txt` contain every value a node
can use, so a brute-force with those lists always succeeds eventually. Smaller
or hand-made lists may miss - which is the whole point of a good wordlist.
"""

from __future__ import annotations

import random

# Service accounts a node might run. hydra has to try the right login too, not
# just the right password, so these also make up the shipped users.txt.
COMMON_LOGINS = [
    "admin", "root", "administrator", "operator", "deploy", "backup",
    "svc", "sysadmin", "service", "support", "oracle", "postgres",
]

# The passwords a node might actually use. All of these end up in common.txt.
COMMON_PASSWORDS = [
    "123456", "password", "12345678", "qwerty", "123456789", "letmein",
    "dragon", "monkey", "abc123", "trustno1", "hunter2", "iloveyou",
    "admin123", "passw0rd", "sunshine", "master", "shadow", "superman",
    "football", "welcome", "ninja", "azerty", "solo", "starwars",
    "changeme", "root1234", "toor", "p@ssw0rd", "q1w2e3r4", "zaq12wsx",
    "baseball", "access", "flower", "hottie", "loveme", "whatever",
    "michael", "secret", "server2024", "backup01",
]

# Plausible extra entries that pad out common.txt but no node ever uses.
DECOY_PASSWORDS = [
    "000000", "111111", "121212", "654321", "qwertyuiop", "asdfghjkl",
    "pokemon", "batman", "cheese", "freedom", "jordan23", "michelle",
    "princess", "qazwsx", "robert", "thomas", "computer", "jennifer",
    "daniel", "andrew", "joshua", "matthew", "hockey", "ranger",
    "tigger", "charlie", "jessica", "pepper", "mustang", "ginger",
]

WORDLIST_DIR = "/usr/share/wordlists"


def credentials_for(world, node) -> tuple[str, str]:
    """The one valid (login, password) pair for a node. Deterministic."""
    rng = random.Random(f"{world.seed}:{node.hostname}:creds")
    return rng.choice(COMMON_LOGINS), rng.choice(COMMON_PASSWORDS)


def _password_list() -> list[str]:
    rng = random.Random(1337)
    words = list(dict.fromkeys(COMMON_PASSWORDS + DECOY_PASSWORDS))
    rng.shuffle(words)
    return words


def provision(fs, now: float = 0.0) -> None:
    """Drop the wordlists onto a filesystem (called when hydra is installed)."""
    fs.mkdir_p(WORDLIST_DIR, mtime=now)

    def put(name: str, lines: list[str]) -> None:
        path = f"{WORDLIST_DIR}/{name}"
        if fs.get(path) is None:
            fs.put(path, "\n".join(lines) + "\n", mode=0o644, mtime=now)

    put("common.txt", _password_list())
    put("users.txt", COMMON_LOGINS)
    put("top20.txt", COMMON_PASSWORDS[:20])
