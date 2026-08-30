#!/usr/bin/env python3
"""Pull one conversation out of a claude.ai data export and into this repo.

claude.ai exports your whole account as a zip containing `conversations.json`.
This lifts a single conversation out of it and writes a readable transcript
plus whatever attachment content the export carried:

  conversations/<slug>/transcript.md   the conversation, in order, as Markdown
  conversations/<slug>/raw.json        the untouched conversation object
  conversations/<slug>/attachments/    text extracted from uploaded files
  conversations/<slug>/files/          binary attachments, when the zip has them

Usage:

    python3 scripts/import_chat_export.py export.zip --list
    python3 scripts/import_chat_export.py export.zip --name kalodata
    python3 scripts/import_chat_export.py export.zip --uuid 1a2b3c...

The input may be the zip, an already-unzipped directory, or conversations.json
itself. Nothing outside the standard library is required.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "conversations"

# Files in the export that are metadata, not user attachments.
MANIFEST_NAMES = {"conversations.json", "projects.json", "users.json"}


# --------------------------------------------------------------------------
# reading the export


class Export:
    """A claude.ai export, however it arrived: zip, directory, or bare json."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        if path.is_file() and zipfile.is_zipfile(path):
            self._zip = zipfile.ZipFile(path)

    def conversations(self) -> list[dict[str, Any]]:
        raw = self._read_manifest()
        data = json.loads(raw)
        # Exports have always been a top-level list, but tolerate a wrapper.
        if isinstance(data, dict):
            data = data.get("conversations", [])
        if not isinstance(data, list):
            raise SystemExit("conversations.json is not a list of conversations")
        return data

    def _read_manifest(self) -> str:
        if self._zip is not None:
            for name in self._zip.namelist():
                if Path(name).name == "conversations.json":
                    return self._zip.read(name).decode("utf-8")
            raise SystemExit(f"no conversations.json inside {self.path}")
        if self.path.is_dir():
            found = list(self.path.rglob("conversations.json"))
            if not found:
                raise SystemExit(f"no conversations.json under {self.path}")
            return found[0].read_text(encoding="utf-8")
        if self.path.is_file():
            return self.path.read_text(encoding="utf-8")
        raise SystemExit(f"no such export: {self.path}")

    def binaries(self) -> dict[str, bytes]:
        """Any non-manifest file the export shipped, keyed by base name.

        claude.ai exports usually carry only the *text* extracted from
        attachments, but some include the original files. Take them if present.
        """
        out: dict[str, bytes] = {}
        if self._zip is not None:
            for info in self._zip.infolist():
                name = Path(info.filename).name
                if info.is_dir() or not name or name in MANIFEST_NAMES:
                    continue
                if name.endswith(".json") and info.file_size > 5_000_000:
                    continue
                out[name] = self._zip.read(info)
        elif self.path.is_dir():
            for f in self.path.rglob("*"):
                if f.is_file() and f.name not in MANIFEST_NAMES:
                    out[f.name] = f.read_bytes()
        return out


# --------------------------------------------------------------------------
# picking the conversation


def title_of(conv: dict[str, Any]) -> str:
    return (conv.get("name") or "").strip() or "(untitled)"


def matching(convs: list[dict[str, Any]], name: str | None, uuid: str | None) -> list[dict[str, Any]]:
    if uuid:
        return [c for c in convs if c.get("uuid") == uuid]
    if name:
        needle = name.lower()
        hits = [c for c in convs if needle in title_of(c).lower()]
        if hits:
            return hits
        # Fall back to searching message bodies - the title may not say it.
        return [c for c in convs if needle in json.dumps(c).lower()]
    return []


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "conversation"


# --------------------------------------------------------------------------
# rendering


def blocks(msg: dict[str, Any]) -> Iterator[str]:
    """Message body, preferring structured content over the flat `text`."""
    content = msg.get("content")
    if isinstance(content, list) and content:
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text" and block.get("text"):
                yield block["text"]
            elif kind == "thinking" and block.get("thinking"):
                yield f"> _[thinking]_\n>\n> " + block["thinking"].replace("\n", "\n> ")
            elif kind == "tool_use":
                args = json.dumps(block.get("input", {}), indent=2, ensure_ascii=False)
                yield f"_[tool use: {block.get('name', '?')}]_\n\n```json\n{args}\n```"
            elif kind == "tool_result":
                yield f"_[tool result]_\n\n```\n{_flatten(block.get('content'))}\n```"
        return
    if msg.get("text"):
        yield msg["text"]


def _flatten(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False)


def transcript(conv: dict[str, Any], attachment_index: dict[str, str]) -> str:
    lines = [f"# {title_of(conv)}", ""]
    meta = [
        f"- Source: claude.ai conversation `{conv.get('uuid', '?')}`",
        f"- Created: {conv.get('created_at', '?')}",
        f"- Updated: {conv.get('updated_at', '?')}",
        f"- Messages: {len(conv.get('chat_messages') or [])}",
    ]
    lines += meta + ["", "---", ""]

    for i, msg in enumerate(conv.get("chat_messages") or [], start=1):
        who = {"human": "User", "assistant": "Claude"}.get(msg.get("sender"), msg.get("sender") or "?")
        stamp = msg.get("created_at", "")
        lines.append(f"## {i}. {who}" + (f"  \n_{stamp}_" if stamp else ""))
        lines.append("")

        body = "\n\n".join(b for b in blocks(msg) if b and b.strip())
        lines.append(body if body.strip() else "_(no text content)_")
        lines.append("")

        refs = list(_attachment_refs(msg, attachment_index))
        if refs:
            lines.append("**Attachments**")
            lines.append("")
            lines += refs
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _attachment_refs(msg: dict[str, Any], index: dict[str, str]) -> Iterator[str]:
    for att in msg.get("attachments") or []:
        name = att.get("file_name") or "unnamed"
        size = att.get("file_size")
        note = index.get(name)
        detail = f" ({size} bytes)" if size else ""
        link = f" - [`{note}`]({note})" if note else " - _content not in export_"
        yield f"- `{name}`{detail}{link}"
    # Images and other uploads live under `files` and carry no payload.
    for f in msg.get("files") or []:
        name = f.get("file_name") or "unnamed"
        note = index.get(name)
        link = f" - [`{note}`]({note})" if note else " - _binary not included in export_"
        yield f"- `{name}` (file){link}"


# --------------------------------------------------------------------------
# writing


def write_attachments(conv: dict[str, Any], binaries: dict[str, bytes], dest: Path) -> dict[str, str]:
    """Materialize attachment content. Returns {file_name: repo-relative path}."""
    index: dict[str, str] = {}
    used: set[str] = set()

    def unique(directory: Path, name: str) -> Path:
        safe = re.sub(r"[^\w.\- ]+", "_", name) or "attachment"
        target = directory / safe
        n = 2
        while str(target) in used:
            target = directory / f"{target.stem}-{n}{target.suffix}"
            n += 1
        used.add(str(target))
        return target

    for msg in conv.get("chat_messages") or []:
        for att in msg.get("attachments") or []:
            content = att.get("extracted_content")
            name = att.get("file_name") or "attachment"
            if not content:
                continue
            out = unique(dest / "attachments", f"{name}.txt" if not name.endswith(".txt") else name)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
            index[name] = str(out.relative_to(dest))

        for f in (msg.get("files") or []) + (msg.get("attachments") or []):
            name = f.get("file_name")
            if not name or name in index or name not in binaries:
                continue
            out = unique(dest / "files", name)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(binaries[name])
            index[name] = str(out.relative_to(dest))

    return index


# --------------------------------------------------------------------------


def _display(path: Path) -> Path:
    """Repo-relative when it lives here, absolute when the caller aimed elsewhere."""
    try:
        return path.resolve().relative_to(ROOT)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path, help="export.zip, an unzipped directory, or conversations.json")
    ap.add_argument("--name", help="match conversations whose title (or body) contains this")
    ap.add_argument("--uuid", help="match one conversation by exact uuid")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: conversations/)")
    ap.add_argument("--list", action="store_true", help="list conversations and exit")
    args = ap.parse_args(argv)

    export = Export(args.export)
    convs = export.conversations()

    if args.list or not (args.name or args.uuid):
        for c in convs:
            n = len(c.get("chat_messages") or [])
            print(f"{c.get('uuid', '?')}  {n:>4} msgs  {c.get('updated_at', '')[:10]}  {title_of(c)}")
        if not args.list:
            print("\nNothing selected. Re-run with --name or --uuid.", file=sys.stderr)
            return 1
        return 0

    hits = matching(convs, args.name, args.uuid)
    if not hits:
        print(f"No conversation matched. Run with --list to see what's in the export.", file=sys.stderr)
        return 1
    if len(hits) > 1:
        print("Multiple conversations matched - pick one with --uuid:", file=sys.stderr)
        for c in hits:
            print(f"  {c.get('uuid')}  {title_of(c)}", file=sys.stderr)
        return 1

    conv = hits[0]
    dest = args.out / slugify(title_of(conv))
    dest.mkdir(parents=True, exist_ok=True)

    index = write_attachments(conv, export.binaries(), dest)
    (dest / "raw.json").write_text(json.dumps(conv, indent=2, ensure_ascii=False), encoding="utf-8")
    (dest / "transcript.md").write_text(transcript(conv, index), encoding="utf-8")

    msgs = len(conv.get("chat_messages") or [])
    print(f"Imported {title_of(conv)!r}: {msgs} messages, {len(index)} attachments -> {_display(dest)}")
    missing = [
        f.get("file_name")
        for m in conv.get("chat_messages") or []
        for f in (m.get("files") or [])
        if f.get("file_name") and f.get("file_name") not in index
    ]
    if missing:
        print(f"Note: {len(missing)} file(s) referenced but not present in the export:", file=sys.stderr)
        for name in dict.fromkeys(missing):
            print(f"  {name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
