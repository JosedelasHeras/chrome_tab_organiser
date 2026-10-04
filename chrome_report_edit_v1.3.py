#!/usr/bin/env python3
"""chrome_report_edit.py — local web app for editing the Chrome tab HTML report.

Run:
  python chrome_report_edit.py [--dir PATH] [--port 8765] [--host 127.0.0.1]
                               [--no-browser]

Starts a tiny stdlib HTTP server and opens the editor in your browser.
The editor lets you:
  - rename windows (click the "Window N" heading)
  - edit entries in place (group chip, tab name, URL)
  - delete entries (× on a row)
  - insert an entry into a chosen window at a chosen position (＋ / Add tab)
  - save the modified report to disk under a name you type

Only the standard library is used. The managed directory (--dir) defaults
to this script's own directory; all reports there ending in .html are
listed by the editor. Files are only ever written through an explicit save.
"""
import argparse
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.getcwd()

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
  #modal { position:fixed; inset:0; background:rgba(15,20,30,.35);
    display:none; align-items:center; justify-content:center; z-index:200; }
  #modal.open { display:flex; }
  #modal .box { background:#fff; border-radius:8px; padding:18px 20px;
    width:460px; max-width:92vw; box-shadow:0 8px 30px rgba(0,0,0,.18); }
  #modal h2 { margin:0 0 12px; font-size:15px; }
  #modal label { display:block; font-size:12px; color:var(--mut);
    margin:10px 0 4px; }
  #modal input, #modal select { width:100%; height:30px; font:inherit;
    font-size:13px; border:1px solid var(--line); border-radius:4px;
    padding:0 8px; }
  #modal .rowbtns { margin-top:16px; display:flex; justify-content:flex-end;
    gap:8px; }
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
  <label class="chk" title="Within each window, put tabs without a group first, then sort tab groups alphabetically">
    <input type="checkbox" id="sortGroups"> sort groups alphabetically
  </label>
  <span class="sep"></span>
  <span id="stats" title="windows / tabs / groups"></span>
  <span id="status"></span>
</header>
<div id="hint">Pick a report, or open a .html file, then edit: click text to
  rename (window, group, tab, URL); use +\u00a0/\u2715 buttons in the rows to
  insert or delete entries.</div>
<iframe id="preview"></iframe>
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
      refreshStats();
    });
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
      "button.ce-add:hover { background:#eef2fb; }"
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
    var head = win.querySelector(".window-head");
    if (head) head.appendChild(add);
  });

  d.querySelectorAll("tbody tr").forEach(setUpRow);

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
  refreshStats();
  closeModal();
  setStatus("Inserted into Window " + (win + 1) + ".");
}

/* add tab button in the window (from header) */

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
});
document.getElementById("fCancel").addEventListener("click", closeModal);
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
    args = ap.parse_args(argv)

    global BASE
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