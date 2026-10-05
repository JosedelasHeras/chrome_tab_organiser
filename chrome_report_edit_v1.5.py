#!/usr/bin/env python3
"""chrome_report_edit_v1.5.py — local web app for editing the Chrome tab HTML report.

Run:
  python chrome_report_edit_v1.5.py [--dir PATH] [--port 8765]
                                     [--host 127.0.0.1] [--no-browser]
                                     [--no-chrome]

Starts a tiny stdlib HTTP server and opens the editor in your browser.
The editor lets you:
  - rename windows (click the "Window N" heading)
  - edit entries in place (group chip, tab name, URL)
  - delete entries (× on a row)
  - insert an entry into a chosen window at a chosen position (＋ / Add tab)
  - reorder tabs by dragging the ⠿ grip on a row, up or down inside the
    window, or across into any other window (the grip itself is the drag
    source, so editing text in rows is never disturbed)
  - import tabs from the LIVE Chrome session into any window
    ("Add tabs from window" beside Add tab): pick one of Chrome's open
    windows or one of its named tab groups, and every tab is copied into
    the target window. Tabs whose URL is already in the target window are
    skipped. Without "sort groups alphabetically" ticked the imported tabs
    are inserted at the very beginning of the window (in source order);
    with it ticked, each tab is placed alphabetically by its own group so
    the window stays globally sorted. Group names AND colours come across.
  - save the modified report to disk under a name you type

Chrome's own session-recovery files (the SNSS format) are parsed to build
the live tab list, so Chrome can keep running while you import. Pass
--no-chrome to skip that feature entirely.

Only the standard library is used. The managed directory (--dir) defaults
to this script's own directory; all reports there ending in .html are
listed by the editor. Files are only ever written through an explicit save.
"""
import argparse
import json
import os
import re
import struct
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.getcwd()
ALLOW_CHROME = True

PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chrome Report Editor</title>
<style>
  :root { --bg:#f6f7f9; --ink:#1f2430; --mut:#6b7280; --line:#e5e7eb;
          --accent:#1a73e8; --danger:#d93025; }
  * { box-sizing:border-box; }
  html, body { margin:0; height:100%; }
  body { background:var(--bg); color:var(--ink);
         font-family:Segoe UI, system-ui, Arial, sans-serif; }
  header.tbar { position:fixed; top:0; left:0; right:0; height:52px;
    background:#fff; border-bottom:1px solid var(--line); display:flex;
    align-items:center; gap:8px; padding:0 12px; z-index:100; }
  .tbar .app-title { font-size:14px; font-weight:600; margin-right:6px;
    white-space:nowrap; }
  .tbar select, .tbar input, .tbar button { height:30px; font:inherit;
    font-size:13px; }
  .tbar select { max-width:260px; }
  .tbar input[type=text] { width:260px; padding:0 8px; border:1px solid
    var(--line); border-radius:4px; }
  .btn { background:#fff; border:1px solid var(--line); border-radius:4px;
    padding:0 10px; cursor:pointer; }
  .btn:hover { background:#f3f6fb; }
  .btn.primary { background:var(--accent); border-color:var(--accent);
    color:#fff; }
  .btn.primary:hover { background:#1663c5; }
  .tbar .sep { width:1px; height:26px; background:var(--line); }
  .tbar .chk { display:inline-flex; align-items:center; gap:5px;
    font-size:12px; color:var(--mut); white-space:nowrap; cursor:pointer;
    user-select:none; }
  .tbar .chk input { margin:0; }
  #status { font-size:12px; color:var(--mut); flex:1; overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap; text-align:right; }
  #stats { font-size:12px; color:#1663c5; font-weight:600;
    white-space:nowrap; }
  #preview { position:fixed; top:52px; left:0; right:0; bottom:0;
    width:100%; height:calc(100vh - 52px); border:0; background:#fff; }
  #hint { position:fixed; top:52px; left:0; right:0; bottom:0;
    height:calc(100vh - 52px); display:flex; align-items:center;
    justify-content:center; background:var(--bg); z-index:50; color:var(--mut);
    font-size:15px; }
  #hint.hidden { display:none; }
  #modal, #wModal { position:fixed; inset:0; background:rgba(15,20,30,.35);
    display:none; align-items:center; justify-content:center; z-index:200; }
  #modal.open, #wModal.open { display:flex; }
  #modal .box, #wModal .box { background:#fff; border-radius:8px;
    padding:18px 20px; width:460px; max-width:92vw;
    box-shadow:0 8px 30px rgba(0,0,0,.18); }
  #modal h2, #wModal h2 { margin:0 0 12px; font-size:15px; }
  #modal label, #wModal label { display:block; font-size:12px;
    color:var(--mut); margin:10px 0 4px; }
  #modal input, #modal select, #wModal input, #wModal select {
    width:100%; height:30px; font:inherit;
    font-size:13px; border:1px solid var(--line); border-radius:4px;
    padding:0 8px; }
  #modal .rowbtns, #wModal .rowbtns { margin-top:16px;
    display:flex; justify-content:flex-end; gap:8px; }
</style>
</head>
<body>
<header class="tbar">
  <span class="app-title">Chrome Report Editor</span>
  <select id="fileSel" title="Available reports in the managed directory"></select>
  <button id="btnLoad" class="btn" type="button">Load</button>
  <label class="btn" style="display:inline-flex;align-items:center"
         title="Load a report that is not in the directory">
    Open&hellip;<input type="file" id="fileInput" accept=".html,.htm"
                       style="display:none">
  </label>
  <span class="sep"></span>
  <input id="saveName" type="text" placeholder="report name.html"
         spellcheck="false">
  <button id="btnSave" class="btn primary" type="button">Save</button>
  <button id="btnAdd" class="btn" type="button">Add tab</button>
  <label class="chk" title="Within each window, put tabs without a group first, then sort tab groups alphabetically. Dragging a tab turns this off.">
    <input type="checkbox" id="sortGroups"> sort groups alphabetically
  </label>
  <span class="sep"></span>
  <span id="stats" title="windows / tabs / groups"></span>
  <span id="status"></span>
</header>
<div id="hint">Pick a report, or open a .html file, then edit: click text to
  rename (window, group, tab, URL); use +&nbsp;/&times; buttons in the rows to
  insert or delete entries; drag the &nbsp;grip to move a tab up, down, or into
  another window; or use <b>Add tabs from window</b> in a window header to copy
  tabs out of the running Chrome.</div>
<iframe id="preview"></iframe>
<div id="wModal">
  <div class="box">
    <h2>Add tabs from Chrome</h2>
    <label>From</label>
    <select id="wSource"></select>
    <div id="wInfo" style="font-size:12px;color:#6b7280;margin-top:8px"></div>
    <div class="rowbtns">
      <button id="wCancel" class="btn" type="button">Cancel</button>
      <button id="wOk" class="btn primary" type="button">Add tabs</button>
    </div>
  </div>
</div>
<div id="modal">
  <div class="box">
    <h2>Insert a tab</h2>
    <label>Window</label>
    <select id="fWin"></select>
    <label>Position</label>
    <select id="fPos"></select>
    <label>Group (optional)</label>
    <input id="fGroup" list="groupList" placeholder="e.g. ChIP">
    <datalist id="groupList"></datalist>
    <label>Tab name</label>
    <input id="fTitle" placeholder="Tab title">
    <label>URL</label>
    <input id="fUrl" placeholder="https://">
    <div class="rowbtns">
      <button id="fCancel" class="btn" type="button">Cancel</button>
      <button id="fOk" class="btn primary" type="button">Insert</button>
    </div>
  </div>
</div>
<script>
"use strict";
var FDOC = null;          // contentDocument of the preview iframe
var loadedName = null;
var expectingLoad = false;
var pendingInsert = null; // {window, } state for the modal

var frame = document.getElementById("preview");
var hint = document.getElementById("hint");
var statusEl = document.getElementById("status");
var statsEl = document.getElementById("stats");
var selEl = document.getElementById("fileSel");
var saveNameEl = document.getElementById("saveName");
var modal = document.getElementById("modal");
var fWin = document.getElementById("fWin");
var fPos = document.getElementById("fPos");
var fGroup = document.getElementById("fGroup");
var fTitle = document.getElementById("fTitle");
var fUrl = document.getElementById("fUrl");
var groupList = document.getElementById("groupList");
var sortChk = document.getElementById("sortGroups");
var wModal = document.getElementById("wModal");
var wSource = document.getElementById("wSource");
var wInfo = document.getElementById("wInfo");
var pendingImport = null;   // {winIdx, snapshot} for the import modal

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function(c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;",
             '"': "&quot;", "'": "&#39;" }[c];
  });
}
function setStatus(msg) { statusEl.textContent = msg || ""; }
function el(tag, cls, text) {
  var e = FDOC.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/* ---------- group sorting ---------- */
var sortSnap = []; // per-window row-order snapshot while sorting is on
function groupNameOf(tr) {
  var chip = tr.querySelector("td.group .chip");
  if (!chip || chip.classList.contains("none")) return "";
  return chip.textContent.trim();
}
function snapshotGroups() {
  sortSnap = [];
  FDOC.querySelectorAll("section.window").forEach(function(win) {
    sortSnap.push({
      win: win,
      rows: Array.prototype.slice.call(win.querySelectorAll("tbody tr"))
    });
  });
}
function sortGroups() {
  FDOC.querySelectorAll("section.window").forEach(function(win) {
    var tbody = win.querySelector("tbody");
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
    var ungrouped = [];
    var grouped = [];
    for (var i = 0; i < rows.length; i++) {
      var name = groupNameOf(rows[i]);
      if (name) grouped.push({ i: i, name: name, tr: rows[i] });
      else ungrouped.push(rows[i]);
    }
    grouped.sort(function(a, b) {
      var c = a.name.toLowerCase().localeCompare(b.name.toLowerCase());
      return c || (a.i - b.i);
    });
    ungrouped.forEach(function(tr) { tbody.appendChild(tr); });
    grouped.forEach(function(o) { tbody.appendChild(o.tr); });
  });
}
function restoreGroups() {
  sortSnap.forEach(function(sw) {
    var tbody = sw.win.querySelector("tbody");
    if (!tbody) return;
    sw.rows.forEach(function(r) { if (r.isConnected) tbody.appendChild(r); });
  });
  sortSnap = [];
}

/* ---------- row positions (data-pos) ----------
   Reports from the generator tag rows with data-pos. Older reports have no
   such attribute at all; those are tracked per window so a round-trip never
   invents or leaves stale positions behind. */
var posAware = new WeakSet();
function markPosAware() {
  posAware = new WeakSet();
  if (!FDOC) return;
  FDOC.querySelectorAll("section.window").forEach(function(win) {
    if (win.querySelector("tbody tr[data-pos]")) posAware.add(win);
  });
}
function renumberPos(win) {
  if (!win) return;
  var tbody = win.querySelector("tbody");
  if (!tbody) return;
  var rows = tbody.querySelectorAll("tr");
  if (posAware.has(win)) {
    for (var i = 0; i < rows.length; i++) {
      rows[i].setAttribute("data-pos", String(i + 1));
    }
  } else {
    rows.forEach(function(r) { r.removeAttribute("data-pos"); });
  }
}
function renumberAll() {
  if (!FDOC) return;
  FDOC.querySelectorAll("section.window").forEach(renumberPos);
}

/* ---------- drag to reorder ---------- */
var dragRow = null;
function rowOf(ev) {
  var t = ev.target;
  return t && t.closest ? t.closest("tr") : null;
}
function tbodyOf(ev) {
  var t = ev.target;
  return t && t.closest ? t.closest("section.window tbody") : null;
}
/* Index at which a row dropped at clientY belongs. Only changes when the
   pointer crosses a row midpoint, which keeps live moves from thrashing. */
function dropIndexFor(tbody, y) {
  var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i].getBoundingClientRect();
    if (y < r.top + r.height / 2) return i;
  }
  return rows.length;
}
function clearDropZones() {
  if (!FDOC) return;
  FDOC.querySelectorAll("tbody.ce-dropzone").forEach(function(tb) {
    tb.classList.remove("ce-dropzone");
  });
}
function endDrag() {
  var moved = dragRow;
  if (dragRow) dragRow.classList.remove("ce-dragging");
  if (FDOC && FDOC.documentElement) {
    FDOC.documentElement.classList.remove("ce-drag-live");
  }
  dragRow = null;
  clearDropZones();
  /* dragend fires even when Chrome refuses to dispatch drop at the
     release point (over a chip, another grip, or a link), so the commit
     must live here, not in the drop handler. The row is already in place
     from the live dragover moves. */
  if (moved) {
    renumberAll();
    refreshStats();
  }
}
/* The grip itself is the drag source: its draggable attribute is set when
   the row is built, long before any gesture, so nothing depends on mutating
   the DOM mid-mousedown. Rows are never draggable, which keeps text editing
   and link clicks in the rows untouched. */
function onDragStart(ev) {
  var grip = ev.target && ev.target.closest
    ? ev.target.closest(".ce-grip") : null;
  if (!grip) { ev.preventDefault(); return; }  /* not our drag: cancel it */
  var tr = rowOf(ev);
  if (!tr) { ev.preventDefault(); return; }
  /* A real drag replaces the alphabetical view, so drop the snapshot
     instead of letting a later uncheck revert the drag. */
  if (sortChk.checked) {
    sortChk.checked = false;
    sortSnap = [];
  }
  dragRow = tr;
  /* Chrome aborts the drag session if the DOM is mutated synchronously
     inside dragstart (known bug: dragend fires immediately, no dragover).
     Defer the visual state to the next task. While the drag is live, all
     buttons become pointer-transparent: Chrome will not complete a drop
     over another draggable grip (the natural straight-down drag path),
     and hit testing must fall through to the cells underneath. */
  setTimeout(function() {
    tr.classList.add("ce-dragging");
    FDOC.documentElement.classList.add("ce-drag-live");
  }, 0);
  try {
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", "ce-row");
    /* Show the row as the drag ghost, not the tiny grip glyph. */
    ev.dataTransfer.setDragImage(tr, 24, 12);
  } catch (e) { /* synthetic events may lack a full transfer object */ }
}
function onDragOver(ev) {
  if (!dragRow) return;
  var tbody = tbodyOf(ev);
  if (!tbody) return;
  /* Always accept the drop inside a table, including over the dragged row's
     own area (the pointer starts there), so the cursor shows "move". */
  ev.preventDefault();
  try { ev.dataTransfer.dropEffect = "move"; } catch (e) {}
  var tr = rowOf(ev);
  if (tr && tr === dragRow) { clearDropZones(); return; }
  clearDropZones();
  tbody.classList.add("ce-dropzone");
  var idx = dropIndexFor(tbody, ev.clientY);
  var ref = tbody.querySelectorAll("tr")[idx] || null;
  if (ref === dragRow) ref = dragRow.nextElementSibling;
  if (ref !== dragRow) tbody.insertBefore(dragRow, ref);
}
function onDragLeave(ev) {
  var tbody = tbodyOf(ev);
  if (tbody && !tbody.contains(ev.relatedTarget)) {
    tbody.classList.remove("ce-dropzone");
  }
}
function onDrop(ev) {
  if (!dragRow) return;
  ev.preventDefault();
  ev.stopPropagation();
  endDrag();
}

/* ---------- stats ---------- */
function refreshStats() {
  if (!FDOC) return;
  var wins = FDOC.querySelectorAll("section.window");
  var w = 0, t = 0, seen = {}, g = 0;
  wins.forEach(function(win) {
    var rows = win.querySelectorAll("tbody tr");
    var groups = {};
    rows.forEach(function(r) {
      var chip = r.querySelector("td.group .chip");
      if (chip && !chip.classList.contains("none") && chip.textContent.trim()) {
        var key = chip.textContent.trim();
        groups[key] = true;
        if (!seen[key]) seen[key] = true;
      }
    });
    var meta = win.querySelector(".window-head .win-meta");
    if (meta) {
      var txt = rows.length + " tab" + (rows.length === 1 ? "" : "s");
      var gCount = Object.keys(groups).length;
      if (gCount) {
        txt += " \u00b7 " + gCount + " group" + (gCount === 1 ? "" : "s");
      }
      if (win.querySelector(".active-star")) {
        txt += " \u00b7 <b>active window</b>";
      }
      meta.innerHTML = txt;
    }
    w += 1;
    t += rows.length;
  });
  g = Object.keys(seen).length;
  var st = FDOC.querySelector(".stats");
  if (st) {
    st.innerHTML = w + " window" + (w === 1 ? "" : "s") +
                   " \u00b7 " + t + " tab" + (t === 1 ? "" : "s") +
                   " \u00b7 " + g + " tab group" + (g === 1 ? "" : "s");
  }
  statsEl.textContent = w + " \u00b7 " + t + " \u00b7 " + g;
}

/* ---------- content helpers ---------- */
function tbText(el) { return (el && el.textContent || "").trim(); }

function rowMarkup(group, title, url, active, color) {
  var g = (group || "").trim();
  color = /^#[0-9a-fA-F]{3,8}$/.test(color || "") ? color : "#5f6368";
  var chip = g
    ? '<span class="chip" style="background:' + color + '">' + esc(g) + "</span>"
    : '<span class="chip none"></span>';
  var star = active ? '<span class="active-star">\u2605</span> ' : "";
  var t = (title || "").trim() || "(no title)";
  var u = (url || "").trim();
  var tabCell = u
    ? '<a href="' + esc(u) + '" title="' + esc(u) + '">' + esc(t) + "</a>"
    : esc(t);
  var urlCell = u
    ? '<a class="url-text" href="' + esc(u) + '">' + esc(u) + "</a>"
    : "";
  return '<tr><td class="group">' + chip + '</td><td class="tab">' +
         star + tabCell + '</td><td class="url">' + urlCell + '</td></tr>';
}

function onUrlBlur(ev) {
  var a = ev.target;
  var u = a.textContent.trim();
  a.href = u;
  a.setAttribute("title", u);
  var row = a.closest("tr");
  if (row) {
    var tabA = row.querySelector("td.tab a");
    if (tabA) { tabA.setAttribute("href", u); tabA.setAttribute("title", u); }
  }
}
function onChipInput(ev) {
  var chip = ev.target;
  var txt = chip.textContent.trim();
  if (chip.classList.contains("none")) {
    if (txt) { chip.classList.remove("none"); chip.style.background = "#5f6368"; }
  } else if (!txt) {
    chip.classList.add("none"); chip.style.background = "";
  }
  refreshStats();
}

function setUpRow(tr) {
  var chip = tr.querySelector("td.group .chip");
  if (chip) {
    chip.contentEditable = "true";
    chip.addEventListener("input", onChipInput);
  }
  var tabTd = tr.querySelector("td.tab");
  var tabA = tabTd ? tabTd.querySelector("a") : null;
  if (tabA) tabA.contentEditable = "true";
  else if (tabTd) tabTd.contentEditable = "true";
  var urlA = tr.querySelector("td.url a");
  if (urlA) {
    urlA.contentEditable = "true";
    urlA.addEventListener("blur", onUrlBlur);
  }
  var tdg = tr.querySelector("td.group");
  if (tdg) {
    var bGrip = el("button", "ce-inject ce-grip", "\u283f");
    bGrip.title = "Drag to move this tab (up, down, or into another window)";
    bGrip.draggable = true;  /* the grip is the drag source, set up front */
    var bIns = el("button", "ce-inject ce-ins", "+");
    bIns.title = "Insert a tab after this row";
    bIns.addEventListener("click", function(ev) {
      ev.preventDefault(); ev.stopPropagation();
      openInsert(tr);
    });
    var bDel = el("button", "ce-inject ce-del", "\u2715");
    bDel.title = "Delete this tab";
    bDel.addEventListener("click", function(ev) {
      ev.preventDefault(); ev.stopPropagation();
      tr.remove();
      renumberAll();
      refreshStats();
    });
    tdg.appendChild(bGrip);
    tdg.appendChild(bIns);
    tdg.appendChild(bDel);
  }
}

/* ---------- editor injection into the loaded report ---------- */
function injectEditor(d) {
  var css = d.getElementById("ce-css");
  if (!css) {
    css = d.createElement("style");
    css.id = "ce-css";
    css.textContent = [
      "td.group { white-space:nowrap; }",
      "[contenteditable]:hover { outline:1px dashed #1a73e8; }",
      "[contenteditable]:focus { outline:1px solid #1a73e8; }",
      "button.ce-inject { background:#fff; color:#5f6368; border:1px solid",
      " #d7dbe2; border-radius:12px; height:20px; width:20px; line-height:1;",
      " font-size:12px; margin-left:5px; padding:0; cursor:pointer;",
      " vertical-align:middle; }",
      "button.ce-inject:hover { background:#eef2fb; color:#1a73e8; }",
      "button.ce-inject.ce-del:hover { background:#fdeceb; color:#d93025; }",
      "button.ce-add { background:#fff; color:#1a73e8; border:1px solid",
      " #d7dbe2; border-radius:4px; font-size:11px; padding:1px 8px;",
      " cursor:pointer; margin-left:6px; }",
      "button.ce-add:hover { background:#eef2fb; }",
      "button.ce-add.ce-addwin { color:#188038; border-color:#b7e0c4; }",
      "button.ce-add.ce-addwin:hover { background:#e6f4ea; }",
      "button.ce-inject.ce-grip { cursor:grab; user-select:none;",
      " -webkit-user-select:none; touch-action:none; }",
      "button.ce-inject.ce-grip:active { cursor:grabbing; }",
      "tr.ce-dragging { opacity:.4; }",
      "tr.ce-dragging > td { cursor:grabbing; }",
      "tbody.ce-dropzone { box-shadow:inset 0 0 0 2px #1a73e8; }",
      "tr.ce-dragging *:not(.ce-grip) { pointer-events:none; }",
      ".ce-drag-live button { pointer-events:none; }"
    ].join(String.fromCharCode(10));
    d.head.appendChild(css);
  }

  d.querySelectorAll(".window-head .wname").forEach(function(w) {
    w.contentEditable = "true";
  });

  d.querySelectorAll("section.window").forEach(function(win) {
    var add = el("button", "ce-inject ce-add", "Add tab");
    add.addEventListener("click", function(ev) {
      ev.preventDefault(); ev.stopPropagation();
      openInsert(null, winIndex(win));
    });
    var addWin = el("button", "ce-inject ce-add ce-addwin",
                    "Add tabs from window");
    addWin.title = "Copy tabs from the live Chrome session into this window";
    addWin.addEventListener("click", function(ev) {
      ev.preventDefault(); ev.stopPropagation();
      openImport(winIndex(win));
    });
    var head = win.querySelector(".window-head");
    if (head) { head.appendChild(add); head.appendChild(addWin); }
  });

  d.querySelectorAll("tbody tr").forEach(setUpRow);

  /* Drag to reorder. Listeners live on the document so rows created later
     (insert) and rows moved between windows are covered too. */
  d.addEventListener("dragstart", onDragStart);
  d.addEventListener("dragover", onDragOver);
  d.addEventListener("dragleave", onDragLeave);
  d.addEventListener("drop", onDrop);
  d.addEventListener("dragend", endDrag);

  d.addEventListener("click", function(ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest("a") : null;
    if (a) ev.preventDefault();
  }, true);

  d.addEventListener("keydown", function(ev) {
    if (ev.key === "Backspace" && (ev.metaKey || ev.ctrlKey)) {
      var t = ev.target;
      var row = t && t.closest ? t.closest("tr") : null;
      if (row && row.querySelector(".ce-del")) {
        ev.preventDefault();
        row.remove();
        renumberAll();
        refreshStats();
      }
    }
  }, true);
}

function winIndex(win) {
  return Array.prototype.indexOf.call(
    FDOC.querySelectorAll("section.window"), win);
}

/* ---------- load a report ---------- */
function applyReport(text, name) {
  saveNameEl.value = name;
  loadedName = name;
  expectingLoad = true;
  frame.addEventListener("load", onFrameLoaded);
  frame.srcdoc = text;
}

function onFrameLoaded() {
  frame.removeEventListener("load", onFrameLoaded);
  if (!expectingLoad) return;
  expectingLoad = false;
  try { FDOC = frame.contentDocument; } catch (e) { FDOC = null; }
  if (!FDOC) { setStatus("Could not access report document."); return; }
  sortChk.checked = false;
  sortSnap = [];
  try {
    injectEditor(FDOC);
    markPosAware();
    refreshStats();
  } catch (e) {
    console.error("Load setup failed:", e);
    setStatus("Load error: " + e);
  }
  hint.classList.add("hidden");
  setStatus('Loaded "' + (loadedName || "") + '" \u2014 click text to edit.');
}

function doLoad(name) {
  if (!name) return;
  fetch("/api/load?name=" + encodeURIComponent(name))
    .then(function(r) { return r.json(); })
    .then(function(j) {
      if (j.ok) { applyReport(j.html, name); }
      else setStatus("Load failed: " + (j.error || "unknown"));
    })
    .catch(function(err) { setStatus("Load error: " + err); });
}

function refreshFiles() {
  fetch("/api/files").then(function(r) { return r.json(); }).then(function(j) {
    selEl.innerHTML = "";
    (j.files || []).forEach(function(n) {
      var o = document.createElement("option");
      o.value = n; o.textContent = n;
      selEl.appendChild(o);
    });
    if (loadedName) {
      var found = false;
      for (var i = 0; i < selEl.options.length; i++) {
        if (selEl.options[i].value === loadedName) { selEl.selectedIndex = i; found = true; break; }
      }
      if (!found) {
        var o = document.createElement("option");
        o.value = loadedName; o.textContent = loadedName + " (in use)";
        selEl.appendChild(o);
      }
    } else if (selEl.options.length) {
      selEl.selectedIndex = 0;
    }
  }).catch(function(err) { setStatus("Cannot list reports: " + err); });
}

/* ---------- save ---------- */
function serializeReport() {
  if (!FDOC) return null;
  renumberAll();
  if (FDOC.documentElement) {
    FDOC.documentElement.classList.remove("ce-drag-live");
  }
  FDOC.querySelectorAll(".ce-inject").forEach(function(n) { n.remove(); });
  var css = FDOC.getElementById("ce-css");
  if (css) css.remove();
  FDOC.querySelectorAll("[contenteditable]").forEach(function(n) {
    n.removeAttribute("contenteditable");
  });
  var html = "<!DOCTYPE html>" + String.fromCharCode(10) +
                 FDOC.documentElement.outerHTML;
  injectEditor(FDOC);
  refreshStats();
  return html;
}

function doSave() {
  if (!FDOC) { setStatus("Load a report first."); return; }
  var name = (saveNameEl.value || "").trim();
  if (!name) name = loadedName || "report.html";
  var html = serializeReport();
  if (html == null) return;
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name, html: html })
  }).then(function(r) { return r.json(); }).then(function(j) {
    if (j.ok) {
      setStatus("Saved " + j.path + " (" + j.bytes + " bytes)");
      saveNameEl.value = j.name;
      loadedName = j.name;
      refreshFiles();
    } else {
      setStatus("Save failed: " + (j.error || "unknown"));
    }
  }).catch(function(err) { setStatus("Save error: " + err); });
}

/* ---------- insert dialog ---------- */
function openInsert(afterRow, winIdx) {
  if (!FDOC) { setStatus("Load a report first."); return; }
  var wins = FDOC.querySelectorAll("section.window");
  fWin.innerHTML = "";
  wins.forEach(function(win, i) {
    var o = document.createElement("option");
    o.value = i;
    var name = tbText(win.querySelector(".wname")) || ("Window " + (i + 1));
    o.textContent = name + " \u2014 " + win.querySelectorAll("tbody tr").length + " tabs";
    fWin.appendChild(o);
  });
  fPos.innerHTML = "";
  var oTop = document.createElement("option");
  oTop.value = "top"; oTop.textContent = "At top of the window";
  fPos.appendChild(oTop);
  if (afterRow) {
    var oRow = document.createElement("option");
    oRow.value = "row"; oRow.textContent = "After: " + (tbText(afterRow.querySelector("td.tab")) || "(row)");
    fPos.appendChild(oRow);
  }
  var oEnd = document.createElement("option");
  oEnd.value = "end"; oEnd.textContent = "At the end of the window";
  fPos.appendChild(oEnd);

  var list = FDOC.querySelectorAll("td.group .chip");
  var names = {}, out = [];
  list.forEach(function(c) {
    var n = c.textContent.trim();
    if (n && !names[n]) { names[n] = true; out.push(n); }
  });
  groupList.innerHTML = "";
  out.forEach(function(n) {
    var l = document.createElement("option");
    l.value = n; groupList.appendChild(l);
  });

  if (afterRow) fWin.value = winIndex(afterRow.closest("section.window"));
  else if (winIdx != null && winIdx >= 0 && winIdx < fWin.options.length) {
    fWin.value = winIdx;
  }
  fPos.value = afterRow ? "row" : "top";
  pendingInsert = { afterRow: afterRow, winIdx: winIdx };
  fGroup.value = ""; fTitle.value = ""; fUrl.value = "";
  modal.classList.add("open");
  setStatus("");
  setTimeout(function() { fTitle.focus(); }, 10);
}

function closeModal() { modal.classList.remove("open"); pendingInsert = null; }

function doInsert() {
  var p = pendingInsert || {};
  var win = parseInt(fWin.value, 10);
  var pos = fPos.value;
  var gName = (fGroup.value || "").trim();
  var col = null;
  if (gName) {
    var chips = FDOC.querySelectorAll("td.group .chip:not(.none)");
    for (var ci = 0; ci < chips.length; ci++) {
      if (chips[ci].textContent.trim() === gName) {
        var m = (chips[ci].getAttribute("style") || "").match(/background:([^;]+)/);
        if (m) { col = m[1]; break; }
      }
    }
  }
  var mark = rowMarkup(gName, fTitle.value, fUrl.value, false, col || "#5f6368");
  var wins = FDOC.querySelectorAll("section.window");
  if (!wins.length || isNaN(win) || win >= wins.length) {
    setStatus("Insert failed: no such window."); closeModal(); return;
  }
  var tbody = wins[win].querySelector("tbody");
  var tr = FDOC.createElement("tr");
  tr.innerHTML = mark;
  if (pos === "row" && p.afterRow && p.afterRow.isConnected) p.afterRow.after(tr);
  else if (pos === "top") tbody.prepend(tr);
  else tbody.appendChild(tr);
  setUpRow(tr);
  renumberPos(wins[win]);
  refreshStats();
  closeModal();
  setStatus("Inserted into Window " + (win + 1) + ".");
}

/* ---------- import tabs from the live Chrome session ----------
   The report's own window names are user-assigned when a report is
   generated, so they cannot be matched against Chrome (which has no
   window names). The picker therefore lists the live windows in tab-strip
   order plus Chrome's named tab groups, and the user chooses. */

/* URLs are compared loosely: chrome:// paged history aside, a trailing
   slash or letter case is the usual difference between the same page. */
function normUrl(u) {
  var s = String(u == null ? "" : u).trim();
  if (!s) return "";
  s = s.replace(/#.*$/, "");
  try {
    var a = document.createElement("a");
    a.href = s;
    if (a.protocol && a.host) {
      return (a.protocol + "//" + a.host +
              (a.pathname || "/").replace(/\\/+$/, "") +
              (a.search || "")).toLowerCase();
    }
  } catch (e) { /* fall through to the raw form */ }
  return s.replace(/\\/+$/, "").toLowerCase();
}

function sourceLabel(opt) {
  return opt ? opt.textContent : "";
}

function tabsForSelection(snap, sel) {
  if (!snap || !sel) return [];
  var kind = sel.split("\t");
  if (kind[0] === "w") {
    for (var i = 0; i < snap.windows.length; i++) {
      if (String(snap.windows[i].id) === kind[1]) return snap.windows[i].tabs;
    }
    return [];
  }
  if (kind[0] === "g") {
    var want = kind[1].toLowerCase();
    var out = [];
    snap.windows.forEach(function(w) {
      w.tabs.forEach(function(t) {
        if ((t.group || "").trim().toLowerCase() === want) out.push(t);
      });
    });
    return out;
  }
  return [];
}

function refreshImportInfo() {
  var n = tabsForSelection(pendingImport && pendingImport.snap,
                           wSource.value).length;
  if (!n) {
    wInfo.textContent = "Nothing to add for this choice.";
    return;
  }
  wInfo.textContent = n + " tab" + (n === 1 ? "" : "s") + " will be added" +
    (sortChk.checked ? ", placed alphabetically by group."
                     : ", inserted at the beginning of the window.");
}

function openImport(winIdx) {
  if (!FDOC) { setStatus("Load a report first."); return; }
  var wins = FDOC.querySelectorAll("section.window");
  if (!wins.length || winIdx == null || winIdx < 0 || winIdx >= wins.length) {
    setStatus("Import failed: no such window."); return;
  }
  wInfo.textContent = "Reading Chrome's session files...";
  wSource.innerHTML = "";
  wModal.classList.add("open");
  setStatus("");
  fetch("/api/live").then(function(r) { return r.json(); })
    .then(function(j) {
      if (!j || !j.ok) {
        pendingImport = null;
        wSource.innerHTML = "";
        wInfo.textContent = "Chrome session not available: " +
          ((j && j.error) || "unknown error");
        return;
      }
      pendingImport = { winIdx: winIdx, snap: j };
      wSource.innerHTML = "";
      var totalTabs = 0;
      if (j.windows.length) {
        var og = document.createElement("optgroup");
        og.label = "Chrome windows";
        j.windows.forEach(function(w) {
          totalTabs += w.tabs.length;
          var o = document.createElement("option");
          o.value = "w\t" + w.id;
          var gset = {};
          w.tabs.forEach(function(t) {
            if (t.group) gset[t.group.trim().toLowerCase()] = true;
          });
          o.textContent = w.name + " — " + w.tabs.length + " tab" +
            (w.tabs.length === 1 ? "" : "s") + " · " +
            Object.keys(gset).length + " group" +
            (Object.keys(gset).length === 1 ? "" : "s") +
            (w.active ? " · active" : "");
          og.appendChild(o);
        });
        wSource.appendChild(og);
      }
      if (j.groups.length) {
        var gg = document.createElement("optgroup");
        gg.label = "Chrome tab groups";
        j.groups.forEach(function(g) {
          var o = document.createElement("option");
          o.value = "g\t" + g.name;
          o.textContent = g.name + " — " + g.count + " tab" +
            (g.count === 1 ? "" : "s");
          gg.appendChild(o);
        });
        wSource.appendChild(gg);
      }
      if (!wSource.options.length) {
        pendingImport = null;
        wInfo.textContent = "No Chrome windows or tab groups found.";
        return;
      }
      wSource.selectedIndex = 0;
      var skipped = (j.skipped || []).length;
      refreshImportInfo();
      setStatus("Chrome snapshot: " + j.windows.length + " window" +
        (j.windows.length === 1 ? "" : "s") + " · " + totalTabs + " tabs · " +
        j.groups.length + " group" + (j.groups.length === 1 ? "" : "s") +
        (skipped ? " · " + skipped + " session file(s) skipped" : ""));
    })
    .catch(function(err) {
      pendingImport = null;
      wInfo.textContent = "Could not read Chrome's session files: " + err;
    });
}

function closeImport() {
  wModal.classList.remove("open");
  pendingImport = null;
}

function doImport() {
  var p = pendingImport;
  if (!p || !p.snap) { closeImport(); return; }
  var wins = FDOC.querySelectorAll("section.window");
  var win = wins[p.winIdx];
  if (!win) { setStatus("Import failed: no such window."); closeImport(); return; }
  var tbody = win.querySelector("tbody");
  if (!tbody) { setStatus("Import failed: window has no table."); closeImport(); return; }
  var picked = sourceLabel(wSource.options[wSource.selectedIndex]);
  var tabs = tabsForSelection(p.snap, wSource.value);
  if (!tabs.length) {
    setStatus("Nothing to import for that choice.");
    closeImport();
    return;
  }

  /* Skip URLs already in the target window. Chrome is allowed to have the
     same page open twice, and the import copies the window as it really is,
     so only the target is consulted here: repeating the import afterwards
     still adds nothing, because those URLs are in the window by then. */
  var have = {};
  Array.prototype.forEach.call(tbody.querySelectorAll("tr"), function(tr) {
    var a = tr.querySelector("td.url a") || tr.querySelector("td.tab a");
    var k = normUrl(a ? a.getAttribute("href") : "");
    if (k) have[k] = true;
  });
  var fresh = [];
  tabs.forEach(function(t) {
    var k = normUrl(t.url);
    if (k && have[k]) return;
    fresh.push(t);
  });
  var skipped = tabs.length - fresh.length;
  if (!fresh.length) {
    setStatus("Nothing to import: all " + tabs.length + " tab" +
      (tabs.length === 1 ? "" : "s") + " already in this window.");
    closeImport();
    return;
  }

  var sorted = sortChk.checked;
  /* Build the block in a fragment first. Prepending row by row would put
     each row in front of the one added before it, reversing the source
     order; a fragment keeps it as written. Unsorted goes to the very top
     of the window, sorted is appended and sortGroups() then places every
     row by its own group (source order breaks ties inside a group). */
  var frag = FDOC.createDocumentFragment();
  fresh.forEach(function(t) {
    var tr = FDOC.createElement("tr");
    tr.innerHTML = rowMarkup(t.group, t.title, t.url, false,
                             t.color || "#5f6368");
    setUpRow(tr);
    frag.appendChild(tr);
  });
  if (sorted) tbody.appendChild(frag);
  else tbody.insertBefore(frag, tbody.firstChild);
  if (sorted) sortGroups();

  renumberPos(win);
  refreshStats();
  closeImport();
  setStatus("Added " + fresh.length + " tab" + (fresh.length === 1 ? "" : "s") +
    " from " + picked +
    (skipped ? " (" + skipped + " already in this window)" : "") + ".");
}

/* ---------- wires ---------- */
document.getElementById("btnLoad").addEventListener("click", function() {
  doLoad(selEl.value);
});
selEl.addEventListener("change", function() { doLoad(selEl.value); });
document.getElementById("fileInput").addEventListener("change", function(ev) {
  var f = ev.target.files && ev.target.files[0];
  if (!f) return;
  var rd = new FileReader();
  rd.onload = function() { applyReport(String(rd.result), f.name); };
  rd.readAsText(f);
});
document.getElementById("btnSave").addEventListener("click", doSave);
document.getElementById("btnAdd").addEventListener("click", function() {
  openInsert(null, null);
});
sortChk.addEventListener("change", function() {
  if (!FDOC) return;
  if (sortChk.checked) { snapshotGroups(); sortGroups(); }
  else restoreGroups();
  renumberAll();
  /* the import dialog describes its placement based on this box */
  if (pendingImport) refreshImportInfo();
});
document.getElementById("fCancel").addEventListener("click", closeModal);
document.getElementById("wCancel").addEventListener("click", closeImport);
document.getElementById("wOk").addEventListener("click", function(ev) {
  ev.preventDefault(); doImport();
});
wSource.addEventListener("change", refreshImportInfo);
wModal.addEventListener("click", function(ev) {
  if (ev.target === wModal) closeImport();
});
document.getElementById("fOk").addEventListener("click", function(ev) {
  ev.preventDefault(); doInsert();
});
modal.addEventListener("click", function(ev) {
  if (ev.target === modal) closeModal();
});
saveNameEl.addEventListener("keydown", function(ev) {
  if (ev.key === "Enter") doSave();
});
window.addEventListener("beforeunload", function(ev) {
  if (FDOC) ev.preventDefault();
});

refreshFiles();
</script>
</body>
</html>
"""


SNSS_MAGIC = b"SNSS"
DEFAULT_PROFILE = "Default"

# Command ids from Chrome's session-recovery format. Only the ones that
# describe windows, tabs and tab groups are handled here. These must match
# chrome_report_v1.4.py exactly or the stream desynchronises.
CMD_SET_TAB_WINDOW = 0
CMD_SET_TAB_INDEX_IN_WINDOW = 2
CMD_UPDATE_TAB_NAVIGATION = 6
CMD_SET_SELECTED_NAVIGATION_INDEX = 7
CMD_SET_SELECTED_TAB_IN_INDEX = 8
CMD_TAB_CLOSED = 16
CMD_WINDOW_CLOSED = 17
CMD_SET_ACTIVE_WINDOW = 20
CMD_LAST_ACTIVE_TIME = 21
CMD_SET_TAB_GROUP = 25
CMD_SET_TAB_GROUP_METADATA = 27

# Chrome tab-group colour ids, as written by CMD_SET_TAB_GROUP_METADATA.
GROUP_COLORS = {
    1: "#5f6368",
    2: "#1a73e8",
    3: "#d93025",
    4: "#f29900",
    5: "#188038",
    6: "#d01884",
    7: "#a142f4",
    8: "#12a4af",
    9: "#fa903e",
}


def align4(n):
    return (n + 3) & ~3


class Payload:
    def __init__(self, data):
        self.data = data
        self.off = 0
        self.n = len(data)

    def _need(self, size):
        if self.off + size > self.n:
            raise EOFError("payload too short")

    def u8(self):
        self._need(1)
        val = self.data[self.off]
        self.off += 1
        return val

    def u32(self):
        self._need(4)
        val = struct.unpack_from("<I", self.data, self.off)[0]
        self.off += 4
        return val

    def u64(self):
        low = self.u32()
        high = self.u32()
        return (high << 32) | low

    def string(self):
        self._need(4)
        size = struct.unpack_from("<I", self.data, self.off)[0]
        self.off += 4
        raw = self.data[self.off:self.off + size]
        self.off += align4(size)
        return raw.decode("utf-8", "replace")

    def string16(self):
        self._need(4)
        count = struct.unpack_from("<I", self.data, self.off)[0]
        self.off += 4
        blen = count * 2
        raw = self.data[self.off:self.off + blen]
        self.off += align4(blen)
        return raw.decode("utf-16-le", "replace")


class SessionState:
    def __init__(self):
        self.tabs = {}
        self.windows = {}
        self.groups = {}
        self.active_window_id = None

    def get_tab(self, tab_id):
        tab = self.tabs.get(tab_id)
        if tab is None:
            tab = {"id": tab_id, "win": 0, "idx": 0, "history": {},
                   "current_hist": 0, "group": None, "deleted": False}
            self.tabs[tab_id] = tab
        return tab

    def get_window(self, win_id):
        win = self.windows.get(win_id)
        if win is None:
            win = {"id": win_id, "active_tab_idx": -1, "deleted": False}
            self.windows[win_id] = win
        return win

    def get_group(self, high, low):
        key = "%016x%016x" % (high, low)
        group = self.groups.get(key)
        if group is None:
            group = {"high": high, "low": low, "name": "", "color": None}
            self.groups[key] = group
        return group


def process_command(ctype, data, state):
    p = Payload(data)
    if ctype == CMD_SET_TAB_WINDOW:
        win = p.u32()
        tab = p.u32()
        state.get_tab(tab)["win"] = win
    elif ctype == CMD_SET_TAB_INDEX_IN_WINDOW:
        tab = p.u32()
        idx = p.u32()
        state.get_tab(tab)["idx"] = idx
    elif ctype == CMD_UPDATE_TAB_NAVIGATION:
        p.u32()
        tab = p.u32()
        hist_idx = p.u32()
        url = p.string()
        title = p.string16()
        state.get_tab(tab)["history"][hist_idx] = (url, title)
    elif ctype == CMD_SET_SELECTED_NAVIGATION_INDEX:
        tab = p.u32()
        state.get_tab(tab)["current_hist"] = p.u32()
    elif ctype == CMD_SET_SELECTED_TAB_IN_INDEX:
        win = p.u32()
        state.get_window(win)["active_tab_idx"] = p.u32()
    elif ctype == CMD_TAB_CLOSED:
        state.get_tab(p.u32())["deleted"] = True
    elif ctype == CMD_WINDOW_CLOSED:
        state.get_window(p.u32())["deleted"] = True
    elif ctype == CMD_SET_ACTIVE_WINDOW:
        state.active_window_id = p.u32()
    elif ctype == CMD_SET_TAB_GROUP:
        tab = p.u32()
        p.u32()
        high = p.u64()
        low = p.u64()
        state.get_tab(tab)["group"] = state.get_group(high, low)
    elif ctype == CMD_SET_TAB_GROUP_METADATA:
        p.u32()
        high = p.u64()
        low = p.u64()
        name = p.string16()
        group = state.get_group(high, low)
        group["name"] = name
        if p.off + 4 <= p.n:
            group["color"] = p.u32()


def parse_snss(path, state):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 8 or data[:4] != SNSS_MAGIC:
        raise ValueError("not an SNSS file")
    off = 8
    count = 0
    while off + 3 <= len(data):
        size = struct.unpack_from("<H", data, off)[0]
        off += 2
        ctype = data[off]
        off += 1
        payload_len = size - 1
        if payload_len < 0 or off + payload_len > len(data):
            break
        payload = data[off:off + payload_len]
        off += payload_len
        try:
            process_command(ctype, payload, state)
        except (EOFError, struct.error, ValueError, IndexError):
            continue
        count += 1
    return count


def read_session_file(path, state):
    for attempt in range(3):
        try:
            return parse_snss(path, state)
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.3)
    return 0


def default_data_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "Google", "Chrome", "User Data")
    if sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Google/Chrome")
    return os.path.expanduser("~/.config/google-chrome")


def session_files(session_dir):
    files = []
    pat = re.compile(r"^(Session|Tabs)(?:_(\d+))?$")
    for name in os.listdir(session_dir):
        m = pat.match(name)
        if not m:
            continue
        path = os.path.join(session_dir, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            continue
        gen = int(m.group(2)) if m.group(2) else float("inf")
        files.append((gen, name, path))
    files.sort()
    return files


def resolve_tab(tab):
    hist = tab["history"]
    if not hist:
        return "", ""
    current = tab["current_hist"]
    if current in hist:
        return hist[current]
    return hist[max(hist)]


def build_live_model(state):
    windows = []
    for win_id, win in state.windows.items():
        if win["deleted"]:
            continue
        tabs = [t for t in state.tabs.values()
                if t["win"] == win_id and not t["deleted"]]
        if not tabs:
            continue
        tabs.sort(key=lambda t: t["idx"])
        rows = []
        for tab in tabs:
            url, title = resolve_tab(tab)
            group = tab["group"]
            rows.append({
                "url": url,
                "title": title,
                "group": group["name"] if group else None,
                # Same default the generator uses for a colour-less group,
                # so an imported chip is always a real colour.
                "color": (GROUP_COLORS.get(group.get("color"), "#5f6368")
                          if group else None),
            })
        windows.append({
            "id": win_id,
            "active": win_id == state.active_window_id,
            "tabs": rows,
        })
    return windows


def live_snapshot():
    """Windows and named tab groups as Chrome currently has them.

    Read-only: the session files are parsed, never written. Files that are
    mid-write while Chrome is running are skipped with a reason, exactly as
    the generator does, so the newest complete snapshot is used.
    """
    if not ALLOW_CHROME:
        return {"ok": False, "error": "live Chrome import disabled "
                                       "(--no-chrome)"}
    data_dir = default_data_dir()
    sessions = os.path.join(data_dir, DEFAULT_PROFILE, "Sessions")
    if not os.path.isdir(sessions):
        return {"ok": False,
                "error": "Chrome session folder not found: %s" % sessions}
    state = SessionState()
    used = []
    skipped = []
    try:
        candidates = session_files(sessions)
    except OSError as exc:
        return {"ok": False, "error": "cannot list session files: %s" % exc}
    for _gen, name, path in candidates:
        try:
            read_session_file(path, state)
            used.append(name)
        except (PermissionError, OSError):
            skipped.append((name, "in use by Chrome"))
        except (ValueError, struct.error):
            skipped.append((name, "not a readable session file"))

    windows = build_live_model(state)
    if not windows:
        return {"ok": False,
                "error": "no open Chrome windows found in the session files",
                "skipped": ["%s (%s)" % s for s in skipped]}

    # Windows get positional names: Chrome has no user-assigned window
    # names, so the picker lists them in tab-strip order.
    named = []
    for i, win in enumerate(windows, start=1):
        win["name"] = "Window %d" % i
        named.append(win)

    groups = {}
    for win in named:
        for tab in win["tabs"]:
            gname = (tab.get("group") or "").strip()
            if not gname:
                continue
            key = gname.lower()
            g = groups.get(key)
            if g is None:
                g = groups[key] = {"name": gname, "color": tab.get("color"),
                                   "count": 0}
            if not g.get("color") and tab.get("color"):
                g["color"] = tab["color"]
            g["count"] += 1

    return {
        "ok": True,
        "windows": named,
        "groups": sorted(groups.values(), key=lambda g: g["name"].lower()),
        "files": used,
        "skipped": ["%s (%s)" % s for s in skipped],
    }


def send_bytes(handler, code, content_type, body):
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def send_json(handler, code, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    send_bytes(handler, code, "application/json; charset=utf-8", body)


def send_text(handler, code, text):
    body = text.encode("utf-8")
    send_bytes(handler, code, "text/html; charset=utf-8", body)


NAME_RE = re.compile(r"[\w\- .]+")


def safe_name(name):
    name = os.path.basename(name or "").strip()
    if not name or not name.lower().endswith(".html"):
        return None
    if not NAME_RE.fullmatch(name):
        return None
    return name


def resolve(name):
    name = safe_name(name)
    if not name:
        return None
    path = os.path.realpath(os.path.join(BASE, name))
    base = os.path.realpath(BASE) + os.sep
    if not path.startswith(base):
        return None
    return path


def list_reports():
    try:
        names = sorted(n for n in os.listdir(BASE)
                       if n.lower().endswith(".html")
                       and os.path.isfile(os.path.join(BASE, n)))
    except OSError:
        names = []
    return names


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            send_text(self, 200, PAGE_HTML)
        elif u.path == "/api/files":
            send_json(self, 200, {"ok": True, "files": list_reports()})
        elif u.path == "/api/live":
            try:
                send_json(self, 200, live_snapshot())
            except Exception as exc:  # never take the editor down for this
                send_json(self, 500, {"ok": False, "error": str(exc)})
        elif u.path == "/api/load":
            qs = parse_qs(u.query)
            name = (qs.get("name") or [""])[0]
            path = resolve(name)
            if not path or not os.path.isfile(path):
                send_json(self, 404, {"ok": False,
                                      "error": "report not found"})
                return
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                send_json(self, 500, {"ok": False, "error": str(exc)})
                return
            send_json(self, 200,
                      {"ok": True, "name": os.path.basename(path),
                       "html": text})
        else:
            send_json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/save":
            send_json(self, 404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            name = safe_name(data.get("name"))
            html = data.get("html")
        except (ValueError, TypeError, KeyError):
            send_json(self, 400, {"ok": False, "error": "bad request"})
            return
        if not name:
            send_json(self, 400,
                      {"ok": False,
                       "error": ("invalid name (must be a simple .html "
                                 "file name)")})
            return
        if not isinstance(html, str):
            send_json(self, 400, {"ok": False, "error": "missing html"})
            return
        path = resolve(name)
        if not path:
            send_json(self, 400, {"ok": False, "error": "invalid path"})
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
        except OSError as exc:
            send_json(self, 500, {"ok": False, "error": str(exc)})
            return
        send_json(self, 200,
                  {"ok": True, "name": os.path.basename(path),
                   "path": path, "bytes": len(html.encode("utf-8"))})


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Local web app to edit the Chrome tab HTML report.")
    ap.add_argument("--dir", default=None,
                    help="Directory of reports to manage (default: this "
                         "script's directory)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true",
                    help="Do not auto-open the browser")
    ap.add_argument("--no-chrome", action="store_true",
                    help="Disable importing tabs from the live Chrome "
                         "session (no session files are read)")
    args = ap.parse_args(argv)

    global BASE, ALLOW_CHROME
    ALLOW_CHROME = not args.no_chrome
    BASE = os.path.realpath(args.dir or os.path.dirname(
        os.path.abspath(__file__)))
    if not os.path.isdir(BASE):
        sys.exit("Directory not found: %s" % BASE)

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        sys.exit("Cannot start server on %s:%d (%s)" % (args.host,
                                                        args.port, exc))
    server.daemon_threads = True

    url = "http://%s:%d/" % (args.host, args.port)
    print("Chrome Report Editor: %s" % url)
    print("Managing directory:  %s" % BASE)
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()