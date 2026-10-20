"""Google Sheet / CSV helpers for the LOTE4Kids translation list."""
import csv, io, re, urllib.request, urllib.error
from difflib import get_close_matches

DEFAULT_SHEET_ID = "1sBeLApxE3AYowKCLFzkY6pupg7o7bxgXfRggijK2nO4"


def csv_url(url_or_id: str) -> str:
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url_or_id)
    sheet_id = m.group(1) if m else url_or_id.strip()
    g = re.search(r"[#&?]gid=(\d+)", url_or_id)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={g.group(1) if g else '0'}"


def fetch_csv_text(url_or_id: str) -> str:
    """Download the sheet as CSV. Must be shared as 'Anyone with the link can view'."""
    req = urllib.request.Request(csv_url(url_or_id), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get("Content-Type", "")
            data = r.read().decode("utf-8-sig")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google returned HTTP {e.code}. Check the link and that the sheet is shared "
                           "as 'Anyone with the link can view'.") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Google Sheets: {e.reason}") from e
    if "csv" not in ctype and data.lstrip().lower().startswith("<!doctype html"):
        raise RuntimeError("The sheet is private (Google sent a login page). Set sharing to "
                           "'Anyone with the link can view', or upload the sheet as a CSV instead.")
    return data


def parse_rows(text: str):
    return [row for row in csv.reader(io.StringIO(text))]


def languages(rows):
    """[(column index, header name)] for each column after the English one."""
    return [(i, h.strip()) for i, h in enumerate(rows[0]) if i > 0 and h.strip()]


def guess_language(langs, hint: str):
    """Index into `langs` that best matches a file-name hint such as 'haitian-creole'."""
    hint = re.sub(r"[^a-z]+", " ", hint.lower()).strip()
    names = {re.sub(r"[^a-z]+", " ", n.lower()).strip(): i for i, (_, n) in enumerate(langs)}
    for n, i in names.items():
        if n and n in hint:
            return i
    for n, i in names.items():  # word-level fuzzy match (handles the 'Creaole' typo)
        for w in hint.split():
            if len(w) > 3 and get_close_matches(w, n.split(), n=1, cutoff=0.8):
                return i
    return 0


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").lower()).strip()
    return re.sub(r"\s*\d+$", "", s)  # 'zero 0' -> 'zero'


def cat_key(s: str) -> str:
    """Category headings: the sheet writes 'My Greengrocer: Fruit', PDFs write 'My Greengrocer - Fruit'."""
    return re.sub(r"\s*[:\-\u2013]\s*", " - ", norm(s))


def find_category(rows, category: str):
    key = cat_key(category)
    return next((i for i, r in enumerate(rows) if r and cat_key(r[0]) == key), None)


def lookup(rows, col: int, category: str, words):
    """(title_translation, {word: translation or None}) using ONLY the block that starts at the
    category row and ends at the next row beginning with 'My '."""
    start = find_category(rows, category)
    if start is None:
        return None, {w: None for w in words}
    end = next((i for i in range(start + 1, len(rows)) if rows[i] and norm(rows[i][0]).startswith("my ")), len(rows))
    block = {}
    for r in rows[start + 1:end]:
        if not r or col >= len(r) or not r[col].strip():
            continue
        key = norm(r[0])
        block.setdefault(key, r[col].strip())
        for part in key.split(" / "):
            block.setdefault(part.strip(), r[col].strip())
    title = rows[start][col].strip() if col < len(rows[start]) else None
    return title or None, {w: block.get(norm(w)) for w in words}


def lookup_status(rows, col: int, category: str, words):
    """Like lookup(), but says why a word is missing.
    Returns (title_translation, {word: (status, value)}) where status is
    'ok', 'no_section' (section heading not in the sheet), 'no_row' (word not listed in the section)
    or 'empty' (word listed but the language cell is blank)."""
    start = find_category(rows, category)
    if start is None:
        return None, {w: ("no_section", None) for w in words}
    end = next((i for i in range(start + 1, len(rows)) if rows[i] and norm(rows[i][0]).startswith("my ")), len(rows))
    block = {}
    for r in rows[start + 1:end]:
        if not r or not r[0].strip():
            continue
        val = r[col].strip() if col < len(r) else ""
        key = norm(r[0])
        for k in {key, *[p.strip() for p in key.split(" / ")]}:
            block.setdefault(k, val)
    out = {}
    for w in words:
        k = norm(w)
        out[w] = ("no_row", None) if k not in block else (("ok", block[k]) if block[k] else ("empty", None))
    title = rows[start][col].strip() if col < len(rows[start]) else ""
    return title or None, out
