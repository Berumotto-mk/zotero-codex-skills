---
name: zotero-arxiv-pdf2zh
description: Save arXiv papers into a specified Zotero collection, usually through Zotero's local Connector API and with the user's preferred browser as a manual fallback, then translate the saved PDF with the local zotero-pdf2zh server. Use when the user gives a paper title or arXiv URL and a Zotero destination such as "vla/recent", asks to fetch/capture papers into Zotero, asks to run pdf2zh on Zotero PDFs, or needs multi-computer Zotero sync-safe paper intake.
---

# Zotero arXiv PDF2ZH

Use this skill to intake one or more arXiv papers into Zotero, place them in the requested collection path, translate the PDF through the user's local `zotero-pdf2zh` server, and avoid sync conflicts across multiple computers.

## Local Assumptions

- Zotero Desktop local API and Connector run at `http://127.0.0.1:23119`.
- The Zotero pdf2zh server folder defaults to `~/Documents/zotero-pdf2zh/server`.
- The pdf2zh web service normally runs at `http://127.0.0.1:8890` unless Zotero/prefs show a different port.
- Prefer the helper's automatic Zotero Connector save for arXiv capture. Use the user's preferred browser plus manual Zotero Connector clicking only as a fallback when the local Connector save endpoint cannot capture the item or attachment.

## Portable Configuration

The helper is portable across computers if these defaults match the target machine:

- `ZOTERO_LOCAL_BASE_URL`: Zotero local API and Connector base URL. Default: `http://127.0.0.1:23119`.
- `PDF2ZH_BASE_URL`: pdf2zh web service base URL. Default: `http://127.0.0.1:8890`.
- `PDF2ZH_SERVER_DIR`: local pdf2zh server folder. Default: `~/Documents/zotero-pdf2zh/server`.
- `PDF2ZH_TRANSLATED_DIR`: folder where pdf2zh writes generated files. Default: `$PDF2ZH_SERVER_DIR/translated`.
- `ZOTERO_DATA_DIR`: Zotero data directory containing `zotero.sqlite` and `storage/`. Default: `~/Zotero`.
- `ZOTERO_APP_NAME`: application name used by `open -a` after an automatic close/reopen. Default: `Zotero`.

On a second computer, export only the variables that differ from the defaults before running helper commands. The browser does not need an environment variable because the automatic path uses Zotero's local Connector API; browser choice matters only for manual fallback instructions.

## Workflow

1. Normalize the request:
   - Extract paper title or arXiv URL/id.
   - Extract Zotero collection path exactly, such as `vla/recent`.
   - Treat collection path segments case-insensitively for matching, but report the actual Zotero names.
2. Preflight Zotero:
   - Run the Zotero skill helper status command if available.
   - Run this skill's helper `status --collection "path"` to check local API, Connector, selected Zotero target, collection existence, and pdf2zh health.
   - If the selected target is not the requested collection, ask the user to select that collection in Zotero before using manual browser Connector fallback. Do not save into the wrong collection and move later unless the user explicitly approves.
3. Resolve the arXiv paper:
   - Search the web or arXiv for the exact title.
   - Prefer the canonical `https://arxiv.org/abs/<id>` page. Use the PDF URL only for verification or fallback.
4. Capture with Zotero Connector:
   - First run `scripts/zotero_arxiv_pdf2zh.py save-arxiv "https://arxiv.org/abs/<id>" --collection "path"` to fetch arXiv metadata and send it to Zotero through the local Connector API.
   - The helper uses punctuation-insensitive title matching, so Zotero titles such as `AHA-WAM:Asynchronous...` still match user titles written as `AHA-WAM: Asynchronous...`.
   - Verify a PDF attachment exists with `attachments --title "..."`.
   - If automatic Connector capture fails, open the canonical arXiv abs page in the user's preferred browser, tell the user to click the Zotero Connector save button, then wait with `wait-item`.
5. Translate:
   - Ensure the local pdf2zh server is running. If not, start it from `$PDF2ZH_SERVER_DIR` or `~/Documents/zotero-pdf2zh/server` with `python3 server.py --port 8890` when the user wants translation performed now.
   - Run `translate --title "..." --collection "..."`.
   - The helper uploads the Zotero PDF to `/translate`, requests both dual and mono outputs, reports generated files from the server's `translated/` folder, and attaches generated PDFs back under the Zotero parent item by default.
   - Generated attachments are titled `pdf2zh zh-CN dual PDF` for bilingual output and `pdf2zh zh-CN mono PDF` for pure Chinese output.
   - If a translated PDF of the same output type already exists under the parent item, the helper reports `exists` and does not add a duplicate.
   - If Zotero keeps the local database locked while attaching an already-generated file, close Zotero and rerun `attach-translated`; the helper creates a timestamped `zotero.sqlite.codex-backup-*` before writing.
   - For an end-to-end automated run, pass `--auto-close-zotero`; the helper will quit Zotero only if needed to release the database lock, attach the translated PDF, and reopen Zotero.
6. Sync-safe finish:
   - Verify the Zotero item appears in the requested collection.
   - Verify the translated files exist locally.
   - Prompt the user to let Zotero finish syncing on the current computer before switching computers if Zotero reports active sync, attachment download, or upload activity in the UI.

## Sync Rules for Multiple Computers

- Do only one active intake/edit per paper at a time. Avoid saving the same paper separately on multiple computers.
- Before starting, confirm Zotero sync is idle on the current computer and the requested collection exists locally.
- After saving and translating, leave Zotero open until the new item, PDF attachment, notes, and translated attachment or files finish syncing.
- If the same paper already exists, reuse the existing item and add it to the requested collection instead of creating a duplicate.
- If attachment sync is not complete, do not run translation on a placeholder attachment. Wait until the local PDF path resolves and exists.
- If a collection path is ambiguous, stop and ask the user to disambiguate.

## Helper Script

Use:

```bash
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py status --collection "vla/recent"
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py save-arxiv "https://arxiv.org/abs/2606.09811" --collection "vla/recent"
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py wait-item --title "Paper Title" --collection "vla/recent"
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py attachments --title "Paper Title" --collection "vla/recent"
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py translate --title "Paper Title" --collection "vla/recent" --auto-close-zotero
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py attach-translated --title "Paper Title" --collection "vla/recent" --pdf "/path/to/translated.dual.pdf" --auto-close-zotero
python3 ~/.codex/skills/zotero-arxiv-pdf2zh/scripts/zotero_arxiv_pdf2zh.py attach-translated --title "Paper Title" --collection "vla/recent" --pdf "/path/to/translated.mono.pdf" --auto-close-zotero
```

Read `references/pdf2zh-request.md` only when adjusting translation payload fields.

## Fallbacks

- If automatic Connector capture fails, provide concise manual steps for the user's preferred browser and keep monitoring Zotero with `wait-item`.
- If Zotero Connector is unavailable but the user approves a fallback, import a BibTeX/RIS record into the selected collection, then attach the arXiv PDF manually or through Zotero's "Find Available PDF" behavior.
- If pdf2zh server is down and starting it would need installation, environment setup, or network access, report the blocker and leave the Zotero capture complete.
