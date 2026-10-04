# chrome_tab_organiser — User Guide

**chrome_report** (latest: `chrome_report_v1.4.py`)
— generate HTML (and JSON) reports of your open Chrome tabs, organised by tab group

**chrome_report_edit** (latest: `chrome_report_edit_v1.41.py`)
— a local web app to edit those reports: rename windows, groups & tabs, insert /
delete rows, **drag rows to reorder (within and across windows)**, sort groups
alphabetically, save under a new name

*Self-contained tools — Python standard library only, nothing to install.
Pre-built Windows executables are included: `chrome_report_v1.4.exe` and
`chrome_report_edit_v1.41.exe`.*

> **Typical flow**
> 1. `python chrome_report_v1.4.py --json --outdir reports` → create the report(s).
> 2. `python chrome_report_edit_v1.41.py --dir reports` → open the editor in your browser.
> 3. Edit, drag rows into place, then **Save as** a new name, e.g. `final_2026.html`.

---

## 1  The two tools

| | What it does | How to run |
|---|---|---|
| **chrome_report** | Reads Chrome's session files from disk (Chrome can stay running) and writes a self-contained HTML report (+ optional JSON) of every window, tab and tab group. | `python chrome_report_v1.4.py [options]` or `chrome_report_v1.4.exe [options]` |
| **chrome_report_edit** | Serves a localhost-only editor at `http://127.0.0.1:8765/`, shows the report exactly as it will look, and writes changes back to disk when you press **Save**. | `python chrome_report_edit_v1.41.py [options]` or `chrome_report_edit_v1.41.exe [options]` |

Both run on Windows, macOS and Linux (the `.exe` files are Windows-only), never
talk to any external service, and modify nothing on disk except via an explicit
**Save** in the editor.

---

## 2  chrome_report v1.4

### 2.1  What it does

Reads the **Default** profile's session-recovery files (the SNSS format that
Chrome writes continuously into `<data dir>\Default\Sessions\`) and produces a
report in which every window lists its tabs in three columns: **Group** (colour
chips matching Chrome's own colours, blank when ungrouped), **Tab** and **URL**
(both clickable). Duplicate/contained windows are filtered out; each remaining
window is then kept, dismissed or named interactively in the terminal. The
active window and active tab are marked with a star.

### 2.2  Usage & options

```
python chrome_report_v1.4.py [--data-dir PATH] [--outdir PATH] [--json]
                             [--keep-all] [--no-filter]
                             [--preserve_order ON|OFF]
```

| Option | Meaning |
|---|---|
| `(none)` | Auto-detect the Chrome data directory, prompt interactively, write into the current folder. |
| `--data-dir PATH` | Chrome "User Data" directory instead of auto-detect (Windows: `%LOCALAPPDATA%\Google\Chrome\User Data`). |
| `--outdir PATH` | Output directory (created if missing). Default: current folder. |
| `--json` | Additionally write the parsed data as JSON. |
| `--keep-all` | Keep every window with its default name — no interactive prompting (use this in scripts). |
| `--no-filter` | Keep every window Chrome has open (no duplicate/contained filtering). |
| `--preserve_order ON` | **(default)** Tabs listed exactly in Chrome's tab-strip order, so groups appear as the contiguous runs Chrome had. |
| `--preserve_order OFF` | Ungrouped tabs first, then groups A–Z. |

### 2.3  Output files

Written into `--outdir`: `chrome_tabs_Default_v1.4.html` (self-contained report —
inline CSS, safe to share or archive) and, with `--json`,
`chrome_tabs_Default_v1.4.json` (profile, files, groups, windows with tabs).

### 2.4  Window actions & the optional extension

Every window header in the report has an action bar:

- **"Open window (grouped)"** opens that window's tabs in a second browser
  window — ungrouped tabs first, then one block per group;
- each **group chip** can be clicked to open just that group in a second window.

If the companion extension in `tab_organiser_ext\` is installed (unpacked —
steps in `tab_organiser_ext\install.html`), the same buttons open **real Chrome
windows with real tab groups** (name and colour preserved). The source windows
are never touched — it copies, never moves or closes. Without the extension a
badge at the top of the report links to the install steps.

### 2.5  Notes

- Chrome can keep running; nothing is closed or modified.
- `warning: skipped (…, in use by Chrome)` — the newest session file was
  mid-write. The report still contains the previous complete snapshot; re-run
  after a few seconds for the very latest state.

---

## 3  chrome_report_edit v1.41

### 3.1  Startup & options

```
python chrome_report_edit_v1.41.py [--dir PATH] [--port 8765] [--host 127.0.0.1] [--no-browser]
```

| Option | Meaning |
|---|---|
| `(none)` | Serves the `*.html` files in the script's (or exe's) folder and opens the browser automatically. |
| `--dir PATH` | Directory the editor manages and saves into. |
| `--port N` | Local port. Default `8765`. |
| `--host ADDR` | Bind address. Default `127.0.0.1` (loopback only). |
| `--no-browser` | Print the URL instead of auto-opening the browser. |

A browser tab opens at `http://127.0.0.1:8765/`. Pick a report from the
**dropdown** and press **Load**, or click **Open…** to load any `.html` file.
Press `Ctrl+C` in the terminal to stop the server.

### 3.2  Editing capabilities

1. **Rename windows** — click any "Window N" heading.
2. **In-place edits** — click a group chip, tab title or URL text and type.
   Clearing a group name ungroups the tab; editing a URL updates its link and
   tooltip too.
3. **Delete rows** — the **×** button on a row (or `Ctrl/⌘+Backspace` while a
   row is focused).
4. **Insert rows** — **+** on a row (after that row) or **Add tab** in a window
   header (at the end). The dialog asks for window, position, optional group
   (existing names auto-suggested, colour reused), tab name and URL.
5. **Drag rows to reorder** — see 3.3.
6. **Sort groups alphabetically** — see 3.4.
7. **Save** — see 3.5.

Statistics — windows · tabs · groups — update live as you edit.

### 3.3  Drag to reorder (new in v1.41)

- **Press and hold the ↕ grip** in a row's Group cell and move the mouse.
- Drag **up or down within a window**, or **into another window's table**.
- The row dims, a ghost of the whole row follows the pointer, and the target
  table is outlined.
- **Release anywhere over the table** — over a group chip, another row's grips,
  a tab link or a bare cell; the move commits. Above a row's midpoint inserts
  *before* it, below inserts *after* it, past the last row appends at the end.
- Drags start **only from the grip** — clicking text still edits it, links stay
  clickable, and rows are never accidentally dragged.

### 3.4  Sorting tab groups alphabetically

The toolbar checkbox affects the *current* report only, and only when you tick
it: within each window, ungrouped tabs first (keeping their order), then groups
A–Z (case-insensitive). **Untick restores the original order exactly.**
Loading a report always shows its saved order, with the box reset to unticked.

**An actual drag switches the box off automatically**, so your manual order
wins; merely clicking the grip does not. Inserting while sorted places the row
where the dialog says and does not re-sort it.

### 3.5  Saving

Nothing is written to disk until you press **Save** (or `Enter` in the name
box). Names must be simple `*.html` file names — paths, slashes and traversal
attempts are rejected by the server; the file is always written inside the
managed directory. On success the status bar shows the full path and byte count
and the file appears in the dropdown.

Rows are renumbered (`data-pos` = 1..N) after every insert, delete, drag, sort
and save. Reports that load without `data-pos` keep it that way.

---

## 4  Workflow examples

### A  Python files

```text
# 1) Generate the report for the Default profile, with JSON, into .\reports
python chrome_report_v1.4.py --json --outdir reports
#    (answer the window prompts; or add --keep-all to accept all defaults)

# 2) Open the editor pointed at that folder (browser opens automatically)
python chrome_report_edit_v1.41.py --dir reports

# 3) In the browser: load chrome_tabs_Default_v1.4.html
#    - click "Window 3" heading, type "Hi-C"
#    - press-and-hold the ↕ grip on a row, drag it into "Window 1", release
#    - remove stale rows with  x
#    - add a tab with + next to a row (group "ChIP", name "bioRxiv", URL)

# 4) Type "final_2026.html" in the name box and press Save
#    -> reports\final_2026.html is written and listed in the dropdown

# 5) Open the saved file (or keep editing it in the editor)
start reports\final_2026.html
```

### B  Executables (no Python required)

```text
# 1) Double-click chrome_report_v1.4.exe
#    (a console opens for the window prompts; the report lands next to the exe)
#    or from a terminal, hands-free:
chrome_report_v1.4.exe --keep-all --json --outdir reports

# 2) Double-click chrome_report_edit_v1.41.exe
#    (manages the folder the exe lives in and opens the browser itself)
#    or point it at the reports folder:
chrome_report_edit_v1.41.exe --dir reports

# 3) Load, edit, drag rows, Save — exactly as in workflow A.
```

### C  Sorting + drag interplay

```text
# load a report, tick "sort groups alphabetically"  -> groups A-Z per window
# decide one group sits better elsewhere:
#   press-and-hold its row's ↕ grip and drag it to the new spot
#   -> the sort box switches off automatically, your order is kept
# untick/re-tick to go back to alphabetical, then Save to keep that copy
```

---

## 5  Troubleshooting & FAQ

| Symptom / question | Answer |
|---|---|
| `warning: skipped (…, in use by Chrome)` | Chrome was mid-write on its newest session file. The report still shows the previous complete snapshot; re-run after a few seconds. |
| "Default profile not found" | Point `--data-dir` at the right "User Data" directory, or run on the machine that uses this Chrome profile. |
| "Address already in use" when starting the editor | Port 8765 is busy — run with `--port 9000` (any free port). |
| Editor dropdown is empty | It lists `*.html` in `--dir` only. Start with the folder holding your report, or use **Open…**. |
| A drag doesn't start | Drags begin only from the **↕ grip** in the Group cell — press, hold, move. Clicking the text still edits it. |
| Report looks reordered on its own | It shouldn't: loading always shows the saved order and the sort box resets. Untick restores the current session's original order; re-load to be sure. |
| Must Chrome be closed? Are the tools safe? | No, and yes: session files are only read, everything is localhost-only, and nothing is written except via an explicit **Save**. |

---

*chrome_tab_organiser — chrome_report_v1.4.py · chrome_report_edit_v1.41.py (Python 3, no external dependencies) · `_261004`*
