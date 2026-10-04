# chrome\_tab\_organiser — v1.4 Editor Quick Guide

**Date suffix:** `_261004` · **Applies to:** `chrome_report_edit_v1.4.py`

---

## Start it

```
python chrome_report_edit_v1.4.py
```

or double-click `chrome_report_edit_v1.4.exe`.
It opens `http://127.0.0.1:8765/`. Pick a report from the dropdown and press
**Load**, or use **Open…** to load a file from anywhere.

---

## The one new thing: drag to reorder

```
   ┌──────────────────────────────────────────────────────┐
   │ ⠿  +  ✕ │ ChIP │ Alpha      │ https://a.example/     │
   └──────────────────────────────────────────────────────┘
     ↑
   press and hold HERE
```

1. Press and hold the **⠿ grip**.
2. Drag up or down inside the window, or into **another window's table**.
3. Release to drop.

| Drop point | Result |
|------------|--------|
| Top half of a row | Insert **before** it |
| Bottom half of a row | Insert **after** it |
| Below the last row | Insert at the **end** |
| Another window's table | Insert into **that window** |

The dragged row is dimmed; the target table gets a blue outline.

**Starts from the grip only.** Clicking the group name, tab title or URL still
edits that text, and links still do not jump — dragging never gets in the way of
hand-editing.

---

## Sorting groups

The **sort groups alphabetically** checkbox puts ungrouped tabs first, then
groups A→Z. **Starting a drag switches it off automatically** so your manual
order is kept. Unchecking afterwards will not snap rows back.

---

## Other controls (unchanged)

| Control | What it does |
|---------|--------------|
| Click **Window N** | Rename the window |
| Click a **group chip** | Rename the group |
| Click a **tab title / URL** | Edit it in place |
| **+** on a row | Insert a tab after that row |
| **✕** on a row | Delete that tab |
| **Add tab** in a window head | Insert into that window |
| **Ctrl/⌘ + Backspace** | Delete the focused row |
| **Save** or `Enter` in the name box | Write the report to disk |

---

## Saving

Type a new name to create a new file, or leave the existing name to overwrite the
file you loaded. Names must be simple `.html` files inside the managed folder.

Editor controls are stripped automatically — the saved file is a clean report,
ready to open in any browser.

---

## Row numbering

`data-pos` is renumbered `1..N` after every insert, delete, drag, sort and save.
Older reports that have no `data-pos` at all stay that way.
