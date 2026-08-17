#!/usr/bin/env python3
"""Bake the corpus into a self-contained browser page.

Writes two files from the same template:

  docs/index.html     full HTML document - open it by double-clicking, or serve
                      it from GitHub Pages
  docs/artifact.html  the same page as a body fragment, for publishing as a
                      Claude Artifact (which supplies its own document shell)

Data is inlined, so neither file makes a network request and both work offline.

    python3 scripts/build.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from corpus import load

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "template.html"
DOCS = ROOT / "docs"

FIELDS = ("id", "text", "theme", "arc", "depth", "industries", "roles",
          "lands_because", "followups", "avoid_if", "tags", "pack")


def payload() -> dict:
    corpus = load()
    return {
        "questions": [
            {k: q[k] for k in FIELDS if k in q}
            for q in corpus.questions
        ],
        "profiles": corpus.industries["profiles"],
        "arcs": list(corpus.arcs.values()),
        "taxonomy": {
            section: {k: v for k, v in corpus.taxonomy[section].items() if not k.startswith("$")}
            for section in ("arc", "depth", "theme", "industries", "roles")
        },
    }


def main() -> int:
    template = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(payload(), ensure_ascii=False, separators=(",", ":"))

    # </script> inside a JSON string would close the script element early.
    fragment = template.replace("__DATA__", data.replace("</", "<\\/"))

    DOCS.mkdir(exist_ok=True)
    (DOCS / "artifact.html").write_text(fragment, encoding="utf-8")

    # The standalone document needs <title> in the head, not floating in body.
    title_match = re.search(r"<title>(.*?)</title>\s*", fragment)
    title = title_match.group(1) if title_match else "Ask Anyone"
    body = fragment[: title_match.start()] + fragment[title_match.end():] if title_match else fragment

    standalone = (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        "</head>\n<body>\n"
        f"{body.strip()}\n"
        "</body>\n</html>\n"
    )
    (DOCS / "index.html").write_text(standalone, encoding="utf-8")

    for path in (DOCS / "index.html", DOCS / "artifact.html"):
        print(f"wrote {path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
