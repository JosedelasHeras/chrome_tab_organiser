# chrome_tab_organiser — version history

**Date suffix:** `_261005` · **Scope:** what each version added or changed
**Project:** `chrome_tab_organiser` — report generator, report editor and companion extension

Two tools version independently:

| Tool | Current version | Purpose |
|------|-----------------|---------|
| `chrome_report` | **v1.4** | Reads Chrome's session files and writes an HTML (+ JSON) tab report |
| `chrome_report_edit` | **v1.5** | Local web app that edits and saves those reports |
| `tab_organiser_ext` | **v1.4** | Optional Chrome extension: opens report windows/groups as real Chrome windows |

Everything is Python standard library only — no pip installs.
Current sources live in the project root; earlier versions are kept in `older stuff/`.
Dates are the file's creation/modification date.

---

## 1 · Report generator — `chrome_report`

### `chrome_report.py` — 2026-09-11 (first release)
- Reads Chrome's own session-recovery files (SNSS) while Chrome keeps running; no browser API needed.
- One self-contained HTML report **per Chrome profile**, tabs listed per window and organised by tab group (group | tab name | url) with colour chips, counts and the active-tab marker.
- Options: `--data-dir`, `--profile`, `--output`, `--json`, `--no-prompt`; window names taken from a prompt or auto-derived from the active tab title.

### `chrome_report_v1.py` — 2026-09-11
- Window headings normalised to **Window 1 … Window N**.
- Scans **every** Chrome profile found and writes a separate report (`chrome_tabs_<profile>_v1.html`) plus JSON.

### `chrome_report_v1.1.py` — 2026-09-11
- **Default profile only**; fixed output names `chrome_tabs_Default_v1.1.html` / `.json`.
- Options reduced to `--data-dir`, `--outdir`, `--json`; JSON mirrors the HTML structure.

### `chrome_report_v1.2.py` — 2026-09-12
- Interactive **keep / dismiss** prompt per window, showing its name, tab count, group count and the first 5 group names alphabetically (tab names fill any remaining slots, in window order).
- `--keep-all` skips all prompting and restores the v1.1 behaviour.

### `chrome_report_v1.3.py` — 2026-10-04
- **Filtering before prompting:** (1) windows with identical contents collapse to one, (2) windows whose tabs are entirely contained in a larger window are dropped in favour of it.
- Prompt keys: `d` = dismiss, Enter/`k` = keep as "Window N", anything else = use the typed text as the name.
- **Unique window names** — a duplicate gets a `_1`, `_2`, … suffix (case-insensitive).
- `--no-filter` turns the filtering off; `--keep-all` keeps everything without prompting.

### `chrome_report_v1.4.py` — 2026-10-04 — **current**
- `--preserve_order ON|OFF` (default **ON**) — tab strip order exactly as Chrome has it, so groups appear as contiguous runs; `OFF` lists ungrouped tabs first, then groups A–Z.
- **Window action bar:** "Open window (grouped)" opens a second browser window with that window's tabs (ungrouped first, then one block per group in Chrome's group order); **clicking a group chip** opens just that group.
- **Real Chrome windows** via the companion extension `tab_organiser_ext/` — opens a window or a single group as a real Chrome window with real tab groups (title + colour), sources untouched. When the extension is missing, a badge names it and links to `install.html`.
- Each row is tagged with `data-pos="1..N"` for the editor's renumbering.

---

## 2 · Report editor — `chrome_report_edit`

### `chrome_report_edit.py` — 2026-09-11 (first release)
- Local stdlib HTTP server (default `127.0.0.1:8765`) that opens a browser UI over the reports in a managed directory.
- **Rename** windows (click the heading), **edit in place** (group chip, tab name, URL), **delete** rows (`✕`, Ctrl+Backspace), **insert** an entry (window / position / group with suggestions / name / URL), **Save as** a user-named file.
- Report preview is sandboxed; nothing is written to disk until Save.
- Follow-up fix: picking a report from the list now actually opens it.

### `chrome_report_edit_v1.1.py` — 2026-09-11
- **Full-page layout** — controls on the side, the report preview filling the whole viewport (was a small strip at the top).

### `chrome_report_edit_v1.2.py` — 2026-09-11
- **"sort groups alphabetically"** tickbox, unticked by default (no behaviour change until ticked).
- Per window: ungrouped tabs first in their original order, then groups A–Z; unticking restores the exact previous order; Save writes the on-screen order.

### `chrome_report_edit_v1.3.py` — 2026-09-11
- **Case-insensitive sorting** — `ChIP` and `chip` sort adjacent instead of capitals separating from lowercase.
- **No reordering unless ticked** — load-time auto-sort removed; the box resets to unticked on every load, and only an explicit tick reorders.

### `chrome_report_edit_v1.4.py` — 2026-10-04
- **Drag to reorder** — press the ⠿ grip on a row and move it up/down inside a window or across into another window; `data-pos` is renumbered `1..N` after insert, delete, drag, sort and save.
- Legacy reports with no `data-pos` are never given one; editor controls (grip, `+`/`✕`, injected stylesheet) are stripped on save.
- **Defect:** in a real browser the drag never moved anything (see v1.41).

### `chrome_report_edit_v1.41.py` — 2026-10-04
- **Drag made to actually work** — found with genuine native mouse drags, not synthetic events:
  - the **grip itself is the drag source** (`draggable` set when the row is built); no `mousedown` handler and no `preventDefault`, which was suppressing drag initiation.
  - rows are never draggable, so editing text and clicking links in a row are untouched.
  - all `dragstart` DOM changes are **deferred with `setTimeout(0)`** (mutating the DOM there aborted the session).
  - `setDragImage` shows the whole row; buttons are pointer-transparent while dragging so hit-testing reaches the cells.
  - the move **commits on `dragend`**, which fires even where Chrome refuses to dispatch `drop` — releasing over a group chip, another grip, a tab link or a bare cell all commit.
- A real drag switches "sort groups alphabetically" off; a mere grip click leaves it alone.

### `chrome_report_edit_v1.5.py` — 2026-10-05 — **current**
- **Import tabs from the running Chrome session** — a green **"Add tabs from window"** button beside **"Add tab"** on every window header; that window is the import target.
- Source is the **live Chrome session**, read directly from Chrome's session-recovery files (the SNSS reader is embedded from `chrome_report_v1.4.py`) — read-only, Chrome never needs to close, and the report window is *not* the source.
- **Picker** lists Chrome's open windows as `Window 1…N` (tab-strip order, tab/group counts, active marker) and Chrome's named tab groups; Chrome windows have no names of their own.
- Imports tab title, URL, **group name and group colour** (`#5f6368` when a group has none); never imports the active-star.
- **Placement:** unticked sort → prepended at the top of the target window in source order; ticked sort → appended, then `sortGroups()` so the window stays globally A–Z.
- **Dedupe against the target window only** (normalised for case, trailing slash and `#fragment`) — duplicates *within* the source are kept, because Chrome may legitimately open the same URL twice.
- New endpoint `GET /api/live` and new startup flag `--no-chrome` (turns the feature off entirely).

---

## 3 · Companion extension — `tab_organiser_ext` v1.4 — 2026-10-04

- Chrome **Manifest V3** extension with `tabs` + `tabGroups` + `windows` permissions; no network, storage, background script or telemetry.
- Adds **"Open window in Chrome"** and **"Open group in Chrome"** buttons to a report — opens real Chrome windows with real tab groups (title and colour preserved). **Copies only** — never moves, closes or reorders the source windows.
- Needed because Chrome exposes no scripting API for creating tab groups in a running browser (CDP stops short, and Chrome has no remote debugging port here).
- Report-side fallbacks that need no extension: "Open window (grouped)" popup and clicking a group chip.
- Robustness: confirms before opening more than 40 tabs, adds `https://` to scheme-less URLs, collapses duplicates within one action, uses `about:blank` when all of a window's tabs are grouped, maps report colours onto Chrome's 8 group colours.
- Ships `install.html` (load-unpacked steps), `selftest.html` (six live API calls) and two test scripts — see §6.

---

## 4 · Executables

- **2026-09-12** — one-file **PyInstaller** builds introduced; `build_exe.py` added, editor gained a frozen-path guard (`BASE` from `sys.executable` when packaged).
- **2026-10-04 / 2026-10-05** — `build_exe.py` retargeted as versions moved on. It now builds `chrome_report_v1.4.exe` and `chrome_report_edit_v1.5.exe`; the frozen-guard anchor was updated to the v1.5 `--no-chrome` / `ALLOW_CHROME` block.
- `chrome_report_edit_v1.41.exe` is kept from the previous release for reference.

---

## 5 · Documentation

| Date | Documents |
|------|-----------|
| 2026-09-11 | `chrome_session_buddy_guide.html/.pdf` — first instructions (later superseded) |
| 2026-09-11 | `chrome_tab_organiser_guide_260911` + `chrome_tab_organiser_quick_guide_260911` — brand renamed to **chrome_tab_organiser**; guide 7 pp, quick guide 2 pp |
| 2026-09-12 | `chrome_tab_organiser_history.md` + `_condensed.md` — full/condensed session transcripts (now in `older stuff/`) |
| 2026-10-04 | `chrome_tab_organiser_v1_4_update_261004` + `v1_4_quick_guide_261004` — generator v1.4 |
| 2026-10-04 | `chrome_tab_organiser_v1_41_update_261004` + `v1_41_quick_guide_261004` — the drag fix |
| 2026-10-04 | `README.md` — single user guide for generator v1.4 + editor v1.41 |
| 2026-10-05 | **`chrome_tab_organiser_v1.4_v1.5_update_261005`** + **`_quick_guide_261005`** — combined v1.4/v1.5 guide (6 pp) and quick guide (3 pp), md + html + pdf |

All guides are print-ready HTML rendered to PDF with headless Chrome, and carry a 6-digit `YYMMDD` date suffix.

---

## 6 · Testing

| Date | Test | Covers |
|------|------|--------|
| 2026-10-04 | `test_editor_js.py` | Editor page driven in headless Chrome — **33 checks** at v1.41 (drag initiation, cross-window moves, `dragend`-only commits, `data-pos` renumbering, save stripping) |
| 2026-10-04 | `tab_organiser_ext/test_content_js.py` | Extension `content.js` against stub `chrome.*` APIs (20 API calls) |
| 2026-10-04 | `tab_organiser_ext/test_report_js.py` | Report page JS in headless Chrome |
| 2026-10-05 | `test_editor_js.py` (extended) | **58 checks** for v1.5 — 33 drag/regression + 25 import (`/api/live`, placement, dedupe, colours, `--no-chrome`) |
| 2026-10-05 | native CDP drag script | Real press → move → release over four release points; guards the v1.41 behaviour against regressions |

Typical gate: `py_compile` → `test_editor_js.py` → `test_content_js.py` → `test_report_js.py`.

---

## 7 · Repository

- **2026-09-12** — repository initialised; `README.md` added.
- **2026-10-04** — `.gitignore` added first (credentials, `__pycache__`, generated reports/JSON, `v1_out/`, …); generated outputs untracked; `README.md` updated for v1.4/v1.41; local history merged with the existing GitHub history (`-X ours`) and pushed to `github.com/JosedelasHeras/chrome_tab_organiser`.
- Credentials (`260912 - gh cred.txt`) and the push log (`261004_git_update.txt`) are ignored and were never committed.
- **Not yet committed:** the v1.5 editor, the `_261005` guide set, this history file, and the local reorganisation of historical files into `older stuff/`.
