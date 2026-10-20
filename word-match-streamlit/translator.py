"""PDF logic for LOTE4Kids 'Match the Words' worksheets (activity sheet + answer key).

Two worksheet types:
- picture : words on the LEFT, pictures on the right. The left words are replaced.
- wtw     : 'word to word'. File name contains 'wtw' and the body has no pictures; English on
            both sides. ONLY the right-hand words are replaced.

Title (both types), when a title translation is given:
- title 'X - X' (e.g. 'My Actions - My Actions')  ->  'X - <translation>' on one line,
  or two lines 'X' / '<translation>' if one line would touch the picture frame or QR box.
- any other title (e.g. 'My Greengrocer - Fruit') ->  the title is kept exactly as it is and the
  translation is placed on a second line underneath it.
"""
import os, re
from itertools import combinations
from pathlib import Path
import pymupdf as fitz

FONT_DIR = Path(__file__).parent / "fonts"
PAD = 8.0  # min gap (pt) between the title text and the cover-picture frame / QR box
TITLE_XX = re.compile(r"^(.*\S)\s+-\s+\1$")  # 'My Actions - My Actions'
LINE_GAP = 1.25  # second-line spacing as a multiple of the font size


class GlyphError(Exception):
    pass


# spelling fixes applied when a language name is used in a file name (the sheet header says "Creaole")
LANG_FIX = {"creaole": "creole"}


def lang_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    for bad, good in LANG_FIX.items():
        s = s.replace(bad, good)
    return s


def localized_name(filename: str, language: str, known_languages=()) -> str:
    """'my-actions-word-match-english-activity.pdf' + 'Haitian Creole'
    -> 'my-actions-word-match-haitian-creole-activity.pdf'.
    The language already in the name ('english' or any language from `known_languages`) is replaced.
    If none is found, the language is added after 'word-match' (or at the end)."""
    stem, ext = os.path.splitext(filename)
    new = lang_slug(language)
    cands = sorted({"english"} | {lang_slug(l) for l in known_languages} - {""}, key=len, reverse=True)
    for c in cands:
        pat = re.compile(rf"(?<![a-z0-9]){re.escape(c)}(?![a-z0-9])", re.I)
        m = pat.search(stem)
        if m:
            before, after = stem[:m.start()], stem[m.end():]
            nt = new.split("-")
            for k in range(len(nt) - 1, 0, -1):        # 'english-creole' + Haitian Creole -> no doubled 'creole'
                tail = "-" + "-".join(nt[-k:])
                if after.lower().startswith(tail) and (len(after) == len(tail) or after[len(tail)] in "-_ "):
                    after = after[len(tail):]
                    break
            return before + new + after + ext
    m = re.search(r"(word-match-)(.+?)(-(?:activity|answer)\b)", stem, re.I)   # LOTE4Kids pattern
    if m:
        return stem[:m.start(2)] + new + stem[m.end(2):] + ext
    if "word-match" in stem:
        return stem.replace("word-match", f"word-match-{new}", 1) + ext
    return f"{stem}-{new}{ext}"


def default_fonts():
    return ((FONT_DIR / "LiberationSans-Regular.ttf").read_bytes(),
            (FONT_DIR / "LiberationSans-Bold.ttf").read_bytes())


def _body_images(page):
    """Pictures in the worksheet body (ignores cover frame, QR box and footer logo)."""
    return [im for im in page.get_image_info()
            if im["bbox"][1] > 140 and im["bbox"][3] < page.rect.height - 40]


def detect_mode(page, filename: str):
    """Returns (mode, warning or None)."""
    wtw_name = "wtw" in (filename or "").lower()
    has_pics = bool(_body_images(page))
    if wtw_name and not has_pics:
        return "wtw", None
    if wtw_name and has_pics:
        return "picture", "'wtw' is in the file name but the page has pictures, so it was treated as a picture sheet."
    if not has_pics:
        return "picture", "No pictures and no 'wtw' in the file name; treated as a picture sheet (left words)."
    return "picture", None


def _spans(page):
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                yield s


def _is_title_span(s):
    t = s["text"].strip()
    return bool(t) and "Bold" not in s["font"] and 14 <= s["size"] < 20 and s["bbox"][1] < 160 and " - " in t


def analyze_pdf(data: bytes, filename: str = ""):
    page = fitz.open(stream=data, filetype="pdf")[0]
    mode, warning = detect_mode(page, filename)
    mid_x = page.rect.width / 2
    title, words = None, []
    for s in _spans(page):
        t = s["text"].strip()
        if not t:
            continue
        if "Bold" in s["font"] and s["size"] >= 20:
            cx = (s["bbox"][0] + s["bbox"][2]) / 2
            if mode == "picture" or cx > mid_x:
                words.append((s["bbox"][1], t))
        elif _is_title_span(s):
            title = t
    m = TITLE_XX.match(title or "")
    return {
        "mode": mode,
        "warning": warning,
        "title": title,
        "title_is_xx": bool(m),
        "category": m.group(1) if m else title,
        "changes_title": bool(title),
        "words": [w for _, w in sorted(words)],
    }


def _frame_right(page):
    best = None
    for d in page.get_drawings():
        r = d["rect"]
        if d.get("color") == (0.0, 0.0, 0.0) and (d.get("width") or 0) >= 2 \
                and r.x0 < 120 and r.y0 < 150 and r.width > 40:
            best = r
    if best is not None:
        return best.x1 + 1.5
    for im in page.get_image_info():
        b = fitz.Rect(im["bbox"])
        if b.x0 < 120 and b.y0 < 150 and b.width > 60:
            return b.x1 + 3
    return 160.0


def _title_limits(page):
    """(left, right) x-limits for title text: clear of the cover frame and of the QR box."""
    left = _frame_right(page) + PAD
    right = page.rect.width - 30
    for d in page.get_drawings():
        r = d["rect"]
        if r.x0 > 400 and r.y1 < 140 and r.width < 150:
            right = min(right, r.x0 - PAD)
    for s in _spans(page):
        if s["bbox"][1] < 140 and s["text"].strip().lower().startswith("scan for"):
            right = min(right, s["bbox"][0] - PAD)
    return left, right


def _dot_edges(page):
    """(x0 of the left-column dots, x1 of the right-column dots) or (None, None)."""
    mid = page.rect.width / 2
    dots = [d["rect"] for d in page.get_drawings()
            if d.get("fill") and 5 < d["rect"].width < 14 and 5 < d["rect"].height < 14]
    left = [r.x0 for r in dots if r.x1 < mid]
    right = [r.x1 for r in dots if r.x0 > mid]
    return (min(left) if left else None, max(right) if right else None)


def _word_limits(page, on_right):
    """(left, right) x-limits for a word: clear of the matching dots and of the page margin."""
    d_left, d_right = _dot_edges(page)
    if on_right:
        return ((d_right + 12) if d_right else page.rect.width / 2 + 92), page.rect.width - 40
    return 45.0, ((d_left - 10) if d_left else 189.0)


def wrap_word(font, text, size, maxw, max_lines=3):
    """Fit `text` into `maxw`. Breaks ONLY at spaces (a word is never split). Uses as few lines
    as possible (balanced), and if a single word is still too wide, shrinks the font instead.
    Returns (lines, size, fits)."""
    tokens = []
    for t in text.split():
        if t == "/" and tokens:
            tokens[-1] += " /"          # 'direktè / direktris' wraps as 'direktè /' + 'direktris'
        else:
            tokens.append(t)
    if len(tokens) <= 1:
        tokens = [text.strip()]
    sz, best_fallback = size, None
    while True:
        for n in range(1, min(max_lines, len(tokens)) + 1):
            cands = []
            for cuts in combinations(range(1, len(tokens)), n - 1):
                bounds = (0,) + cuts + (len(tokens),)
                parts = [" ".join(tokens[a:b]) for a, b in zip(bounds, bounds[1:])]
                cands.append((max(font.text_length(p, sz) for p in parts), parts))
            w, parts = min(cands, key=lambda c: c[0])
            if best_fallback is None or w < best_fallback[0]:
                best_fallback = (w, parts, sz)
            if w <= maxw:
                return parts, sz, True
        if sz <= size * 0.6:
            return best_fallback[1], best_fallback[2], False
        sz *= 0.95


def _check(font, text):
    missing = sorted({c for c in text if not c.isspace() and not font.has_glyph(ord(c))})
    if missing:
        raise GlyphError(f"The font has no glyphs for {' '.join(missing)} in '{text}'. "
                         "Upload a font that supports this language (see 'Custom font').")


def translate_pdf(data: bytes, filename: str, words: dict, title_translation=None,
                  mode="auto", reg_font=None, bold_font=None):
    """words: {English: translation}. Returns (pdf_bytes, mode_used, notes)."""
    if reg_font is None and bold_font is None:
        reg_font, bold_font = default_fonts()
    elif bold_font is None:      # custom regular only: use it for bold too
        bold_font = reg_font
    elif reg_font is None:
        reg_font = bold_font
    fr, fb = fitz.Font(fontbuffer=reg_font), fitz.Font(fontbuffer=bold_font)
    words = {k.strip().lower(): v for k, v in words.items() if v}
    title_translation = (title_translation or "").strip()

    doc = fitz.open(stream=data, filetype="pdf")
    page = doc[0]
    notes = []
    if mode == "auto":
        mode, warn = detect_mode(page, filename)
        if warn:
            notes.append(warn)
    mid_x = page.rect.width / 2
    left, right = _title_limits(page)

    jobs, found, title_done = [], set(), False
    for s in _spans(page):
        t = s["text"].strip()
        on_right = (s["bbox"][0] + s["bbox"][2]) / 2 > mid_x
        if t.lower() in words and "Bold" in s["font"] and (mode == "picture" or on_right):
            jobs.append(("word", s, words[t.lower()])); found.add(t.lower())
        elif title_translation and not title_done and _is_title_span(s):
            jobs.append(("title", s, t)); title_done = True
    for w in sorted(set(words) - found):
        notes.append(f"Word '{w}' was not found on the page.")
    if title_translation and not title_done:
        notes.append("No title line was found, so the title was not changed.")

    # remove old text: all replaced words, and the title only when it is the 'X - X' kind
    for kind, s, val in jobs:
        if kind == "word" or TITLE_XX.match(val):
            page.add_redact_annot(fitz.Rect(s["bbox"]))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    page.insert_font(fontname="LSR", fontbuffer=reg_font)
    page.insert_font(fontname="LSB", fontbuffer=bold_font)

    for kind, s, val in jobs:
        size, y = s["size"], s["origin"][1]
        if kind == "word":
            cx = (s["bbox"][0] + s["bbox"][2]) / 2
            _check(fb, val)
            lim_l, lim_r = _word_limits(page, cx > mid_x)
            res = wrap_word(fb, val, size, 2 * min(cx - lim_l, lim_r - cx))     # centred on the original spot
            if res[1] < size or not res[2]:
                # still too big: allow the text to use the whole free space beside the dots
                alt = wrap_word(fb, val, size, lim_r - lim_l)
                if (alt[2], alt[1]) > (res[2], res[1]):                          # fits first, then larger font
                    res = alt
            lines, sz, fits = res
            widest = max(fb.text_length(ln, sz) for ln in lines)
            cx_draw = min(max(cx, lim_l + widest / 2), lim_r - widest / 2)      # smallest shift that stays clear
            lead = sz * 1.12
            for i, ln in enumerate(lines):
                base = y + (i - (len(lines) - 1) / 2) * lead      # block stays centred on the original line
                page.insert_text((cx_draw - fb.text_length(ln, sz) / 2, base), ln, fontname="LSB", fontsize=sz)
            if len(lines) > 1:
                notes.append(f"'{val}' was too long for one line, so it was split onto {len(lines)} lines "
                             "(at spaces only).")
            elif sz < size:
                notes.append(f"'{val}' was reduced in size to fit.")
            if not fits:
                notes.append(f"'{val}' is too long to fit next to the dots even after wrapping; check the preview.")
            continue

        tr = title_translation
        _check(fr, tr)
        m = TITLE_XX.match(val)
        base = m.group(1) if m else val
        cx = s["origin"][0] + fr.text_length(val, size) / 2   # centre of the visible title text

        def fits(w, c=cx):
            return c - w / 2 >= left and c + w / 2 <= right

        one_line = f"{base} - {tr}"
        if m and fits(fr.text_length(one_line, size)):
            page.insert_text((cx - fr.text_length(one_line, size) / 2, y), one_line, fontname="LSR", fontsize=size)
            notes.append("Title on one line.")
            continue

        # two lines: title on top (kept as is, or redrawn as 'X' for 'X - X' titles), translation below
        if m:
            page.insert_text((cx - fr.text_length(base, size) / 2, y), base, fontname="LSR", fontsize=size)
        sz = size
        while sz > size * 0.7 and not fits(fr.text_length(tr, sz)):
            sz *= 0.95
        if not fits(fr.text_length(tr, sz)):
            notes.append("The title translation is very long and may touch the picture frame or QR box; "
                         "check the preview.")
        page.insert_text((cx - fr.text_length(tr, sz) / 2, y + size * LINE_GAP), tr, fontname="LSR", fontsize=sz)
        notes.append("Title translation placed on a second line.")
    if mode == "wtw":
        notes.append("Word-to-word sheet: only the right-hand words were replaced.")
    return doc.tobytes(garbage=3, deflate=True), mode, notes
