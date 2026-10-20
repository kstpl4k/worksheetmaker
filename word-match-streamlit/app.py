"""LOTE4Kids Word Match Translator - Streamlit app.

Flow: upload PDFs -> click "Process translations" -> preview / download the translated PDFs.
"""
import io, os, zipfile
import pymupdf as fitz
import streamlit as st
import sheet, translator

st.set_page_config(page_title="Word Match Translator", page_icon="🔤", layout="centered")


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.environ.get(name, default)


# ---- optional password gate (set APP_PASSWORD in Streamlit secrets) ----------------------
pw = secret("APP_PASSWORD")
if pw and st.session_state.get("ok") is not True:
    entered = st.text_input("Password", type="password")
    if entered:
        if entered == pw:
            st.session_state["ok"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


WARN_NOTES = ("not found", "very long", "treated as", "No title line", "too long to fit")  # only these notes are shown


# ---- helpers --------------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Reading the translation sheet...")
def load_rows(url_or_id):
    return sheet.parse_rows(sheet.fetch_csv_text(url_or_id))


def preview_png(data, zoom=1.2):
    return fitz.open(stream=data, filetype="pdf")[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")


def human_size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


@st.dialog("Preview", width="large")
def preview_dialog(label, data):
    st.caption(label)
    img = preview_png(data, 1.6)
    try:
        st.image(img, width="stretch")
    except TypeError:  # older Streamlit versions
        st.image(img, use_container_width=True)


def build_plan(files, rows, col, lang_name):
    """Read the PDFs, group them by worksheet title (a batch can mix 'My Actions',
    'My Greengrocer - Fruit', ...) and look every group up in the sheet.
    Returns (plan, error). plan["errors"] lists everything missing from the sheet."""
    infos = []
    for f in files:
        try:
            infos.append(translator.analyze_pdf(f.getvalue(), f.name))
        except Exception as e:
            return None, f"Couldn't read {f.name}: {e}"
    missing = [f.name for f, i in zip(files, infos) if not i["category"]]
    if missing:
        return None, ("Couldn't find a title like 'My Actions - My Actions' or 'My Greengrocer - Fruit' in: "
                      + ", ".join(missing))
    groups = {}
    for idx, i in enumerate(infos):
        groups.setdefault(sheet.cat_key(i["category"]), []).append(idx)
    out, errors = [], []
    for key, idxs in groups.items():
        category = infos[idxs[0]]["category"]
        names = ", ".join(files[k].name for k in idxs)
        words = list(dict.fromkeys(w for k in idxs for w in infos[k]["words"]))
        changes_title = any(infos[k]["changes_title"] for k in idxs)
        title_tr, status = sheet.lookup_status(rows, col, category, words)
        found = {}
        if sheet.find_category(rows, category) is None:
            errors.append(f"Section '{category}' was not found in the Google Sheet ({names}). "
                          "Check that the heading in the sheet matches the worksheet title.")
        else:
            if changes_title and not title_tr:
                errors.append(f"'{category}' has no {lang_name} title translation in the Google Sheet.")
            for w in words:
                st_, val = status[w]
                if st_ == "no_row":
                    errors.append(f"'{w}' is missing from the '{category}' section of the Google Sheet.")
                elif st_ == "empty":
                    errors.append(f"'{w}' has no {lang_name} translation in the '{category}' section of the Google Sheet.")
                else:
                    found[w] = val          # cells with options ("direktè / direktris") keep all of them
        out.append({"category": category, "files": idxs, "words": words, "changes_title": changes_title,
                    "title": title_tr or "", "found": found})
    return {"infos": infos, "groups": out, "lang": lang_name, "errors": errors}, None


def default_values(plan):
    return [{"title": g["title"], "found": dict(g["found"])} for g in plan["groups"]]


def translate_all(files, plan, values, f_reg, f_bold, lang_name, known_langs):
    out, problems = {}, []
    todo = [(g, v, k) for g, v in zip(plan["groups"], values) for k in g["files"]]
    bar = st.progress(0.0, text="Processing...")
    for n, (g, v, k) in enumerate(sorted(todo, key=lambda t: t[2])):
        f, info = files[k], plan["infos"][k]
        words = {w: v["found"][w] for w in info["words"] if w in v["found"]}  # only this file's words
        try:
            data, mode, notes = translator.translate_pdf(
                f.getvalue(), f.name, words, v["title"].strip(), info["mode"],
                f_reg.getvalue() if f_reg else None, f_bold.getvalue() if f_bold else None)
            name = translator.localized_name(f.name, lang_name, known_langs)
            while name in out:                      # never overwrite another result
                name = name.replace(".pdf", "-2.pdf") if name.endswith(".pdf") else name + "-2"
            out[name] = (data, notes)
        except translator.GlyphError as e:
            problems.append(str(e))
        except Exception as e:  # noqa
            problems.append(f"{f.name}: {e}")
        bar.progress((n + 1) / len(todo), text=f"Processed {n + 1} of {len(todo)}")
    bar.empty()
    return out, problems


# ---- page -----------------------------------------------------------------------------------
st.title("Word Match Translator")

files = st.file_uploader("Upload worksheet PDFs", type="pdf", accept_multiple_files=True)
for f in files or []:
    c1, c2 = st.columns([5, 1])
    c1.write(f"📄 {f.name} ({human_size(f.size)})")
    if c2.button("👁 Preview", key=f"pu|{f.name}"):
        preview_dialog(f"Original: {f.name}", f.getvalue())

rows, load_error = None, None
with st.expander("Settings"):
    src = st.radio("Translation sheet", ["Google Sheet link", "Upload CSV"], horizontal=True)
    try:
        if src == "Google Sheet link":
            url = st.text_input("Google Sheet link", value=secret("SHEET_URL", sheet.DEFAULT_SHEET_ID))
            if url:
                rows = load_rows(url)
        else:
            up = st.file_uploader("Sheet CSV", type="csv", key="csv")
            if up:
                rows = sheet.parse_rows(up.getvalue().decode("utf-8-sig"))
    except Exception as e:
        load_error = str(e)
    st.divider()
    f_reg = st.file_uploader("Custom font, regular (.ttf), for non-Latin languages", type=["ttf", "otf"], key="fr")
    f_bold = st.file_uploader("Custom font, bold (.ttf, optional)", type=["ttf", "otf"], key="fb")

if load_error:
    st.error(load_error)
if not files or not rows:
    if not files:
        st.info("Upload a PDF to continue.")
    st.stop()

langs = sheet.languages(rows)
guess = sheet.guess_language(langs, files[0].name)
lang_idx = st.selectbox("Language", range(len(langs)), index=guess, format_func=lambda i: langs[i][1])
col, lang_name = langs[lang_idx]

# reset the results whenever the files or language change
sig = (tuple((f.name, f.size) for f in files), lang_name, src)
if st.session_state.get("sig") != sig:
    st.session_state["sig"] = sig
    st.session_state["stage"] = None
    for k in ("plan", "results", "errors"):
        st.session_state.pop(k, None)

# Process
if st.button("▶ Process translations", type="primary"):
    st.session_state["stage"] = None
    for k in ("plan", "results", "errors"):
        st.session_state.pop(k, None)
    try:
        if src == "Google Sheet link":
            load_rows.clear()                      # always use the latest version of the sheet
            rows = load_rows(url)
            col = next((c for c, n in sheet.languages(rows) if n == lang_name), col)
    except Exception as e:
        st.error(str(e))
        st.stop()
    plan, err = build_plan(files, rows, col, lang_name)
    if err:
        st.error(err)
    elif plan["errors"]:
        st.session_state["errors"] = plan["errors"]
        st.session_state["stage"] = "error"
    else:
        st.session_state["results"] = translate_all(files, plan, default_values(plan), f_reg, f_bold,
                                                    lang_name, [n for _, n in langs])
        st.session_state["stage"] = "done"

# Missing words: flagged as an error, nothing is processed until the sheet is fixed
if st.session_state.get("stage") == "error":
    errs = st.session_state["errors"]
    st.error("Can't process these files: the Google Sheet is missing translations.\n\n"
             + "\n".join(f"- {m}" for m in errs)
             + "\n\nFix the sheet, then click Process again. The latest version of the sheet is read each time.")

# 4. Results: preview + download
if st.session_state.get("stage") == "done" and st.session_state.get("results"):
    out, problems = st.session_state["results"]
    for p in problems:
        st.error(p)
    if out:
        st.success(f"Done: {len(out)} file{'s' if len(out) != 1 else ''} processed.")
    for name, (data, notes) in out.items():
        st.markdown(f"**{name}**")
        for n in dict.fromkeys(notes):
            if any(w in n for w in WARN_NOTES):
                st.warning(n)
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("👁 Preview", key=f"pr|{name}"):
            preview_dialog(f"Translated: {name}", data)
        b2.download_button("⬇ Download", data, file_name=name, mime="application/pdf", key=f"d|{name}")
    if len(out) > 1:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, (data, _) in out.items():
                z.writestr(name, data)
        st.download_button("⬇ Download all (zip)", buf.getvalue(), file_name="translated-worksheets.zip",
                           mime="application/zip")
