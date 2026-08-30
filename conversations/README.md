# Imported conversations

Transcripts lifted out of claude.ai and checked in here so they can be read,
searched, and referenced from this repo.

## Getting a conversation out of claude.ai

There is no API for chat history, so the content has to come from the official
data export:

1. claude.ai → Settings → Privacy → **Export data**.
2. Anthropic emails a download link (usually within a few minutes).
3. The link gives you a zip containing `conversations.json` — every
   conversation on the account.

## Importing it

```sh
# see what's in the export
python3 scripts/import_chat_export.py ~/Downloads/claude-export.zip --list

# pull one conversation out by title
make import EXPORT=~/Downloads/claude-export.zip NAME=kalodata
```

Each import writes `conversations/<slug>/`:

| Path | Contents |
| --- | --- |
| `transcript.md` | The conversation in order, as Markdown |
| `raw.json` | The untouched conversation object, for fidelity |
| `attachments/` | Text extracted from uploaded files |
| `files/` | Original binaries, when the export includes them |

## A caveat about attachments

The export reliably carries the *text* Claude extracted from an upload
(`extracted_content`) — CSVs, PDFs, and documents come through as readable
text. It does not reliably carry the **original binaries**, and images in
particular usually arrive as a filename with no payload.

The importer says so when it happens:

```
Note: 2 file(s) referenced but not present in the export:
  dashboard_screenshot.png
```

Anything listed there has to be downloaded from the conversation by hand and
dropped into that conversation's `files/` directory.
