# Word Match Translator (Streamlit)

Translates LOTE4Kids "Match the Words" worksheet PDFs (activity sheet + answer key).

- **Picture sheets**: replaces the left-hand words.
- **Word-to-word sheets** (`wtw` in the file name, no pictures): replaces only the right-hand words.
- **Titles (both types)**: `My Actions - My Actions` becomes `My Actions - Aksyon Mwen` (or two lines if it would touch the picture frame or QR box). Any other title, such as `My Greengrocer - Fruit`, is kept as is and the translation goes on a second line underneath.
- Words come from the "picture cards translation list" Google Sheet, looked up only inside the matching section. `My Greengrocer: Fruit` (sheet) and `My Greengrocer - Fruit` (PDF) are treated as the same.

## How it works
1. **Upload** the worksheet PDFs (activity and/or answer key). You can upload sets with different titles together, e.g. My Actions and My Greengrocer - Fruit; each title is looked up in its own sheet section. Any number of files; no size limit is set by the app (`.streamlit/config.toml` raises Streamlit's 200 MB default to 2048 MB; the server's memory is the real ceiling, about 1 GB on the free plan).
2. The Google Sheet is read automatically and the language is guessed from the file name (change it in the dropdown if needed).
3. Click **▶ Process translations**. The app looks up every word and the title in the sheet and translates all the PDFs in one go. Nothing is processed until you click.
4. If anything is missing from the Google Sheet, the app shows an **error** listing exactly what is wrong and processes nothing: a word that isn't listed in its section, a word with an empty translation cell, a section heading that isn't in the sheet, or a missing title translation. A cell with several options, such as "direktè / direktris", is not an error: all the options are kept. Fix the sheet and click **Process** again; the app re-reads the latest sheet each time you click.
5. Translated files are named by swapping the language in the file name for the chosen one (`my-actions-word-match-english-activity.pdf` becomes `my-actions-word-match-haitian-creole-activity.pdf`).
6. **Preview** (large pop-up) and **Download** each translated PDF, or **Download all (zip)**. Uploaded PDFs also have a Preview button for the original.

## Deploy free on Streamlit Community Cloud

1. **GitHub:** create a repo and upload the contents of this folder (`app.py`, `translator.py`, `sheet.py`, `requirements.txt`, `fonts/`, `.streamlit/`). `fonts/` must be included.
2. Go to https://share.streamlit.io, **Continue with GitHub**, and authorize.
3. Click **Create app**, choose your repo, branch `main`, main file path `app.py`. Pick a subdomain if you like.
4. **Advanced settings > Secrets** (optional):
   ```toml
   APP_PASSWORD = "choose-a-password"
   SHEET_URL = "https://docs.google.com/spreadsheets/d/1sBeLApxE3AYowKCLFzkY6pupg7o7bxgXfRggijK2nO4/edit?gid=0"
   ```
5. Click **Deploy** and wait for the build.
6. Share the app's Google Sheet as "Anyone with the link can view" (or use the app's **Upload CSV** option).
7. To limit who can open the app, use the app's Share settings (the free plan allows one private app), or rely on `APP_PASSWORD`.

## Run on your own computer
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes
- Free apps sleep after a period without visitors; the first visit afterwards takes a moment.
- Built-in font: Liberation Sans (SIL Open Font License), Latin scripts with accents. For other scripts upload a font under "Custom font"; right-to-left and complex scripts are untested.
- PyMuPDF is licensed under AGPL. Fine for a private internal tool; check the licence terms (or PyMuPDF's commercial licence) before making the app public.
