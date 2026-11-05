"""A small in-memory Unix-like filesystem with owners and permission bits."""

from __future__ import annotations

import fnmatch
import posixpath
from typing import Iterator


class FSError(Exception):
    """Raised with a ready-to-print message (without the command prefix)."""


class Node:
    is_dir = False

    def __init__(self, name: str, owner: str = "root", group: str = "root",
                 mode: int = 0o644, mtime: float = 0.0):
        self.name = name
        self.owner = owner
        self.group = group
        self.mode = mode
        self.mtime = mtime
        self.parent: Dir | None = None

    def path(self) -> str:
        parts = []
        node: Node | None = self
        while node is not None and node.parent is not None:
            parts.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(parts))


class File(Node):
    def __init__(self, name: str, content: str = "", owner: str = "root",
                 group: str = "root", mode: int = 0o644, mtime: float = 0.0,
                 size: int | None = None, binary: bool = False,
                 tag: str | None = None):
        super().__init__(name, owner, group, mode, mtime)
        self.content = content
        self.fake_size = size
        self.binary = binary
        self.tag = tag

    @property
    def size(self) -> int:
        if self.fake_size is not None:
            return self.fake_size
        return len(self.content.encode("utf-8"))

    def clone(self, name: str | None = None) -> "File":
        return File(name or self.name, self.content, self.owner, self.group,
                    self.mode, self.mtime, self.fake_size, self.binary, self.tag)


class Dir(Node):
    is_dir = True

    def __init__(self, name: str, owner: str = "root", group: str = "root",
                 mode: int = 0o755, mtime: float = 0.0):
        super().__init__(name, owner, group, mode, mtime)
        self.children: dict[str, Node] = {}

    def add(self, node: Node) -> Node:
        node.parent = self
        self.children[node.name] = node
        return node

    @property
    def size(self) -> int:
        return 4096

    def clone(self, name: str | None = None) -> "Dir":
        new = Dir(name or self.name, self.owner, self.group, self.mode, self.mtime)
        for child in self.children.values():
            new.add(child.clone())
        return new


def mode_string(node: Node) -> str:
    out = "d" if node.is_dir else "-"
    for shift in (6, 3, 0):
        bits = (node.mode >> shift) & 7
        out += "r" if bits & 4 else "-"
        out += "w" if bits & 2 else "-"
        out += "x" if bits & 1 else "-"
    if node.mode & 0o1000:
        out = out[:-1] + ("t" if out[-1] == "x" else "T")
    return out


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("", "K", "M", "G", "T"):
        if value < 1024 or unit == "T":
            if unit == "":
                return str(int(value))
            return f"{value:.1f}{unit}" if value < 10 else f"{int(value)}{unit}"
        value /= 1024
    return str(size)


class Identity:
    """Who is performing a filesystem operation."""

    def __init__(self, user: str, groups: set[str] | None = None):
        self.user = user
        self.groups = groups or {user}

    @property
    def is_root(self) -> bool:
        return self.user == "root"


def allowed(node: Node, ident: Identity, perm: str) -> bool:
    if ident.is_root:
        return True
    bit = {"r": 4, "w": 2, "x": 1}[perm]
    if node.owner == ident.user:
        return bool((node.mode >> 6) & bit)
    if node.group in ident.groups:
        return bool((node.mode >> 3) & bit)
    return bool(node.mode & bit)


def normpath(path: str, cwd: str = "/") -> str:
    if not path.startswith("/"):
        path = posixpath.join(cwd, path)
    path = posixpath.normpath(path)
    if path.startswith("//"):
        path = "/" + path.lstrip("/")
    return path


class VFS:
    def __init__(self):
        self.root = Dir("", "root", "root", 0o755)

    # ------------------------------------------------------------ lookup
    def get(self, path: str, cwd: str = "/") -> Node | None:
        path = normpath(path, cwd)
        node: Node = self.root
        if path == "/":
            return node
        for part in path.strip("/").split("/"):
            if not isinstance(node, Dir):
                return None
            nxt = node.children.get(part)
            if nxt is None:
                return None
            node = nxt
        return node

    def resolve(self, path: str, cwd: str, ident: Identity, *,
                want: str | None = None) -> Node:
        """Look up a path checking traversal permission. Raises FSError."""
        full = normpath(path, cwd)
        node: Node = self.root
        if full != "/":
            for part in full.strip("/").split("/"):
                if not isinstance(node, Dir):
                    raise FSError(f"{path}: Not a directory")
                if not allowed(node, ident, "x"):
                    raise FSError(f"{path}: Permission denied")
                nxt = node.children.get(part)
                if nxt is None:
                    raise FSError(f"{path}: No such file or directory")
                node = nxt
        if want == "dir" and not node.is_dir:
            raise FSError(f"{path}: Not a directory")
        if want == "file" and node.is_dir:
            raise FSError(f"{path}: Is a directory")
        return node

    def parent_of(self, path: str, cwd: str, ident: Identity) -> tuple[Dir, str]:
        full = normpath(path, cwd)
        if full == "/":
            raise FSError(f"{path}: Operation not permitted")
        parent_path, name = posixpath.split(full)
        parent = self.resolve(parent_path, "/", ident, want="dir")
        assert isinstance(parent, Dir)
        return parent, name

    # ------------------------------------------------------------ building
    def mkdir_p(self, path: str, owner: str = "root", group: str | None = None,
                mode: int = 0o755, mtime: float = 0.0) -> Dir:
        node: Dir = self.root
        for part in normpath(path).strip("/").split("/"):
            if not part:
                continue
            nxt = node.children.get(part)
            if nxt is None:
                nxt = node.add(Dir(part, owner, group or owner, mode, mtime))
            if not isinstance(nxt, Dir):
                raise FSError(f"{path}: Not a directory")
            node = nxt
        return node

    def put(self, path: str, content: str = "", owner: str = "root",
            group: str | None = None, mode: int = 0o644, mtime: float = 0.0,
            size: int | None = None, binary: bool = False,
            tag: str | None = None) -> File:
        full = normpath(path)
        parent_path, name = posixpath.split(full)
        parent = self.get(parent_path)
        if parent is None:
            parent = self.mkdir_p(parent_path)
        assert isinstance(parent, Dir)
        f = File(name, content, owner, group or owner, mode, mtime, size,
                 binary, tag)
        parent.add(f)
        return f

    def append(self, path: str, text: str) -> None:
        node = self.get(path)
        if isinstance(node, File):
            if node.content and not node.content.endswith("\n"):
                node.content += "\n"
            node.content += text if text.endswith("\n") else text + "\n"
        else:
            self.put(path, text if text.endswith("\n") else text + "\n")

    # ------------------------------------------------------------ walking
    def walk(self, start: Node | None = None) -> Iterator[Node]:
        start = start or self.root
        yield start
        if isinstance(start, Dir):
            for child in list(start.children.values()):
                yield from self.walk(child)

    def find_tag(self, tag: str) -> File | None:
        for node in self.walk():
            if isinstance(node, File) and node.tag == tag:
                return node
        return None

    def used_bytes(self, start: str = "/") -> int:
        node = self.get(start)
        if node is None:
            return 0
        return sum(n.size for n in self.walk(node) if isinstance(n, File))

    # ------------------------------------------------------------ globbing
    def glob(self, pattern: str, cwd: str) -> list[str]:
        """Expand a shell glob. Returns paths in the same style (rel/abs)."""
        absolute = pattern.startswith("/")
        base = "/" if absolute else cwd
        parts = [p for p in pattern.split("/") if p]
        results = [("" if not absolute else "", base)]
        # (display_prefix, real_dir_path)
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            new_results = []
            for disp, real in results:
                node = self.get(real)
                if not isinstance(node, Dir):
                    continue
                if part in (".", ".."):
                    names = [part]
                elif any(c in part for c in "*?["):
                    names = sorted(n for n in node.children
                                   if fnmatch.fnmatchcase(n, part)
                                   and (part.startswith(".") or not n.startswith(".")))
                else:
                    names = [part] if part in node.children else []
                for name in names:
                    real_child = normpath(name, real)
                    if absolute:
                        disp_child = disp + "/" + name
                    else:
                        disp_child = name if not disp else disp + "/" + name
                    if not last and not isinstance(self.get(real_child), Dir):
                        continue
                    new_results.append((disp_child, real_child))
            results = new_results
        return [d for d, _ in results]
