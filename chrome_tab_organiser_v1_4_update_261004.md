# chrome\_tab\_organiser — v1.4 Editor Update

**Feature release:** drag-to-reorder tabs in `chrome_report_edit`
**Date suffix:** `_261004`
**Applies to:** `chrome_report_edit_v1.4.py` (editor), `chrome_report_v1.4.py` (report generator)

Self-contained tools — Python standard library only, no dependencies to install.

---

## 1. What is new in v1.4

Version 1.4 of the report editor adds **drag-and-drop reordering of tabs**:

- Grab the **⠿ grip** on any tab row and drag it **up or down** to change its position
  inside the window.
- Drag a row **into any other window** to move that tab between windows.
- The dragged row is dimmed while in flight, and the target window's table is
  outlined so you can see where it will land.
- Row positions (`data-pos`) are renumbered automatically after every change, so
  saved reports stay internally consistent.

Everything from v1.3 still works exactly as before: renaming windows and groups,
editing tab titles and URLs, inserting rows, deleting rows, alphabetical group
sorting, and saving under a new name.

---

## 2. Files

| File | Purpose |
|------|---------|
| `chrome_report_edit_v1.4.py` | The editor. Run this. |
| `chrome_report_edit_v1.4.exe` | Standalone editor, no Python needed. |
| `chrome_report_edit_v1.3.py` | Previous editor, kept for reference. Unchanged. |
| `chrome_tabs_Default_v1.4.html` | Example report produced by the v1.4 generator. |
| `test_editor_js.py` | Headless test suite for the editor (25 checks). |

Older versions (`chrome_report_edit.py`, `_v1.1.py`, `_v1.2.py`, `_v1.3.py`) are
untouched, as is the existing `chrome_tab_organiser_guide_260911` series.

---

## 3. Running the editor

### From Python

```
python chrome_report_edit_v1.4.py
```

### From the executable

Double-click `chrome_report_edit_v1.4.exe`. On first run Windows may show a
SmartScreen prompt — choose **More info → Run anyway**.

### Options

```
--dir PATH     directory of reports to manage (default: the editor's directory)
--host HOST    default 127.0.0.1
--port PORT    default 8765
--no-browser   do not open a browser window at startup
```

The editor starts a small local web server and opens
`http://127.0.0.1:8765/`. It only ever binds to the loopback address unless you
pass a different `--host`.

### As a frozen executable

The `.exe` manages the directory it lives in. To point it somewhere else:

```
chrome_report_edit_v1.4.exe --dir "D:\path\to\reports"
```

---

## 4. Reordering tabs — the new part

### Starting a drag

Press and hold the **⠿ grip** in the Group cell of a row, then move the mouse.
The grip turns to a grabbing cursor; the row dims to 40% opacity.

> **Note:** the drag starts **only** from the grip. Clicking anywhere else in a
> row keeps its normal behaviour — clicking text edits it, clicking a link does
> not follow it. This is why rows stay comfortable to edit by hand even with
> dragging enabled.

### Dropping

| Drop point | Result |
|------------|--------|
| Above a row's midpoint | Inserted **before** that row |
| Below a row's midpoint | Inserted **after** that row |
| Past the last row | Inserted at the **end** |
| Over another window's table | Inserted into **that window** |

The insertion slot only changes when the pointer crosses a row's midpoint, so the
row settles in place instead of jittering as you move the mouse.

Release the mouse button to commit. `Esc` or an aborted drag leaves the order
untouched.

### Keyboard alternative

No keyboard shortcut is provided in v1.4 — reordering is mouse-only. Everything
else in the editor is unchanged.

---

## 5. Interaction with "sort groups alphabetically"

The toolbar checkbox reorders every window so that ungrouped tabs come first,
then tab groups A→Z. It is a **view-level** reordering that is undone when you
uncheck it.

**Starting a drag turns the checkbox off automatically.** The order you see at
that moment becomes the new baseline, and your drag is applied to it. Unchecking
afterwards will no longer snap the rows back, because there is nothing left to
restore.

If you prefer to use sorting as a one-off view, it is safe: as long as you do not
drag while it is checked, unchecking restores the original order.

---

## 6. Row positions (`data-pos`)

Reports from `chrome_report_v1.4.py` tag each row with `data-pos="1"`, `"2"`, …
in display order. Several parts of the report rely on that numbering matching the
row order, so the editor keeps it truthful:

- `data-pos` is rewritten `1..N` after an **insert**, a **delete**, a **drag**, a
  **group sort**, and on **save**.
- A dragged row keeps its `data-pos` attribute while in flight; the two windows
  involved are renumbered together when the drop completes.
- Reports with **no** `data-pos` anywhere (older v1.3-era and earlier reports) are
  left that way. Editing such a report never silently adds the attribute, so a
  round-trip cannot change its shape.

---

## 7. Saving

Click **Save**, or press `Enter` in the name box. Type a name to write a new
file; leave it as-is to overwrite the file you loaded. Only simple
`[A-Za-z0-9_-. ]` names ending in `.html` are accepted, and writes are confined
to the managed directory.

Saved reports contain **no editor chrome** — the grip, the `+`/`✕` buttons, the
injected stylesheet and all `contenteditable` attributes are stripped
automatically. A saved file is a clean report you can open in any browser.

---

## 8. Testing

```
python -m py_compile chrome_report_edit_v1.4.py test_editor_js.py
python test_editor_js.py
```

`test_editor_js.py` drives the real editor page in headless Chrome with synthetic
drag events and asserts 25 behaviours:

- a grip on every row, carrying `ce-inject` so it is stripped on save
- dragging down within a window reorders the rows
- dragging across windows moves the tab and both windows stay sequential
- `data-pos` is renumbered after insert, delete and drag
- the drag clears its own classes and the drop-zone highlight
- a drag unchecks the group-sort box
- saving strips the grip, the injected CSS and `contenteditable`, and keeps
  `data-pos`
- a legacy report without `data-pos` gains no attributes through any of it

Requires Google Chrome; `Node.js` is **not** required.

---

## 9. Troubleshooting

**The grip does nothing.**
The drag must begin on the ⠿ button itself. Pressing on the group name or the
tab title edits text instead.

**I cannot drop a row onto the window I want.**
Drop onto the *table area* of the target window — its rows. The blue outline
around a table confirms it is a valid target. A window with no tabs yet has no
rows to aim at; add a tab first, then drag.

**My drag did not stick.**
The drop only commits inside a table. Releasing outside the tables cancels.

**Rows went back to their old order.**
You probably had "sort groups alphabetically" checked. It now turns itself off on
the first drag; re-check it if you want the sorted view back.

**The port is already in use.**
Pass another one: `python chrome_report_edit_v1.4.py --port 8766`.

---

## 10. Relationship to the report generator

```
chrome_report_v1.4.py      ──writes──▶   chrome_tabs_Default_v1.4.html
                                                        │
                                          opened in the editor
                                                        ▼
chrome_report_edit_v1.4.py  ◀──saves──   any name you type
```

The editor reads and writes the same HTML the generator produces, so you can
generate a report, tidy the order by dragging, and reopen the saved file
whenever you like. If you then re-run the generator, it will overwrite whatever
default report name it uses — save your edited copy under a different name to keep
it.
