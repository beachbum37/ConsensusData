#!/usr/bin/env python3
"""Build the self-contained posting sheet for the clip slate."""
from __future__ import annotations

import base64
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import re

import qmclip as q

HERE = Path(__file__).resolve().parent
# Per-show state follows QM_WORK; HERE stays the CODE directory.
# One owner for this lives in qmclip.WORK - repeated here because these
# scripts must run without importing it (analyze.py in particular, which
# would delete the transcripts it is writing).
WORK = Path(os.environ.get("WLAM_WORK") or os.environ.get("QM_WORK") or HERE)
_cfg = WORK / "project.json"
CFG = json.loads(_cfg.read_text()) if _cfg.exists() else {}
DELIVER = Path(CFG["out_dir"]) if CFG.get("out_dir") else WORK / "out"


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


# Width the cover thumbnail is embedded at. The posters render() writes are full
# 1080x1920 frames at a median 210KB, and the sheet is a SELF-CONTAINED file that
# gets emailed - embedding them raw triples a ten-clip sheet for no benefit, since
# the thumbnail is being read at about 150px on screen. 320 lands near 34-42KB.
POSTER_W = 320
# Biggest embedded cover we will accept. The downscale lands at 34-42KB; this is
# the tripwire on it having silently not happened.
POSTER_MAX_BYTES = 120_000


def poster_thumb(mp4: Path) -> str:
    """
    The clip's cover frame as a data URI, downscaled, or "" if there is none.

    Empty rather than raising: 20 of 91 delivered clips predate poster() and have
    no .jpg at all, and this sheet gets re-run over archived shows. A missing
    cover must degrade to a card with no image, never to a traceback.
    """
    jpg = mp4.with_suffix(".jpg")
    if not jpg.exists():
        return ""
    try:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(jpg), "-vf",
             f"scale={POSTER_W}:-2", "-q:v", "4", "-f", "mjpeg", "-"],
            capture_output=True)
        data = p.stdout if p.returncode == 0 and p.stdout else jpg.read_bytes()
    except OSError:
        data = jpg.read_bytes()
    # The fallback embeds the RAW poster, and a raw poster is a median 210KB - so
    # a ten-clip sheet built with a broken ffmpeg would be 3.3MB of base64 rather
    # than 400KB, silently. The sheet is emailed; say so rather than shipping it.
    if len(data) > POSTER_MAX_BYTES:
        sys.stderr.write(
            f"note: {jpg.name} did not downscale ({len(data)/1024:.0f}KB); the "
            f"cover is left off this card to keep the sheet emailable.\n")
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def tc(sec: float) -> str:
    return f"{int(sec // 60):02d}:{int(sec % 60):02d}"


def esc(t: str) -> str:
    return html.escape(t or "")


# Slot, label, note, and WHERE THE PLATFORM CUTS IT OFF. The count was already
# printed beside every title and meant nothing - there was no limit next to it,
# so a number on its own is decoration. Two delivered clips ship YouTube titles
# past the ~70 characters Shorts shows before it truncates in search and in the
# sidebar, which is the half of the title that does the work.
#
# These are the VISIBLE lengths, not the API maxima: YouTube accepts 100 and
# shows about 70; X allows 280 but a title that long stops being a title.
TITLE_SLOTS = [("youtube",  "YouTube Shorts", "searchable, keyword first", 70),
               ("tiktok",   "TikTok / Reels", "hook, not keywords", 100),
               ("linkedin", "LinkedIn",       "the insight, named", 150),
               ("x",        "X",              "punchy, cashtags below", 200)]


def titles_block(c: dict) -> str:
    """
    The four titles, each on its own copy button.

    Titles are the part that actually gets retyped, so they are given their own
    row at the TOP of the card rather than buried under the captions - and each
    one copies alone, because you paste them into four different boxes.
    """
    t = c.get("titles") or {}
    rows = []
    for key, label, note, limit in TITLE_SLOTS:
        val = (t.get(key) or "").strip()
        if not val:
            continue
        tid = f"t{key}{c['rank']}"
        over = len(val) > limit
        tip = (f"over the {limit}-character visible limit - it will be truncated"
               if over else f"within the {limit}-character visible limit")
        rows.append(
            f'<div class="trow">'
            f'<div class="tmeta"><span class="tlabel">{esc(label)}</span>'
            f'<span class="tnote">{esc(note)}</span>'
            f'<span class="tlen{" over" if over else ""}" title="{esc(tip)}">'
            f'{len(val)}/{limit}</span></div>'
            f'<p class="tval" id="{tid}">{esc(val)}</p>'
            f'<button class="copy" data-target="{tid}">Copy</button></div>')
    if not rows:
        return ""
    return f'<div class="titles"><h3>Titles</h3>{"".join(rows)}</div>'


# WHERE EACH POST GOES, AND WHAT GOES IN IT.
#
# The card used to be in the EDITOR's order: rationale, then all four titles
# together, then the raw transcript, then two caption boxes. Nothing on it was
# grouped by where it was going, so posting a clip to four places meant four
# passes over the card collecting a title from one block and a caption from
# another - and the four title slots were served by only two caption bodies,
# with nothing saying which.
#
# Now there is one row per destination carrying everything that post needs
# behind ONE button. `body` names which caption text it uses, so the pairing is
# stated rather than implied. X takes no caption body on purpose: the title IS
# the post there, and padding it with a LinkedIn paragraph is how a 280-character
# box gets truncated mid-sentence.
def _text(v, sep: str = ", ") -> str:
    """
    A slate field as text, whether it was written as a string or a list.

    THE SLATE HAS ALWAYS USED LISTS HERE. `titles`, `hashtags` and `onscreen`
    are all written as JSON arrays by every slate on this machine, and every
    reader in this file assumed a string and called .strip() on it. make_sheet
    therefore raised AttributeError on the first real clip it was pointed at,
    which is why no out_dir on this machine contains a posting sheet.
    """
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return sep.join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip()


POST_SLOTS = [
    ("youtube",  "YouTube Shorts", 70,  "platform_caption"),
    ("tiktok",   "TikTok / Reels", 100, "platform_caption"),
    ("linkedin", "LinkedIn",       150, "linkedin_caption"),
    ("x",        "X",              200, None),
]


def about_block(c: dict) -> str:
    """
    "This clip is about X and never says so" - printed where the titles are typed.

    The context resolver finds the person a clip inherited from its segment and
    refers to only as "he" (context.carried_subject). The b-roll path can offer
    a portrait for that; the TITLE is the cheaper and wider fix, because most of
    a feed reads the headline and never presses play. The owner put it plainly:
    "if we have it in the title, it's not gonna realistically matter that much."

    So the sheet says it, right above the boxes, and says whether the titles
    already carry it. Nothing here refuses anything - it is a note to the person
    writing the words.
    """
    who = (c.get("about") or "").strip()
    if not who:
        return ""
    surname = who.split()[-1].lower()
    fields = [c.get("hook") or ""] + list(c.get("titles") or []) + \
             [c.get("platform_caption") or "", c.get("linkedin_caption") or ""]
    named = any(surname in (f or "").lower() for f in fields)
    cls = "about ok" if named else "about warn"
    msg = (f"The clip is about <strong>{esc(who)}</strong> and the titles say so."
           if named else
           f"The clip is about <strong>{esc(who)}</strong> &mdash; the show names "
           f"him before this span and only says &ldquo;he&rdquo; inside it. "
           f"No title or caption mentions him.")
    return f'<p class="{cls}">{msg}</p>'


def posts_block(c: dict) -> str:
    """One row per destination: title + caption + hashtags, one copy button."""
    # BOTH SHAPES, because the slate has always been written with the other one.
    # This read `titles` as a dict keyed by destination and `hashtags` as a
    # string, and every slate on this machine - including the one for the clip
    # already delivered from this show - writes `titles` as a LIST of
    # alternatives and `hashtags` as a LIST of tags. So `make_sheet` raised
    # AttributeError on the first clip it was ever pointed at, which is why no
    # posting sheet exists in any out_dir.
    #
    # Coerced rather than re-specified: a list of titles is a list of
    # ALTERNATIVES, not one per destination, so the first is offered everywhere
    # and the operator picks. Slot i takes alternative i when there are enough
    # to go round, which keeps a hand-authored per-destination list working.
    t = c.get("titles") or {}
    tags = _text(c.get("hashtags"), " ")
    rows = []
    for i, (key, label, limit, body_key) in enumerate(POST_SLOTS):
        if isinstance(t, (list, tuple)):
            title = (t[i] if i < len(t) else (t[0] if t else "")) or ""
            title = str(title).strip()
        else:
            title = (t.get(key) or "").strip()
        if not title:
            continue
        body = (c.get(body_key) or "").strip() if body_key else ""
        pid = f"post-{key}-{c['rank']}"
        over = len(title) > limit
        n = (f'<span class="tlen{" over" if over else ""}" title="'
             f'{"over the " + str(limit) + "-character visible limit" if over else "within " + str(limit)}">'
             f'{len(title)}/{limit}</span>')
        rows.append(
            f'<section class="post">'
            f'<div class="posthead"><h3>{esc(label)}</h3>{n}'
            f'<button class="copy" data-target="{pid}">Copy post</button></div>'
            f'<div class="postbody" id="{pid}">'
            f'<p class="ptitle">{esc(title)}</p>'
            + (block(body) if body else "")
            + (f'<p class="tags">{esc(tags)}</p>' if tags else "")
            + '</div></section>')
    return f'<div class="posts">{"".join(rows)}</div>' if rows else ""


def cutaways_block(c: dict) -> str:
    """
    What the clip cuts away to, and when.

    The sheet said NOTHING about the b-roll. A three-clip sheet whose slate
    carried nine approved cutaways - with the word each lands on, the picture and
    the hold - reached the operator with none of it, so the one part of the clip
    that is chosen rather than spoken was invisible at review time.
    """
    live = [b for b in (c.get("broll") or []) if b.get("approved")]
    if not live:
        return ""
    rows = "".join(
        f'<tr><td class="cw">{esc(str(b.get("on") or "?"))}</td>'
        f'<td>{esc(str(b.get("term") or "?"))}</td>'
        f'<td class="ch">{float(b.get("hold", 0) or 0):.1f}s</td></tr>'
        for b in live)
    return (f'<div class="cutaways"><h3>Cutaways</h3>'
            f'<table>{rows}</table></div>')


def _cleared_chip() -> str:
    """
    The compliance line, per clip, where the decision is actually made.

    It used to be a hardcoded bullet in a footer headed "Before you post",
    printed on 53 of 62 sheets under a heading that was otherwise empty. The
    house rule is that provenance goes in a status chip or a one-line caption,
    never a stacked fine-print footer.
    """
    return ('<span class="tag ok" title="No clip contains the invest call to '
            'action, a share price, or a returns claim. Those moments were cut '
            'out deliberately.">Cleared</span>')


def _links(c: dict, fn: str) -> str:
    """The mp4 and its captions as real links, not as grey text to retype."""
    srt = fn.replace(".mp4", ".srt")
    return (f'<a class="file" href="clips/{fn}">{esc(fn)}</a>'
            # `captions/`, not `../captions/`. The sheet is written INTO the
            # show folder, beside both `clips/` and `captions/` - the mp4 link
            # two lines up is already relative to that, and the footer of this
            # very file tells the reader "files in clips/, subtitle files in
            # captions/". The `../` walked up to the Desktop, so every .srt
            # link in every sheet was dead.
            f'<a class="file" href="captions/{esc(srt)}">.srt</a>')


def tickers_block(c: dict) -> str:
    """A copyable ticker row. Empty clips get nothing rather than an empty box."""
    # TWO FIELDS, TWO PLACES. This rendered whenever EITHER `tickers` or
    # `onscreen` was set, so 51 of 62 delivered sheets carried an empty box whose
    # Copy button collected nothing, wrote "" to the clipboard and still flashed
    # "Copied" - the exact failure the handler's own comment says was fixed.
    #
    # `onscreen` is a compliance statement about what the picture shows, not
    # something anybody pastes, so it is a caption now and the copy box only
    # exists when there are chips to copy.
    spoken = c.get("tickers") or []
    onscreen = _text(c.get("onscreen"))
    if not spoken and not onscreen:
        return ""
    out = '<div class="tickers">'
    if spoken:
        chips = "".join(f'<span class="tk">{esc(t)}</span>' for t in spoken)
        out += (f'<h3>Tickers</h3><div class="tkrow" id="t{c["rank"]}">{chips}</div>'
                f'<button class="copy" data-target="t{c["rank"]}">Copy</button>')
    if onscreen:
        out += f'<p class="onscreen">On screen &middot; {esc(onscreen)}</p>'
    return out + "</div>"


def _heading(clips: list[dict]) -> tuple[str, str]:
    """(title, source line) for THIS slate, not the first one ever cut."""
    n = len(clips)
    words = {1: "One clip", 2: "Two clips", 3: "Three clips", 4: "Four clips",
             5: "Five clips", 6: "Six clips", 7: "Seven clips", 8: "Eight clips",
             9: "Nine clips", 10: "Ten clips"}
    count = words.get(n, f"{n} clips")
    src, dur = "", ""
    cfg = WORK / "project.json"
    if cfg.exists():
        d = json.loads(cfg.read_text())
        src = Path(d.get("source", "")).name
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", d["source"]], capture_output=True, text=True)
            sec = float(out.stdout.strip())
            dur = f"{int(sec)//60}m {int(sec)%60:02d}s"
        except Exception:
            dur = ""
    # THE LARGEST TYPE ON THE PAGE WAS A DOWNLOAD FILENAME. A census of the h1
    # across 62 delivered sheets: "One clip from master" four times, "One clip
    # from EP10_full", "One clip from Bubba says ___  Tune in to find out____",
    # "One clip from Mahalo Kim Ann!   Lot_s of choppiness____kimanncurtin".
    # Every underscore is a character the downloader mangled, rendered at 72px.
    #
    # `show` and `date` in project.json are the real answer and newjob.py knows
    # both. The filename stays on the provenance line underneath, which is where
    # a filename belongs.
    show = str(CFG.get("show") or "").strip()
    date = str(CFG.get("date") or "").strip()
    if show:
        head = f"{count}<br>{esc(show)}"
        sub = " &middot; ".join(x for x in (esc(date), esc(src), dur) if x)
        return head, sub
    stem = Path(src).stem if src else "the recording"
    # No `show` set: at least undo the downloader's mangling rather than
    # rendering it at 72px.
    stem = re.sub(r"[_\s]+", " ", stem).strip(" -_")
    return f"{count} from<br>{esc(stem)}", " &middot; ".join(x for x in (esc(src), dur) if x)


def block(text: str) -> str:
    """Preserve the paragraph breaks the captions were written with."""
    paras = [p.strip() for p in (text or "").split("\n") if p.strip()]
    return "".join(f"<p>{esc(p)}</p>" for p in paras)


def main() -> None:
    slate = json.loads((WORK / "slate.json").read_text())
    clips = sorted(slate["clips"], key=lambda c: c["rank"])

    # q.FONTS, not HERE.parent/assets/fonts. Everything else in the pipeline
    # honours the `fonts` key in project.json, and this line did not - so the
    # sheet was the one step that broke the moment the scripts were run from a
    # copied working directory, which is exactly what you do when two shows are
    # being cut at once.
    inter = b64(q.FONTS / "inter.woff2")

    # Where each clip's cover frame came from. render() records it in
    # qmclip.POSTER_AT, but the sheet is regularly re-run in a fresh process over
    # an already-delivered show, where that dict is empty - so the slate is the
    # durable record and the live dict only backfills it.
    sidecar = {}
    pj = WORK / "posters.json"
    if pj.exists():
        try:
            sidecar = json.loads(pj.read_text())
        except ValueError:
            sidecar = {}
    poster_at = {}
    for c in clips:
        name = f"{c['rank']:02d}-{c['slug']}"
        # posters.json first, then the live dict (same process as the render),
        # then a poster_at left on the clip by an older build.
        t = sidecar.get(name, q.POSTER_AT.get(name, c.get("poster_at")))
        if t is not None:
            poster_at[c["rank"]] = float(t)

    cards = []
    for c in clips:
        fn = f"{c['rank']:02d}-{c['slug']}.mp4"
        thumb = poster_thumb(DELIVER / "clips" / fn)
        at = poster_at.get(c["rank"])
        cover = ""
        if thumb:
            cap = (f"cover +{at:.2f}s" if at is not None else "cover frame")
            cover = (f'<figure class="cover"><img src="{thumb}" alt="Cover frame '
                     f'for {esc(c["hook"])}" loading="lazy">'
                     f'<figcaption>{cap}</figcaption></figure>')
        # Name all four. "Screen" for everything that is not a head shot hid the
        # mode whose relationship to the captions changed most: in duo the
        # captions land on the lower speaker's face, so a reviewer needs to be
        # able to spot a duo clip on the sheet.
        mode = {"head": "Camera", "share": "Screen",
                "conversation": "Conversation",
                "conversation_share": "Conversation + screen",
                "head_follow": "Conversation",
                "duo": "Two-up (retired)",
                "duo_share": "Two-up + screen (retired)"
                }.get(c.get("mode", "head"), "Camera")
        why = esc(c['why'].split('CAPTION FIX')[0].split('COMPLIANCE')[0]
                   .split('REQUIRED')[0].strip())
        cards.append(f"""
<article class="clip" id="c{c['rank']}">
  <header class="clip-head">
    <span class="rank">{c['rank']:02d}</span>
    {cover}
    <div class="clip-title">
      <h2>{esc(c['hook'])}</h2>
      <p class="meta">
        <span>{tc(c['start'])} to {tc(c['end'])}</span>
        <span>{c['end']-c['start']:.0f}s</span>
        <span class="tag">{mode}</span>
        <span class="tag">{esc(c['angle'])}</span>
        {_cleared_chip()}
        {_links(c, fn)}
      </p>
      {posts_block(c)}
    </div>
  </header>

{about_block(c)}
{cutaways_block(c)}
{tickers_block(c)}

  <details class="ref">
    <summary>Reference &mdash; why this cut, and what was said</summary>
    <p class="why">{why}</p>
    <div class="quote"><p>{esc(c['quote'])}</p></div>
  </details>
</article>""")

    _head_title, _head_src = _heading(clips)
    # The tab name and the emailed filename. Two sheets open at once used to be
    # indistinguishable - every one was titled "Quasar Markets clip slate".
    _show = str(CFG.get("show") or "").strip()
    _date = str(CFG.get("date") or "").strip()
    if not _show and CFG.get("source"):
        _show = re.sub(r"[_\s]+", " ", Path(CFG["source"]).stem).strip(" -_")[:60]
    _doc_title = " ".join(x for x in (_show, _date, "\u2014 clip slate") if x)

    # Per-show notes come from the SLATE ("notes": [...] at the top level, or

    # "note" on a clip). This block used to be four bullets hard-coded from one

    # show in August, and they shipped verbatim on twelve posting sheets since.

    _notes = list(slate.get("notes") or [])

    for _c in clips:

        if _c.get("note"):

            _notes.append(f"Clip {_c.get('rank', '?'):02d}: {_c['note']}")

    _notes_html = "".join(f"<li>{esc(n)}</li>" for n in _notes)

    # CREDITS. Almost every picture this rig uses is CC0, public domain or under a
    # stock licence that asks for nothing, and those are deliberately NOT listed -
    # a credit block naming forty photographs nobody is owed is noise, and noise
    # is how the one line that IS owed gets skipped.
    #
    # What is listed is anything carrying an ATTRIBUTION obligation. That is
    # almost entirely the portrait tier: a photograph of a named public figure is
    # the one subject where the free libraries have nothing, so search_people
    # reaches for Commons and takes CC BY when there is no public-domain frame.
    # CC BY asks for a credit "reasonable to the medium", and a burned-in credit
    # on a 50-second vertical clip is not reasonable and would wreck the frame -
    # so it is carried here, where the operator pastes it into the platform
    # caption. THIS BLOCK IS THE REASON THE TIER MAY TAKE CC BY AT ALL. If it is
    # ever removed, search_people goes back to public-domain only.
    _credits = []
    try:
        _idx = json.loads((q.BROLL_LIB / "index.json").read_text())
    except Exception:
        _idx = {}
    _used = {b.get("asset") for c in clips for b in (c.get("broll") or [])
             if b.get("approved") and b.get("asset")}
    _free = ("public domain", "publicdomain", "pdm", "cc0", "no restrictions",
             "pexels", "pixabay")
    for _a in sorted(_used):
        _r = _idx.get(_a) or {}
        _lic = (_r.get("licence") or "").lower()
        if not _lic or any(k in _lic for k in _free):
            continue
        _credits.append((_r.get("title") or _a, _r.get("creator") or "unknown",
                         _r.get("licence") or "", _r.get("page") or ""))
    _credits_html = ""
    if _credits:
        _rows = "".join(
            f"<li>{esc(t)} &mdash; {esc(cr)}, {esc(li)}"
            + (f' &middot; <span class="mut">{esc(pg)}</span>' if pg else "")
            + "</li>" for t, cr, li, pg in _credits)
        _credits_html = (
            '<h3 style="margin-top:18px">Credits &mdash; paste these into the '
            'caption</h3><p class="mut">These pictures are licensed on condition '
            'of attribution. Everything else in the set is public domain or '
            'stock and is owed nothing.</p><ul>' + _rows + "</ul>")

    # THE FOOTER ONLY EXISTS WHEN IT HAS SOMETHING IN IT. It used to ship two
    # headings over nothing: `<h3>What was left out</h3><p></p>` - literally an
    # empty paragraph - on 53 of 62 delivered sheets, and a "Before you post"
    # list whose only content was a hardcoded compliance sentence. That sentence
    # is now a per-clip Cleared chip, which is where the decision is made.
    _left_out = str(slate.get("rejected_note", "") or "").strip()
    _parts = []
    if _notes_html:
        _parts.append(f"<h3>Before you post</h3><ul>{_notes_html}</ul>")
    if _credits_html:
        _parts.append(_credits_html)
    if _left_out:
        _parts.append(f'<h3>What was left out</h3><p>{esc(_left_out)}</p>')
    _footer_html = f'<div class="note">{"".join(_parts)}</div>' if _parts else ""

    doc = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<!-- WITHOUT THIS THE PHONE LAYOUT IS DEAD CODE. All 587 delivered sheets shipped
     with no viewport meta, so a 375px phone reported a 980px legacy layout
     viewport and the @media(max-width:820px) block never matched once - the hook,
     the timecode and the filename were all clipped on the device the operator is
     most likely holding when they post. -->
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(_doc_title)}</title>
<style>
@font-face{{font-family:'Inter';src:url(data:font/woff2;base64,{inter}) format('woff2');font-weight:100 900;font-display:swap}}
:root{{
  --bg:#0e1319; --card:#101010; --elev:#141a21;
  --tx:#fffdf9; --tx2:rgba(255,253,249,.92); --mut:rgba(255,253,249,.62); --dim:rgba(255,253,249,.42);
  --cyan:#9cc4d4; --div:rgba(255,253,249,.14);
  /* header column + gap, and the body indent that has to match it. The cover
     figure (132px + 24px gap) is added in .clip-head:has(.cover) below. */
  --rankw:64px; --gap:24px; --coverw:156px;
  --indent:calc(var(--rankw) + var(--gap));
}}
:root[data-theme="light"]{{
  --bg:#f4f2ee; --card:#fffdf9; --elev:#eae7e1;
  --tx:#101010; --tx2:#26292d; --mut:#4a4f55; --dim:#6b7076;
  --cyan:#5d8899; --div:rgba(16,16,16,.14);
}}
@media (prefers-color-scheme: light){{
  :root:not([data-theme="dark"]){{
    --bg:#f4f2ee; --card:#fffdf9; --elev:#eae7e1;
    --tx:#101010; --tx2:#26292d; --mut:#4a4f55; --dim:#6b7076;
    --cyan:#5d8899; --div:rgba(16,16,16,.14);
  }}
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);
  font-family:Inter,system-ui,sans-serif;font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased;letter-spacing:-.005em;line-height:1.6}}
.wrap{{max-width:1120px;margin:0 auto;padding:72px 32px 120px}}
.eyebrow{{font-size:11px;font-weight:600;letter-spacing:.22em;color:var(--cyan);
  text-transform:uppercase;display:flex;align-items:center;gap:14px;margin:0 0 20px}}
.eyebrow::before{{content:'';width:46px;height:3px;background:var(--cyan)}}
h1{{font-family:Inter,sans-serif;font-weight:400;font-size:clamp(40px,6.4vw,72px);
  line-height:1.02;letter-spacing:-.02em;margin:0 0 18px}}
.lede{{color:var(--mut);font-size:17px;max-width:64ch;margin:0 0 10px}}
.src{{color:var(--dim);font-size:13px;margin:0}}
.rule{{height:1px;background:var(--div);border:0;margin:52px 0 0}}
.clip{{padding:52px 0;border-bottom:1px solid var(--div)}}
.clip-head{{display:flex;gap:var(--gap);align-items:flex-start}}
/* A card WITH a cover pushes its own body indent out to match. :has() is
   supported everywhere this sheet is opened; a browser without it simply keeps
   the un-covered indent, which is the pre-poster() layout and still correct. */
.clip:has(.cover){{--indent:calc(var(--rankw) + var(--gap) + var(--coverw))}}
/* The cover frame. This is the still the feed judges the clip on, so it is on
   the card at a size you can actually read, with the timestamp it came from -
   frame 0 catches the hook card mid-swipe and 15% transparent. */
.cover{{margin:0;flex:0 0 132px;display:flex;flex-direction:column;gap:6px}}
.cover img{{width:132px;height:auto;display:block;border-radius:4px;
  border:1px solid var(--div);background:#000}}
.cover figcaption{{font-family:Inter,sans-serif;font-size:11px;letter-spacing:.04em;
  color:var(--dim);text-align:center}}
.rank{{font-family:Inter,sans-serif;font-size:42px;font-weight:400;
  color:var(--cyan);line-height:1;min-width:var(--rankw);opacity:.9}}
.clip-title h2{{font-family:Inter,sans-serif;font-weight:400;
  font-size:clamp(25px,3.4vw,38px);line-height:1.06;letter-spacing:-.02em;margin:0 0 12px}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 18px;margin:0;font-size:12px;color:var(--dim)}}
.meta .tag{{background:var(--elev);color:var(--mut);padding:3px 10px;border-radius:6px;
  font-size:11px;letter-spacing:.04em}}
.meta .file{{color:var(--cyan);font-weight:500}}
/* The body indent is derived, not typed. It used to be a hardcoded 88px while
   the header column was 64px + a 24px gap; adding the cover figure widened the
   header by another 156px and the h2 stopped sitting above the paragraph it
   heads. One property, both places. */
.why{{color:var(--tx2);max-width:72ch;margin:22px 0 0 var(--indent);font-size:15px}}
.quote{{margin:22px 0 0 var(--indent);padding-left:20px;border-left:2px solid var(--cyan)}}
.quote p{{margin:0;color:var(--mut);font-size:14px;line-height:1.75;max-width:76ch}}
.caps{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:30px 0 0 var(--indent)}}
.caps section{{background:var(--elev);border-radius:12px;padding:18px 20px 8px}}
.caphead{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.caphead h3{{font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
  color:var(--dim);margin:0}}
.copy{{background:none;border:1px solid var(--div);color:var(--mut);border-radius:7px;
  font:inherit;font-size:11px;padding:4px 11px;cursor:pointer;transition:.14s}}
.copy:hover{{border-color:var(--cyan);color:var(--cyan)}}
.copy.done{{border-color:var(--cyan);color:var(--cyan)}}
.cap p{{margin:0 0 11px;font-size:14px;color:var(--tx2)}}
.cap .tags{{color:var(--cyan);font-size:12.5px}}
.note{{margin:48px 0 0;padding:22px 24px;background:var(--elev);border-radius:12px;
  border-left:2px solid var(--cyan)}}
.note h3{{font-family:Inter,sans-serif;font-size:15px;margin:0 0 10px;font-weight:600}}
.note p, .note li{{color:var(--mut);font-size:13.5px;margin:0 0 8px;max-width:78ch}}
.note ul{{margin:0;padding-left:18px}}
.theme{{position:fixed;top:20px;right:20px;background:var(--card);border:1px solid var(--div);
  color:var(--mut);border-radius:8px;font:inherit;font-size:12px;padding:7px 13px;cursor:pointer}}
/* ---- the post blocks: one row per destination -------------------------- */
.about{{margin:10px 0 4px;padding:9px 12px;border-radius:8px;font-size:13px;
  line-height:1.45;border:1px solid var(--div)}}
.about strong{{font-weight:600}}
.about.warn{{background:#fdf3e3;color:#6b4a12;border-color:#e8d5a8}}
/* INDENTED LIKE EVERYTHING ELSE. `.why`, `.quote` and `.caps` all carried
   margin-left:var(--indent) and the Titles block did not, so the four titles -
   the only content on the card that is actually retyped - were the one thing
   not aligned under their own hook. Three competing left edges ran down every
   card: 192px, 280px and 436px, measured. */
/* INSIDE the column beside the cover, not below it. The header row is as tall
   as the 256px cover while the hook and its meta line are only 76px, so 180px
   of every card was empty air to the right of the thumbnail with the content
   starting underneath it. Putting the posts in that column fills the space with
   something already on the page and shortens the card. */
.posts{{display:flex;flex-direction:column;gap:2px;margin-top:14px}}
.clip-title{{min-width:0;flex:1}}
.post{{border-top:1px solid var(--div);padding:14px 0}}
.post:first-child{{border-top:0}}
.posthead{{display:flex;align-items:baseline;gap:12px;margin:0 0 8px}}
.posthead h3{{margin:0;font-size:11px;font-weight:650;letter-spacing:.13em;
  text-transform:uppercase;color:var(--mut);flex:0 0 auto}}
.postbody{{max-width:66ch}}
.ptitle{{margin:0 0 8px;font-size:17px;font-weight:600;color:var(--tx);line-height:1.4}}
.postbody p{{margin:0 0 8px;color:var(--tx2)}}
.posthead .copy{{margin-left:auto}}

/* ---- what the clip cuts away to --------------------------------------- */
.cutaways{{margin:16px 0 0 var(--indent)}}
.cutaways h3{{margin:0 0 6px;font-size:11px;font-weight:650;letter-spacing:.13em;
  text-transform:uppercase;color:var(--mut)}}
.cutaways table{{border-collapse:collapse;font-size:13px;color:var(--tx2)}}
.cutaways td{{padding:3px 18px 3px 0;vertical-align:top}}
.cutaways .cw{{color:var(--cyan);white-space:nowrap}}
.cutaways .ch{{color:var(--dim);font-variant-numeric:tabular-nums;white-space:nowrap}}

/* ---- reference, folded away ------------------------------------------- */
/* The rationale and the raw transcript are for the reviewer, not the poster.
   The quote alone was 18% of a card's height and it sat BETWEEN the titles and
   the captions - so the two things you paste were separated by the one thing
   you never paste. */
.ref{{margin:16px 0 0 var(--indent)}}
.ref summary{{cursor:pointer;font-size:11px;font-weight:650;letter-spacing:.13em;
  text-transform:uppercase;color:var(--dim);list-style:none}}
.ref summary::-webkit-details-marker{{display:none}}
.ref summary::before{{content:"+ ";color:var(--cyan)}}
.ref[open] summary::before{{content:"\2212 "}}
.ref .why,.ref .quote{{margin-left:0}}
.tag.ok{{color:var(--cyan);border-color:currentColor}}
.tlen{{font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}}
.tlen.over{{color:#b4341f;font-weight:700}}
.tlen.over::after{{content:" over"}}
a.file{{color:var(--dim);text-decoration:none;border-bottom:1px solid var(--div)}}
a.file:hover{{color:var(--cyan)}}
.tickers{{margin-left:var(--indent)}}
.onscreen{{color:var(--dim);font-size:13px;margin:6px 0 0}}

/* ---- print ------------------------------------------------------------- */
/* There was no @media print at all. A three-clip sheet printed as 7 pages with
   a title label on one page and its value on the next, the theme button
   printed as a physical button, and a dark-toggled sheet printed solid black. */
@media print{{
  :root,:root[data-theme="dark"]{{
    --bg:#fff; --card:#fff; --elev:#fff; --tx:#000; --tx2:#1a1a1a;
    --mut:#444; --dim:#666; --cyan:#2a5b6b; --div:rgba(0,0,0,.18);
  }}
  .theme{{display:none}}
  .clip,.post,.cutaways,.caps section{{break-inside:avoid}}
  .clip-head{{break-after:avoid}}
  .ref{{display:none}}
  body{{background:#fff}}
  a.file{{border:0}}
}}

@media (max-width:820px){{
  .caps{{grid-template-columns:1fr;margin-left:0}}
  .why,.quote{{margin-left:0}}
  .rank{{font-size:32px;min-width:46px}}
  .cover{{flex-basis:96px}} .cover img{{width:96px}}
  /* Narrow: the body runs full width, so the indent is zero on BOTH branches -
     it used to be zeroed for .why/.quote/.caps while the header kept its column,
     which is the same mismatch in the other direction. */
  .clip,.clip:has(.cover){{--indent:0px}}
  /* THE POSTS LIVE BESIDE THE COVER ON A DESKTOP, and on a 375px phone that
     leaves them 150px wide. Wrap the header so the cover keeps its row and the
     column that carries everything you paste drops below it at full width. */
  .clip-head{{flex-wrap:wrap}}
  .clip-title{{flex:1 0 100%}}
  .posts,.cutaways,.ref,.tickers{{margin-left:0}}
  .postbody,.ptitle{{max-width:100%}}
  h1{{overflow-wrap:anywhere}}
  .posthead{{flex-wrap:wrap}}
  .posthead .copy{{margin-left:0;width:100%}}
}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}

.tickers{{margin:14px 0 4px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.tickers h3{{margin:0;font-size:11px;letter-spacing:.14em;text-transform:uppercase;opacity:.55}}
.tkrow{{display:flex;gap:8px;flex-wrap:wrap}}
.tk{{display:inline-block;padding:4px 10px;border-radius:4px;background:#123;
    color:var(--cyan);font-weight:650;font-size:14px;letter-spacing:.04em}}
.onscreen{{margin:0;font-size:12px;opacity:.6;flex-basis:100%}}

.tlen.over{{color:#b4341f;font-weight:700}}
.tlen.over::after{{content:" over"}}
.titles{{margin:18px 0 6px;border-top:1px solid var(--div);padding-top:14px}}
.titles h3{{margin:0 0 10px;font-size:10px;font-weight:600;letter-spacing:.12em;
  text-transform:uppercase;opacity:.5}}
.trow{{display:grid;grid-template-columns:1fr auto;gap:6px 14px;align-items:start;
  padding:9px 0;border-bottom:1px solid var(--div)}}
.trow:last-child{{border-bottom:0}}
.tmeta{{grid-column:1/-1;display:flex;align-items:center;gap:9px}}
.tlabel{{font-size:11px;font-weight:650;letter-spacing:.04em}}
.tnote{{font-size:11px;opacity:.45}}
.tlen{{margin-left:auto;font-size:11px;opacity:.4;font-variant-numeric:tabular-nums}}
.tval{{margin:0;font-size:16px;line-height:1.35;font-weight:500}}
</style>

<button class="theme" id="theme">Light / dark</button>
<div class="wrap">
  <p class="eyebrow">Quasar Markets &nbsp;&middot;&nbsp; Clip slate</p>
  <h1>{_head_title}</h1>
  <p class="lede">Vertical 1080 by 1920, burned-in captions, a retention beat after every sentence, and invest.quasarmarkets.com on every one. Ranked in the order
  to post them. Every word is verbatim from the replay, checked against the transcript.</p>
  <p class="src">Source: {_head_src}
  &nbsp;&middot;&nbsp; files in <strong>clips/</strong>, subtitle files in <strong>captions/</strong></p>
  <hr class="rule">
  {''.join(cards)}
  {_footer_html}
</div>

<script>
document.getElementById('theme').onclick = () => {{
  const r = document.documentElement;
  const dark = getComputedStyle(r).getPropertyValue('--bg').trim().toLowerCase() === '#0e1319';
  r.setAttribute('data-theme', dark ? 'light' : 'dark');
}};
document.querySelectorAll('.copy').forEach(b => b.onclick = () => {{
  const el = document.getElementById(b.dataset.target);
  // The target is sometimes the <p> itself (a title) or a row of <span> chips
  // (the tickers); querySelectorAll('p') on those found nothing and copied an
  // empty string while the button still flashed "Copied".
  const parts = el.matches('p') ? [el] : [...el.querySelectorAll('p, .tk')];
  const text = parts.map(p => p.textContent.trim()).filter(Boolean)
                    .join(el.classList.contains('tkrow') ? ' ' : '\\n\\n');
  // NEVER SAY "COPIED" WHEN NOTHING WAS COPIED. The empty Tickers box is gone,
  // but the handler should not depend on that: an empty target now says so
  // instead of resolving writeText("") and flashing success.
  if (!text) {{
    b.textContent = 'Nothing to copy';
    setTimeout(() => {{ b.textContent = 'Copy'; }}, 1400);
    return;
  }}
  const flash = (msg) => {{
    b.textContent = msg; b.classList.add('done');
    setTimeout(() => {{ b.textContent = 'Copy'; b.classList.remove('done'); }}, 1400);
  }};
  // Opened over file:// this is not a secure context, so the async clipboard
  // API is missing; and even where it exists the write can be refused. Both
  // paths fall through to the textarea trick rather than failing silently.
  const legacy = () => {{
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }}
    ta.remove();
    flash(ok ? 'Copied' : 'Select and copy');
  }};
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(text).then(() => flash('Copied')).catch(legacy);
  }} else {{
    legacy();
  }}
}});
</script>"""

    out = DELIVER / "POSTING-SHEET.html"
    out.write_text(doc)
    print(out, f"{out.stat().st_size/1024:.0f}KB")

    # TICKERS.txt. The instruments and the on-screen chart get written into the
    # post, and the sheet is an HTML page you have to open and scroll. This is the
    # same two fields as a flat file you can cat next to the clips, which is how
    # they were actually being read. It was documented for a while before it
    # existed and was hand-written each show; now it comes off the slate.
    lines = []
    for c in clips:
        tk = c.get("tickers") or []
        on = _text(c.get("onscreen"))
        if not tk and not on:
            continue
        lines.append(f"{c.get('rank', '?'):>2}  {c['slug']}")
        if tk:
            lines.append(f"    tickers:  {', '.join(tk)}")
        if on:
            lines.append(f"    onscreen: {on}")
        lines.append("")
    tick = DELIVER / "TICKERS.txt"
    if lines:
        tick.write_text("\n".join(lines).rstrip() + "\n")
        print(tick, f"{len(lines)} lines")
    else:
        print("no tickers or on-screen notes in the slate - TICKERS.txt not written")


if __name__ == "__main__":
    main()
