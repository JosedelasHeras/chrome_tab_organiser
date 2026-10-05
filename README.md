# chrome_tab_organiser — User Guide

**chrome_report** (latest: `chrome_report_v1.4.py`)
— generate HTML (and JSON) reports of your open Chrome tabs, organised by tab group

**chrome_report_edit** (latest: `chrome_report_edit_v1.5.py`)
— a local web app to edit those reports: rename windows, groups & tabs, insert /
delete rows, **drag rows to reorder (within and across windows)**, sort groups
alphabetically, **import tabs straight from the running Chrome**, save under a
new name

*Self-contained tools — Python standard library only, nothing to install.
Pre-built Windows executables are included: `chrome_report_v1.4.exe` and
`chrome_report_edit_v1.5.exe`.*

> **Typical flow**
> 1. `python chrome_report_v1.4.py --json --outdir reports` → create the report(s).
> 2. `python chrome_report_edit_v1.5.py --dir reports` → open the editor in your browser.
> 3. Edit, drag rows into place, import the tabs you forgot to include, then
>    **Save as** a new name, e.g. `final_2026.html`.

---

## 1  The two tools

| | What it does | How to run |
|---|---|---|
| **chrome_report** | Reads Chrome's session files from disk (Chrome can stay running) and writes a self-contained HTML report (+ optional JSON) of every window, tab and tab group. | `python chrome_report_v1.4.py [options]` or `chrome_report_v1.4.exe [options]` |
| **chrome_report_edit** | Serves a localhost-only editor at `http://127.0.0.1:8765/`, shows the report exactly as it will look, and writes changes back to disk when you press **Save**. | `python chrome_report_edit_v1.5.py [options]` or `chrome_report_edit_v1.5.exe [options]` |

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

## 3  chrome_report_edit v1.5

### 3.1  Startup & options

```
python chrome_report_edit_v1.5.py [--dir PATH] [--port 8765] [--host 127.0.0.1] [--no-browser]
                                   [--no-chrome]
```

| Option | Meaning |
|---|---|
| `(none)` | Serves the `*.html` files in the script's (or exe's) folder and opens the browser automatically. |
| `--dir PATH` | Directory the editor manages and saves into. |
| `--port N` | Local port. Default `8765`. |
| `--host ADDR` | Bind address. Default `127.0.0.1` (loopback only). |
| `--no-browser` | Print the URL instead of auto-opening the browser. |
| `--no-chrome` | Switch the live Chrome import off; no session files are read at all. |

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
7. **Import tabs from Chrome** — see 3.5 (new in v1.5).
8. **Save** — see 3.6.

Statistics — windows · tabs · groups — update live as you edit.

### 3.3  Drag to reorder (new in v1.41)

- **Press and hold the ↕ grip** in a row's Group cell and move the mouse.
- Drag **up or down within a window**, or **into another window's table**.
- The row dims, a ghost of the whole row follows the pointer, and the target
  table is outlined.
- **Release anywhere over the table** — over a group chip, another row's grips,
  a tab link or a bare cell; the move commits. Above a row's midpoint inserts
  *before* it, below inserts *after* it, past the last row appends at the end
  (releasing over a link always places the tab just before the hovered row).
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

### 3.5  Importing tabs from the running Chrome (new in v1.5)

Each window header carries a green **Add tabs from window** button next to
**Add tab**. It copies tabs out of the Chrome you are actually using into the
window whose header you clicked — Chrome keeps running, nothing is closed, and
only its session-recovery files are read (exactly as the generator does).

1. Click **Add tabs from window** on the window that should receive the tabs.
2. The **Add tabs from Chrome** dialog opens with a live list:
   - **Chrome windows** — `Window 1`, `Window 2`, … with each one's tab and
     group count. Chrome has no user-assigned window names, so they are listed
     in tab-strip order and the one Chrome is showing now is marked *active*.
   - **Chrome tab groups** — every named group across all windows, with its tab
     count (e.g. `ChIP — 24 tabs`).
3. The line under the list previews how many tabs would be added and where they
   would land.
4. **Add tabs**.

| Source | Result |
|---|---|
| A Chrome window | Every tab in it, in Chrome's own tab-strip order |
| A named group | Every tab in that group, across all windows |

What comes across, and what does not:

- **Group name and colour** are preserved, so a chip looks the same as it does
  in Chrome.
- **Title and URL** are copied as they are. The active-window marker (star) is
  **not** imported — that mark belongs to the report's own window.
- **Tabs whose URL is already in the target window are skipped**, and the status
  bar says how many were skipped. Comparison ignores letter case, a trailing
  slash and `#fragment`, so `Example.com`, `example.com/` and `example.com#top`
  count as the same page.
- If Chrome legitimately has the same page open twice, both are imported — only
  what is *already in the report* is skipped. Importing the same window twice
  therefore adds nothing the second time.
- Grouped tabs are placed **alphabetically by their own group**, so importing
  keeps a sorted window sorted.

Where the imported tabs land:

| "sort groups alphabetically" | Placement |
|---|---|
| unticked (default) | Inserted at the **very beginning** of the target window, in Chrome's order |
| ticked | Inserted and the whole window re-sorted: ungrouped first, then groups A–Z |

Imported rows are ordinary rows: renumbered (`data-pos`), editable in place, and
draggable by their grip like any other.

If Chrome's session files cannot be read, the dialog says so and changes
nothing. The newest session file is often locked while Chrome is writing it —
that is normal, and the newest complete snapshot is used instead.

### 3.6  Saving

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
python chrome_report_edit_v1.5.py --dir reports

# 3) In the browser: load chrome_tabs_Default_v1.4.html
#    - click "Window 3" heading, type "Hi-C"
#    - press-and-hold the ↕ grip on a row, drag it into "Window 1", release
#    - remove stale rows with  x
#    - add a tab with + next to a row (group "ChIP", name "bioRxiv", URL)
#    - forgot a tab? "Add tabs from window" on that window's header,
#      pick a Chrome window or a Chrome group, then Add tabs

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

# 2) Double-click chrome_report_edit_v1.5.exe
#    (manages the folder the exe lives in and opens the browser itself)
#    or point it at the reports folder:
chrome_report_edit_v1.5.exe --dir reports

# 3) Load, edit, drag rows, import Chrome tabs, Save — as in workflow A.
```

### C  Sorting + drag interplay

```text
# load a report, tick "sort groups alphabetically"  -> groups A-Z per window
# decide one group sits better elsewhere:
#   press-and-hold its row's ↕ grip and drag it to the new spot
#   -> the sort box switches off automatically, your order is kept
# untick/re-tick to go back to alphabetical, then Save to keep that copy
```

### D  Filling a report from the live Chrome

```text
# You already made a report, but since then you opened more tabs in Chrome.
# Leave Chrome running, then in the editor:

# unsorted: the chosen Chrome window's tabs go to the top of the target
#   "Add tabs from window" -> Chrome windows -> Window 3 -> Add tabs
#   -> "Added 18 tabs from Window 3 (2 already in this window)."

# sorted: ticked, so each imported tab lands in its own group, A-Z
#   tick "sort groups alphabetically" first, then import a group
#   -> Chrome tab groups -> ChIP -> Add tabs
#   -> that window stays alphabetical

# Save as a new name; the imported rows are normal rows from then on
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
| **Add tabs from window** says the Chrome session is not available | Chrome's session folder wasn't found (usually a non-Default profile or Chrome for another OS account), or Chrome has no open windows. Start Chrome with a tab open and try again. |
| The imported list misses the newest tabs | Chrome had its newest session file locked while writing. The newest complete snapshot is used — close the dialog and click the button again after a moment. |
| Can I import if Chrome is closed? | Yes. The session files are read from disk, so a closed Chrome still works (its last saved session). |
| I don't want the editor touching Chrome at all | Start it with `--no-chrome`; the import button then reports the feature is disabled and no session file is opened. |
| The Chrome window names don't match my report's window names | Expected — Chrome has no window names, so the picker lists `Window 1…N` in tab-strip order and marks the active one. You always choose where the tabs go in the report. |
| Must Chrome be closed? Are the tools safe? | No, and yes: session files are only read, everything is localhost-only, and nothing is written except via an explicit **Save**. |

---

*chrome_tab_organiser — chrome_report_v1.4.py · chrome_report_edit_v1.5.py (Python 3, no external dependencies) · `_261005`*
