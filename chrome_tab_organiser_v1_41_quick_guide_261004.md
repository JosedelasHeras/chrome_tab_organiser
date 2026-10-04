# chrome\_tab\_organiser — v1.41 Editor Quick Guide

**Date suffix:** `_261004` · **Applies to:** `chrome_report_edit_v1.41.py`

---

## Start it

```
python chrome_report_edit_v1.41.py
```

or double-click `chrome_report_edit_v1.41.exe`.
It opens `http://127.0.0.1:8765/`. Pick a report from the dropdown and press
**Load**, or use **Open…** to load a file from anywhere.

---

## The fixed feature: drag to reorder

```
   ┌──────────────────────────────────────────────────────┐
   │ ⠿  +  ✕ │ ChIP │ Alpha      │ https://a.example/     │
   └──────────────────────────────────────────────────────┘
     ↑
   press and hold HERE
```

1. Press and hold the **⠿ grip** and move the mouse.
2. Drag up or down inside the window, or into **another window's table**.
3. The row dims, follows the pointer, and the target table is outlined.
4. **Release anywhere over the table** — the move commits.

| Release point | Result |
|---------------|--------|
| Above a row's midpoint | Insert **before** it |
| Below a row's midpoint | Insert **after** it |
| Past the last row | Insert at the **end** |
| Another window's table | Insert into **that window** |

It works releasing over the group chip, another row's grips, a tab link, or a
bare cell — v1.41 commits on `dragend`, so the release point no longer needs
to be a perfect drop target. **Starts from the grip only** — clicking text
still edits it and links still do not jump.

---

## Sorting groups

The **sort groups alphabetically** checkbox puts ungrouped tabs first, then
groups A→Z. **An actual drag switches it off automatically** so your manual
order is kept; merely clicking the grip does not.

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
| **Save** / `Enter` in the name box | Write the report to disk |

---

## Saving

Type a new name to create a new file, or leave the existing name to overwrite
the loaded one. Editor controls and drag state are stripped automatically —
the saved file is a clean report.

---

## Row numbering

`data-pos` is renumbered `1..N` after every insert, delete, drag, sort and
save. Older reports without `data-pos` stay that way.
