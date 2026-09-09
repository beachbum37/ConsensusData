#!/usr/bin/env python3
"""
Splice validated additions into broll.py's vocabulary literals.

BY AST, NOT BY REGEX. broll.py is 17,718 lines and EXPAND alone is 11,901
entries; a regex that finds "the closing brace" finds the wrong one eventually,
and the failure mode is a syntactically valid file with the wrong contents. The
literals' exact line spans come from Python's own parser, the new lines are
inserted immediately before each closing line, and the result is re-parsed and
re-imported before it is allowed to stand.

    python3 apply.py            report what would change
    python3 apply.py --write    write it, after backing up to git
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(os.environ.get("WLAM_VOCAB") or os.environ.get("QM_VOCAB") or Path(__file__).resolve().parent)
TARGET = Path(__file__).resolve().parent / "broll.py"
NAMES = ("EXPAND", "PEOPLE", "ABSTRACT", "NOT_A_PICTURE")


def spans(src: str) -> dict[str, tuple[int, int]]:
    """1-based (first line, last line) of each vocabulary assignment."""
    tree = ast.parse(src)
    out: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id in NAMES:
                out[t.id] = (node.lineno, node.end_lineno)
    return out


def fmt_expand(d: dict[str, str]) -> list[str]:
    return [f"    {k!r}: {v!r}," for k, v in sorted(d.items())]


def fmt_people(d: dict[str, list]) -> list[str]:
    return [f"    {k!r}: ({v[0]!r}, {v[1]!r})," for k, v in sorted(d.items())]


def fmt_words(ws: list[str], indent: str = "    ") -> list[str]:
    """Wrapped, like the existing literals, so a diff stays readable."""
    out, line = [], indent
    for w in sorted(ws):
        piece = f"{w!r}, "
        if len(line) + len(piece) > 78:
            out.append(line.rstrip())
            line = indent
        line += piece
    if line.strip():
        out.append(line.rstrip())
    return out


def main() -> None:
    add = json.loads((HERE / "additions.json").read_text())
    src = TARGET.read_text()
    lines = src.splitlines()
    sp = spans(src)
    missing = [n for n in NAMES if n not in sp]
    if missing:
        raise SystemExit(f"could not locate {missing} in {TARGET}")

    banner = "    # --- added 2026-08-28, vocabulary expansion run ---"
    blocks = {
        "EXPAND": ([banner] + fmt_expand(add.get("expand", {}))) if add.get("expand") else [],
        "PEOPLE": ([banner] + fmt_people(add.get("people", {}))) if add.get("people") else [],
        "ABSTRACT": ([banner] + fmt_words(add.get("abstract", []))) if add.get("abstract") else [],
        "NOT_A_PICTURE": ([banner] + fmt_words(add.get("not_a_picture", []))) if add.get("not_a_picture") else [],
    }

    counts = {"EXPAND": len(add.get("expand", {})),
             "PEOPLE": len(add.get("people", {})),
             "ABSTRACT": len(add.get("abstract", [])),
             "NOT_A_PICTURE": len(add.get("not_a_picture", []))}
    print(f"{TARGET}")
    for n in NAMES:
        a, b = sp[n]
        print(f"  {n:14s} lines {a:6d}-{b:6d}   + {counts[n]:,} entries")

    if "--write" not in sys.argv:
        print("\n(report only - pass --write to apply)")
        return

    dirty = subprocess.run(["git", "-C", str(TARGET.parent), "status", "--porcelain",
                            "--", TARGET.name], capture_output=True, text=True)
    if dirty.stdout.strip():
        raise SystemExit("broll.py has uncommitted changes - commit or stash first, "
                         "so this splice is revertible with one command")

    # INSERT FROM THE BOTTOM UP, or every span after the first is off by the
    # number of lines already added.
    for n in sorted(NAMES, key=lambda k: -sp[k][0]):
        if not blocks[n]:
            continue
        close = sp[n][1] - 1                       # 0-based index of closing line
        lines[close:close] = blocks[n]

    out = "\n".join(lines) + "\n"
    try:
        ast.parse(out)
    except SyntaxError as e:
        raise SystemExit(f"REFUSING TO WRITE: the spliced file does not parse: {e}")
    TARGET.write_text(out)

    # AND IT MUST IMPORT, with the counts it promised.
    chk = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import broll as b; "
         "print(len(b.EXPAND), len(b.PEOPLE), len(b.ABSTRACT), len(b.NOT_A_PICTURE))"
         % str(TARGET.parent)],
        capture_output=True, text=True)
    if chk.returncode:
        subprocess.run(["git", "-C", str(TARGET.parent), "checkout", "--", TARGET.name])
        raise SystemExit(f"REVERTED: broll.py no longer imports:\n{chk.stderr[-2000:]}")
    print(f"\nwritten. EXPAND PEOPLE ABSTRACT NOT_A_PICTURE = {chk.stdout.strip()}")


if __name__ == "__main__":
    main()
