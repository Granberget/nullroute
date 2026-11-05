"""Tokenise and parse a command line into pipelines.

Supports quotes, backslash escapes, pipes (|), redirections (>, >>, <, 2>,
2>&1), and command lists separated by ;, && and ||.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ParseError(Exception):
    pass


OPERATORS = ["&&", "||", ">>", "2>&1", "2>>", "2>", "|", ";", ">", "<", "&"]


@dataclass
class Word:
    text: str
    quoted: bool = False      # if any part was quoted, no globbing


@dataclass
class Command:
    words: list[Word] = field(default_factory=list)
    stdout: str | None = None
    append: bool = False
    stdin: str | None = None
    stderr: str | None = None   # path, or "&1"


@dataclass
class Pipeline:
    commands: list[Command]
    op: str = ";"               # operator that links to the NEXT pipeline
    background: bool = False    # ended with &


def tokenize(line: str) -> list[Word | str]:
    tokens: list[Word | str] = []
    i = 0
    buf = ""
    quoted = False
    in_word = False
    n = len(line)
    while i < n:
        ch = line[i]
        if ch in " \t":
            if in_word:
                tokens.append(Word(buf, quoted))
                buf, quoted, in_word = "", False, False
            i += 1
            continue
        if ch == "#" and not in_word:
            break
        op = next((o for o in OPERATORS if line.startswith(o, i)), None)
        if op and not (op.startswith("2") and in_word):
            if in_word:
                tokens.append(Word(buf, quoted))
                buf, quoted, in_word = "", False, False
            tokens.append(op)
            i += len(op)
            continue
        if ch == "'":
            end = line.find("'", i + 1)
            if end < 0:
                raise ParseError("unexpected EOF while looking for matching `''")
            buf += line[i + 1:end]
            quoted = in_word = True
            i = end + 1
            continue
        if ch == '"':
            j = i + 1
            part = ""
            while j < n and line[j] != '"':
                if line[j] == "\\" and j + 1 < n and line[j + 1] in '"\\$':
                    part += line[j + 1]
                    j += 2
                    continue
                part += line[j]
                j += 1
            if j >= n:
                raise ParseError('unexpected EOF while looking for matching `"\'')
            buf += part
            quoted = in_word = True
            i = j + 1
            continue
        if ch == "\\" and i + 1 < n:
            buf += line[i + 1]
            quoted = in_word = True
            i += 2
            continue
        buf += ch
        in_word = True
        i += 1
    if in_word:
        tokens.append(Word(buf, quoted))
    return tokens


def parse(line: str) -> list[Pipeline]:
    tokens = tokenize(line)
    pipelines: list[Pipeline] = []
    cmds: list[Command] = []
    cmd = Command()
    i = 0

    def finish_cmd():
        nonlocal cmd
        if not cmd.words:
            raise ParseError("syntax error near unexpected token")
        cmds.append(cmd)
        cmd = Command()

    while i < len(tokens):
        t = tokens[i]
        if isinstance(t, Word):
            cmd.words.append(t)
            i += 1
            continue
        if t in (">", ">>", "<", "2>", "2>>"):
            if i + 1 >= len(tokens) or not isinstance(tokens[i + 1], Word):
                raise ParseError(f"syntax error near unexpected token `{t}'")
            target = tokens[i + 1].text
            if t in (">", ">>"):
                cmd.stdout, cmd.append = target, t == ">>"
            elif t == "<":
                cmd.stdin = target
            else:
                cmd.stderr = target
            i += 2
            continue
        if t == "2>&1":
            cmd.stderr = "&1"
            i += 1
            continue
        if t == "|":
            finish_cmd()
            i += 1
            continue
        if t in (";", "&&", "||", "&"):
            if cmd.words:
                finish_cmd()
            if cmds:
                if t == "&":
                    pipelines.append(Pipeline(cmds, ";", background=True))
                else:
                    pipelines.append(Pipeline(cmds, t))
            elif t != ";":
                raise ParseError(f"syntax error near unexpected token `{t}'")
            cmds = []
            i += 1
            continue
        i += 1
    if cmd.words:
        finish_cmd()
    elif cmds:
        raise ParseError("syntax error: unexpected end of line")
    if cmds:
        pipelines.append(Pipeline(cmds, ";"))
    return pipelines
