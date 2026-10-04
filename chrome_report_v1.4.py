#!/usr/bin/env python3
"""chrome_report_v1.4.py — dump Chrome windows, tabs & tab groups into HTML.

Like chrome_report_v1.3.py (duplicate/contained windows are filtered out,
then each window is kept, dismissed or named interactively), with an
interactive HTML report:

  * --preserve_order ON (default) lists the tabs exactly in Chrome's tab
    strip order, so tab groups appear as the contiguous runs Chrome had.
    --preserve_order OFF lists ungrouped tabs first, then groups A-Z.

  * every window header has an action bar:
      - "Open window (grouped)" opens a second browser window with that
        window's tabs arranged as ungrouped-first, then one block per tab
        group in Chrome's own group order;
      - the group chips can be clicked to open just that group in a second
        browser window, with the group (name and colour) preserved.

  * if the companion extension in tab_organiser_ext/ is installed, each
    window can also be opened (and each group opened) as a REAL Chrome
    window with real Chrome tab groups - the source windows are left
    untouched (it copies, it never moves or closes anything). When it is
    missing, the badge at the top names the extension and links to
    tab_organiser_ext/install.html with the install steps.

Reads Chrome's own session-recovery files (the SNSS format written into
  <data dir>\\Default\\Sessions\\
while Chrome runs) and produces a self-contained HTML report plus a JSON
report. For every window it lists each tab organised by tab group
(group | tab name | url).

Usage:
  python chrome_report_v1.4.py [--data-dir PATH] [--outdir PATH] [--json]
                               [--keep-all] [--no-filter]
                               [--preserve_order ON|OFF]

Examples:
  python chrome_report_v1.4.py
  python chrome_report_v1.4.py --outdir reports --json
  python chrome_report_v1.4.py --no-filter --keep-all --preserve_order OFF

Notes:
  - Only the standard library is used; no pip installs required.
  - Output files (in --outdir, default current directory):
        chrome_tabs_Default_v1.4.html
        chrome_tabs_Default_v1.4.json  (only with --json)
  - Interactive prompting requires a terminal; for scripts pass --keep-all.
  - With --keep-all every window is kept with its default name.
  - --no-filter keeps every window that Chrome has open (no de-duplication).
  - The Chrome-side buttons need the optional unpacked extension in
    tab_organiser_ext/ (see its README.md); everything else works without it.
  - If Chrome is writing its session files at the moment you run this the
    script retries briefly; re-run after a few seconds if a warning shows.
"""
import argparse
import html
import json
import os
import re
import struct
import sys
import time
from collections import Counter
from urllib.parse import quote

SNSS_MAGIC = b"SNSS"

VERSION = "1.4"

DEFAULT_PROFILE = "Default"

EXT_DIR_NAME = "tab_organiser_ext"
EXT_NAME_FALLBACK = "Tab Organiser (report actions)"


def extension_display_name(ext_dir):
    """Extension name from its manifest, so the badge cannot drift."""
    try:
        with open(os.path.join(ext_dir, "manifest.json"), encoding="utf-8") as fh:
            name = json.load(fh).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, ValueError):
        pass
    return EXT_NAME_FALLBACK

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
        idx = p.u32()
        state.get_tab(tab)["current_hist"] = idx
    elif ctype == CMD_SET_SELECTED_TAB_IN_INDEX:
        win = p.u32()
        idx = p.u32()
        state.get_window(win)["active_tab_idx"] = idx
    elif ctype == CMD_TAB_CLOSED:
        tab = p.u32()
        state.get_tab(tab)["deleted"] = True
    elif ctype == CMD_WINDOW_CLOSED:
        win = p.u32()
        state.get_window(win)["deleted"] = True
    elif ctype == CMD_SET_ACTIVE_WINDOW:
        win = p.u32()
        state.active_window_id = win
    elif ctype == CMD_LAST_ACTIVE_TIME:
        pass
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


def build_model(state):
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
        active_pos = win["active_tab_idx"]
        for pos, tab in enumerate(tabs):
            url, title = resolve_tab(tab)
            group = tab["group"]
            rows.append({
                "url": url,
                "title": title,
                "group": group["name"] if group else None,
                "color": group.get("color") if group else None,
                "active": pos == active_pos,
            })
        windows.append({
            "id": win_id,
            "active": win_id == state.active_window_id,
            "name": None,
            "rows": rows,
        })
    return windows


def collect_profile(profile_dir, profile_name):
    files = session_files(os.path.join(profile_dir, "Sessions"))
    state = SessionState()
    used = []
    skipped = []
    for _gen, name, path in files:
        try:
            read_session_file(path, state)
            used.append(path)
        except (PermissionError, OSError):
            skipped.append((path, "in use by Chrome"))
        except (ValueError, struct.error):
            skipped.append((path, "not a readable session file"))
    windows = build_model(state)
    groups = sorted(set(g["name"] for g in state.groups.values() if g["name"]))
    return {"profile": profile_name, "files": used, "skipped": skipped,
            "windows": windows, "state": state,
            "group_names": groups}


def output_file_name(ext):
    return "chrome_tabs_%s_v%s.%s" % (DEFAULT_PROFILE, VERSION, ext)


def window_groups(win):
    return sorted({row["group"] for row in win["rows"] if row["group"]})


def window_brief(win):
    groups = window_groups(win)
    names = list(groups[:5])
    if len(names) < 5:
        for row in win["rows"]:
            if len(names) >= 5:
                break
            title = (row["title"] or "").strip() or "(no title)"
            if title not in names:
                names.append(title)
    return groups, names


def window_signature(win):
    """Multiset of (group, url) for a window; tab titles are ignored."""
    return Counter((row["group"] or "", row["url"]) for row in win["rows"])


def filter_windows(windows):
    """Drop duplicate windows and windows contained in larger ones.

    Returns (kept, dropped) where dropped is a list of
    (original_index, reason) pairs; reasons name the original numbering.
    """
    sigs = [window_signature(win) for win in windows]
    seen = {}
    dropped = []
    pool = []
    for index, sig in enumerate(sigs):
        token = tuple(sorted(sig.items()))
        if token in seen:
            dropped.append((index, "duplicate of Window %d" % (seen[token] + 1)))
        else:
            seen[token] = index
            pool.append(index)
    while True:
        target = None
        for position, index in enumerate(pool):
            for other in pool:
                if index == other:
                    continue
                if (sigs[index] <= sigs[other]
                        and len(windows[index]["rows"])
                        < len(windows[other]["rows"])):
                    target = (position, index, other)
                    break
            if target:
                break
        if not target:
            break
        position, index, other = target
        dropped.append((index, "contained in Window %d" % (other + 1)))
        del pool[position]
    dropped_indexes = {index for index, _reason in dropped}
    kept = [win for index, win in enumerate(windows)
            if index not in dropped_indexes]
    return kept, dropped


def unique_name(name, used):
    """Return name, or name_N if already taken (case-insensitive)."""
    if name.lower() not in used:
        return name
    index = 1
    while ("%s_%d" % (name, index)).lower() in used:
        index += 1
    return "%s_%d" % (name, index)


def assign_default_names(windows):
    used = set()
    for pos, win in enumerate(windows, start=1):
        name = unique_name("Window %d" % pos, used)
        used.add(name.lower())
        win["name"] = name
    return windows


def ask_keep_windows(windows, keep_all):
    if keep_all:
        return assign_default_names(windows)
    if not sys.stdin.isatty():
        sys.exit("stdin is not a terminal; pass --keep-all to run without "
                 "interactive prompts")
    used = set()
    kept = []
    total = len(windows)
    for pos, win in enumerate(windows, start=1):
        default = "Window %d" % pos
        groups, names = window_brief(win)
        print()
        print("[%d/%d] %s — %d tab(s), %d group(s)"
              % (pos, total, default, len(win["rows"]), len(groups)))
        print("  " + (", ".join(names) if names else "(no tabs)"))
        try:
            answer = input(
                "Keep, discard, or type a name [K/d/name]: ").strip()
        except EOFError:
            sys.exit("input closed — aborting, no report written")
        except KeyboardInterrupt:
            sys.exit("interrupted — no report written")
        if answer.lower() == "d":
            print("  dismissed.")
            continue
        if answer == "" or answer.lower() == "k":
            wanted = default
        else:
            wanted = answer
        name = unique_name(wanted, used)
        used.add(name.lower())
        win["name"] = name
        kept.append(win)
        print("  kept as \"%s\"" % name)
    print()
    print("Kept %d of %d windows." % (len(kept), total))
    return kept


def escape(text):
    return html.escape(text or "", quote=True)


CORE_JS = r"""
(function () {
  var EXT_IN = 'tab-organiser-report';
  var EXT_OUT = 'tab-organiser-ext';
  var CONFIRM_LIMIT = 40;
  var EXT_NAME = __EXT_NAME__;
  var EXT_INSTALL_URL = __EXT_INSTALL_URL__;

  function status(text, isError) {
    var el = document.getElementById('action-status');
    if (!el) { return; }
    el.textContent = text || '';
    el.className = isError ? 'status err' : 'status';
  }

  function badge(text, on) {
    var el = document.getElementById('ext-status');
    if (!el) { return; }
    el.textContent = text;
    el.className = on ? 'badge on' : 'badge';
  }

  function badgeMissing() {
    var el = document.getElementById('ext-status');
    if (!el) { return; }
    el.className = 'badge';
    el.textContent = 'extension not installed - ';
    if (!EXT_INSTALL_URL) {
      el.appendChild(document.createTextNode(EXT_NAME));
      el.appendChild(document.createTextNode(
        ' - Chrome-side actions disabled'));
      return;
    }
    var link = document.createElement('a');
    link.href = EXT_INSTALL_URL;
    link.target = '_blank';
    link.rel = 'noopener';
    link.title = 'open the install instructions';
    link.textContent = EXT_NAME;
    el.appendChild(link);
    el.appendChild(document.createTextNode(
      ' - Chrome-side actions disabled'));
  }

  function extCall(action, payload, timeoutMs) {
    return new Promise(function (resolve, reject) {
      var id = Math.random().toString(36).slice(2);
      var timer = setTimeout(function () {
        window.removeEventListener('message', onMessage);
        reject(new Error('the extension did not respond - is it installed?'));
      }, timeoutMs || 30000);
      function onMessage(event) {
        var data = event.data;
        if (!data || data.src !== EXT_OUT || data.id !== id) { return; }
        window.removeEventListener('message', onMessage);
        clearTimeout(timer);
        if (data.ok) { resolve(data.result); } else { reject(new Error(data.error)); }
      }
      window.addEventListener('message', onMessage);
      window.postMessage({src: EXT_IN, id: id, action: action, payload: payload || {}}, '*');
    });
  }

  function escapeAttr(text) {
    return String(text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function rowUrl(tr) {
    var a = tr.querySelector('td.url a');
    return a ? (a.getAttribute('href') || '') : '';
  }

  function rowGroup(tr) {
    var chip = tr.querySelector('td.group .chip');
    if (!chip || chip.classList.contains('none')) { return ''; }
    return chip.getAttribute('data-group') || '';
  }

  function rowsInSection(section) {
    return Array.prototype.slice.call(section.querySelectorAll('tbody tr'));
  }

  function chipsInSection(section) {
    return Array.prototype.slice.call(section.querySelectorAll('.chip-act'));
  }

  function windowLabel(section) {
    var el = section.querySelector('.wname');
    return el ? el.textContent : 'Window';
  }

  function payloadForGroup(section, chip) {
    var name = chip.getAttribute('data-group');
    var rows = rowsInSection(section).filter(function (tr) { return rowGroup(tr) === name; });
    var urls = rows.map(rowUrl).filter(function (u) { return !!u; });
    return {group: name, color: chip.getAttribute('data-color') || '', urls: urls, rows: rows.length};
  }

  function payloadForWindow(section) {
    var all = rowsInSection(section);
    var ungrouped = all.filter(function (tr) { return !rowGroup(tr); })
      .map(rowUrl).filter(function (u) { return !!u; });
    var groups = chipsInSection(section).map(function (chip) {
      var name = chip.getAttribute('data-group');
      var rows = all.filter(function (tr) { return rowGroup(tr) === name; });
      return {group: name, color: chip.getAttribute('data-color') || '',
              urls: rows.map(rowUrl).filter(function (u) { return !!u; })};
    }).filter(function (g) { return g.urls.length; });
    return {ungrouped: ungrouped, groups: groups};
  }

  function confirmIfLarge(count) {
    if (count <= CONFIRM_LIMIT) { return true; }
    return window.confirm('This will open ' + count +
      ' new tabs in Chrome.\nContinue?');
  }

  function chromeOpenGroup(section, chip) {
    var payload = payloadForGroup(section, chip);
    if (!payload.urls.length) {
      status('group "' + payload.group + '" has no URLs to open', true);
      return;
    }
    if (!confirmIfLarge(payload.urls.length)) { return; }
    status('opening group "' + payload.group + '" in Chrome...');
    extCall('open-group', payload).then(function (result) {
      status('opened ' + (result.tabs || 0) + ' tab(s) as a new Chrome group' +
             (result.groupId ? ' (group id ' + result.groupId + ')' : ''));
    }).catch(function (err) { status(err.message, true); });
  }

  function chromeOpenWindow(section) {
    var payload = payloadForWindow(section);
    var count = payload.ungrouped.length;
    payload.groups.forEach(function (g) { count += g.urls.length; });
    if (!count) { status('this window has no URLs to open', true); return; }
    if (!confirmIfLarge(count)) { return; }
    status('opening ' + count + ' tab(s) in a new Chrome window...');
    extCall('open-window', payload).then(function (result) {
      status('opened ' + (result.tabs || 0) + ' tab(s) in ' + (result.groups || 0) +
             ' Chrome group(s)');
    }).catch(function (err) { status(err.message, true); });
  }

  document.addEventListener('click', function (event) {
    var el = event.target && event.target.closest
      ? event.target.closest('[data-action^="chrome-"]') : null;
    if (!el) { return; }
    var section = el.closest('section.window');
    if (el.getAttribute('data-action') === 'chrome-group') {
      chromeOpenGroup(section, el);
    } else if (el.getAttribute('data-action') === 'chrome-window') {
      chromeOpenWindow(section);
    }
  });

  function enableChromeButtons(enabled) {
    var buttons = document.querySelectorAll('[data-action^="chrome-"]');
    Array.prototype.forEach.call(buttons, function (button) {
      button.disabled = !enabled;
    });
  }

  function detectExtension() {
    var tries = 0;
    function check() {
      if (document.documentElement.getAttribute('data-tab-organiser-ext') === 'ready') {
        badge('extension connected - Chrome-side actions available', true);
        enableChromeButtons(true);
        return;
      }
      if (tries < 40) { tries += 1; window.setTimeout(check, 100); return; }
      badgeMissing();
      enableChromeButtons(false);
    }
    check();
  }

  detectExtension();
  window.TAB_ORGANISER = {extCall: extCall, status: status, badge: badge};
})();
"""


VIEW_JS = r"""
(function () {
  var T = window.TAB_ORGANISER;
  if (!T) { return; }

  function escapeText(text) {
    var d = document.createElement('span');
    d.textContent = text == null ? '' : text;
    return d.innerHTML;
  }

  function escapeAttr(text) {
    return escapeText(text).replace(/"/g, '&quot;');
  }

  function rowUrl(tr) {
    var a = tr.querySelector('td.url a');
    return a ? (a.getAttribute('href') || '') : '';
  }

  function rowGroup(tr) {
    var chip = tr.querySelector('td.group .chip');
    if (!chip || chip.classList.contains('none')) { return ''; }
    return chip.getAttribute('data-group') || '';
  }

  function rowsInSection(section) {
    return Array.prototype.slice.call(section.querySelectorAll('tbody tr'));
  }

  function chipsInSection(section) {
    return Array.prototype.slice.call(section.querySelectorAll('.chip-act'));
  }

  function cssText() {
    var style = document.querySelector('style');
    return style ? style.outerHTML : '';
  }

  function popup(title, subtitle, bodyHtml) {
    var win = window.open('', '_blank');
    if (!win) { T.status('popup blocked - please allow popups for this page', true); return null; }
    var doc = '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">' +
      '<title>' + escapeText(title) + '</title>' + cssText() + '</head><body>' +
      '<header><h1>' + escapeText(title) + '</h1>' +
      '<div class="meta">' + escapeText(subtitle) + '</div>' +
      '<div class="status"><span class="badge" id="ext-status">checking extension...</span>' +
      ' <span id="action-status"></span></div></header>' + bodyHtml +
      '<script>' + CORE_JS + '<\/script>' +
      '</body></html>';
    win.document.open();
    win.document.write(doc);
    win.document.close();
    return win;
  }

  function sectionHtml(title, rows, actionsHtml) {
    return '<section class="window"><div class="window-head"><h3>' +
      escapeText(title) + '</h3></div>' + (actionsHtml || '') +
      '<table><thead><tr><th>Group</th><th>Tab</th><th>URL</th></tr></thead><tbody>' +
      rows.map(function (tr) { return tr.outerHTML; }).join('\n') +
      '</tbody></table></section>';
  }

  function windowLabel(section) {
    var el = section.querySelector('.wname');
    return el ? el.textContent : 'Window';
  }

  function openGroupView(section, chip) {
    var name = chip.getAttribute('data-group');
    var color = chip.getAttribute('data-color') || '';
    var rows = rowsInSection(section).filter(function (tr) { return rowGroup(tr) === name; });
    if (!rows.length) { T.status('no rows found for group ' + name, true); return; }
    popup('Group: ' + name,
          windowLabel(section) + ' - ' + rows.length + ' tab(s), ' +
          rows.length + ' will open in one new window',
          '<div class="window-actions">' +
          '<button class="btn" data-action="chrome-group" data-group="' +
          escapeAttr(name) + '" data-color="' + escapeAttr(color) + '" disabled>' +
          'Open group in Chrome</button></div>' +
          sectionHtml('Group "' + name + '" - ' + rows.length + ' tab(s)', rows, ''));
    T.status('opened group "' + name + '" (' + rows.length + ' tabs) in a new window');
  }

  function openWindowView(section) {
    var label = windowLabel(section);
    var all = rowsInSection(section);
    var body = '';
    var ungrouped = all.filter(function (tr) { return !rowGroup(tr); });
    if (ungrouped.length) {
      body += sectionHtml(label + ' - ungrouped (' + ungrouped.length + ')', ungrouped, '');
    }
    chipsInSection(section).forEach(function (chip) {
      var name = chip.getAttribute('data-group');
      var rows = all.filter(function (tr) { return rowGroup(tr) === name; });
      if (!rows.length) { return; }
      body += '<div class="window-actions"><button class="btn" data-action="chrome-group"' +
        ' data-group="' + escapeAttr(name) + '" data-color="' +
        escapeAttr(chip.getAttribute('data-color')) + '" disabled>Open group in Chrome</button></div>' +
        sectionHtml(name + ' (' + rows.length + ')', rows, '');
    });
    popup(label + ' - grouped',
          all.length + ' tab(s) - ungrouped first, then groups in Chrome order',
          body);
    T.status('opened "' + label + '" (' + all.length + ' tabs) grouped, in a new window');
  }

  document.addEventListener('click', function (event) {
    var el = event.target && event.target.closest
      ? event.target.closest('[data-action^="open-"]') : null;
    if (!el) { return; }
    var section = el.closest('section.window');
    if (el.getAttribute('data-action') === 'open-group') { openGroupView(section, el); }
    else if (el.getAttribute('data-action') === 'open-window') { openWindowView(section); }
  });
})();
"""

def build_report_js(ext_dir):
    """Inline the core bridge into popups, then fill in extension details."""
    name = extension_display_name(ext_dir)
    install_page = os.path.join(ext_dir, "install.html")
    url = ""
    if os.path.isfile(install_page):
        url = "file:///" + quote(install_page.replace("\\", "/"), safe="/:")
    core = CORE_JS.replace("__EXT_NAME__", json.dumps(name))
    core = core.replace("__EXT_INSTALL_URL__", json.dumps(url))
    view = VIEW_JS.replace("CORE_JS", json.dumps(core))
    return core + "\n" + view


REPORT_JS = build_report_js(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), EXT_DIR_NAME))


def ordered_rows(win, preserve_order):
    """Rows in Chrome's tab strip order, or grouped order when off."""
    pairs = list(enumerate(win["rows"]))
    if not preserve_order:
        pairs.sort(key=lambda pair: (
            (1 if pair[1]["group"] else 0),
            pair[1]["group"] or "",
            pair[0]))
    return [row for _pos, row in pairs]


def render_html(profile, generated, preserve_order=True):
    total_windows = len(profile["windows"])
    total_tabs = sum(len(w["rows"]) for w in profile["windows"])
    total_groups = len(profile["group_names"])

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang=\"en\">")
    parts.append("<head>")
    parts.append("<meta charset=\"utf-8\">")
    parts.append("<meta name=\"viewport\" "
                 "content=\"width=device-width, initial-scale=1\">")
    parts.append("<title>Chrome windows &amp; tabs &mdash; %s</title>"
                 % escape(profile["profile"]))
    parts.append("""<style>
      :root { --bg:#f6f7f9; --card:#ffffff; --ink:#1f2430; --mut:#6b7280;
      --line:#e5e7eb; --accent:#1a73e8; }
      * { box-sizing:border-box; }
      body { margin:0; font-family:Segoe UI, system-ui, Arial, sans-serif;
      background:var(--bg); color:var(--ink); }
      header { background:var(--card); border-bottom:1px solid var(--line);
      padding:24px 32px; }
      h1 { margin:0 0 6px; font-size:22px; }
      .meta { color:var(--mut); font-size:13px; }
      .stats { margin-top:10px; font-size:13px; }
      .stats b { color:var(--accent); }
      main { padding:24px 32px; max-width:1200px; }
      .profile-meta { color:var(--mut); font-size:12px; margin:0 0 18px; }
      .window { background:var(--card); border:1px solid var(--line);
      border-radius:8px; margin:0 0 20px; overflow:hidden; }
      .window-head { padding:12px 16px; border-bottom:1px solid var(--line);
      display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
      .window-head h3 { margin:0; font-size:15px; }
      .window-head .wname { font-weight:600; }
      .win-meta { font-size:12px; color:var(--mut); }
      .active-star { color:#f29900; }
      table { width:100%; border-collapse:collapse; font-size:13px; }
      th { text-align:left; background:#fafafa; color:var(--mut);
      font-weight:600; padding:6px 12px; border-bottom:1px solid var(--line);
      font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
      td { padding:5px 12px; border-bottom:1px solid var(--line);
      vertical-align:top; word-break:break-word; }
      tr:last-child td { border-bottom:none; }
      td.group { width:16%; }
      td.tab { width:44%; }
      td.url { width:40%; }
      a { color:var(--accent); text-decoration:none; }
      a:hover { text-decoration:underline; }
      .chip { display:inline-block; padding:1px 8px; border-radius:10px;
      color:#fff; font-size:12px; max-width:100%; overflow:hidden;
      text-overflow:ellipsis; white-space:nowrap; vertical-align:middle; }
      .chip.none { background:#eef0f3; color:#9aa0a6; }
      .url-text { color:#5f6368; font-size:12px; }
      .window-actions { display:flex; gap:8px; flex-wrap:wrap;
      padding:10px 16px; border-bottom:1px solid var(--line); background:#fafbfc; }
      .btn { font:inherit; font-size:12px; padding:5px 12px; cursor:pointer;
      border:1px solid var(--line); border-radius:6px; background:var(--card);
      color:var(--ink); }
      .btn:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
      .btn:disabled { opacity:.45; cursor:not-allowed; }
      .group-chips { display:flex; gap:8px; flex-wrap:wrap; }
      .chip-act { display:inline-flex; align-items:center; gap:6px;
      font:inherit; font-size:12px; padding:3px 10px; cursor:pointer;
      border:1px solid var(--line); border-radius:12px; background:var(--card); }
      .chip-act:hover { border-color:var(--accent); }
      .chip-act .dot { width:9px; height:9px; border-radius:50%;
      display:inline-block; }
      .status { margin-top:10px; font-size:13px; display:flex; gap:8px;
      align-items:center; flex-wrap:wrap; }
      .status .err { color:#c5221f; }
      .badge { font-size:12px; padding:2px 10px; border-radius:12px;
      background:#eef0f3; color:#5f6368; }
      .badge.on { background:#e6f4ea; color:#137333; }
      .badge a { color:#1a73e8; text-decoration:underline; }
      .badge a:hover { color:#1558b0; }
      footer { color:var(--mut); font-size:12px; padding:0 32px 32px; }
    </style>""")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<header>")
    parts.append("<h1>Chrome windows &amp; tabs &mdash; %s</h1>"
                 % escape(profile["profile"]))
    parts.append('<div class="meta">Generated %s</div>' % escape(generated))
    parts.append('<div class="stats">%d windows &middot; %d tabs &middot; '
                 '%d tab groups</div>'
                 % (total_windows, total_tabs, total_groups))
    parts.append('<div class="profile-meta">Tab order: <b>%s</b> (%s)</div>'
                 % ("Chrome order" if preserve_order else "grouped order",
                    "exactly as in the tab strip, groups stay contiguous"
                    if preserve_order else
                    "ungrouped first, then groups A-Z"))
    parts.append('<div class="status">'
                 '<span class="badge" id="ext-status">checking extension...</span>'
                 '<span id="action-status"></span></div>')
    parts.append("</header>")

    parts.append("<main>")
    if profile["skipped"]:
        parts.append('<div class="profile-meta">Could not read '
                     '%d session file(s): %s'
                     % (len(profile["skipped"]),
                        escape("; ".join("(%s, %s)" % (
                            os.path.basename(p), reason)
                            for p, reason in profile["skipped"]))))
        parts.append('<div class="profile-meta">Re-run in a few seconds if '
                     'recent tabs are missing.</div>')
    else:
        parts.append('<div class="profile-meta">Sources: %s</div>'
                     % escape(", ".join(
                         os.path.basename(p)
                         for p in profile["files"])))

    seen_groups = {}
    for windex, win in enumerate(profile["windows"]):
        name = win.get("name") or "Window %d" % (windex + 1)
        rows = ordered_rows(win, preserve_order)
        tabs_in_window = len(rows)
        group_names = []
        for row in rows:
            if row["group"] and row["group"] not in group_names:
                group_names.append(row["group"])

        parts.append('<section class="window">')
        parts.append('<div class="window-head">')
        parts.append('<h3><span class="wname">%s</span></h3>'
                     % escape(name))
        parts.append('<span class="win-meta">%d tabs'
                     % tabs_in_window)
        if group_names:
            parts.append(' &middot; %d group(s)'
                         % len(group_names))
        if win["active"]:
            parts.append(' &middot; <b>active window</b>')
        parts.append('</span></div>')

        parts.append('<div class="window-actions">')
        parts.append('<button class="btn" data-action="open-window">'
                     'Open window (grouped)</button>')
        parts.append('<button class="btn" data-action="chrome-window" disabled>'
                     'Open window in Chrome</button>')
        for gname in group_names:
            gid = "g%d" % seen_groups.setdefault(gname, len(seen_groups))
            color = GROUP_COLORS.get(
                next((r["color"] for r in rows if r["group"] == gname), ""),
                "#5f6368")
            parts.append('<button class="chip-act" data-action="open-group" '
                         'data-group="%s" data-color="%s" data-gid="%s" '
                         'title="open group &quot;%s&quot; in a new window">'
                         '<span class="dot" style="background:%s"></span>%s</button>'
                         % (escape(gname), escape(color), gid,
                            escape(gname), color, escape(gname)))
        parts.append('</div>')

        parts.append('<table>')
        parts.append('<thead><tr><th>Group</th><th>Tab</th>'
                     '<th>URL</th></tr></thead>')
        parts.append('<tbody>')
        for position, row in enumerate(rows, start=1):
            if row["group"]:
                color = GROUP_COLORS.get(row["color"], "#5f6368")
                chip = ('<span class="chip" style="background:%s" '
                        'data-group="%s">%s</span>'
                        % (color, escape(row["group"]), escape(row["group"])))
            else:
                chip = '<span class="chip none"></span>'
            tab_cell = escape(row["title"]) or "(no title)"
            if row["url"]:
                link = escape(row["url"])
                tab_cell = ('<a href="%s" title="%s">%s</a>'
                            % (link, link, tab_cell))
            url_cell = ""
            if row["url"]:
                url_cell = ('<a class="url-text" href="%s">%s</a>'
                            % (escape(row["url"]), escape(row["url"])))
            star = '<span class="active-star">&#9733;</span> ' \
                if row["active"] else ""
            parts.append('<tr data-pos="%d"><td class="group">%s</td>'
                         '<td class="tab">%s%s</td>'
                         '<td class="url">%s</td></tr>'
                         % (position, chip, star, tab_cell, url_cell))
        parts.append('</tbody></table>')
        parts.append('</section>')
    parts.append("</main>")

    parts.append("<script>%s</script>" % REPORT_JS)

    parts.append('<footer>Report generated by chrome_report_v%s.py '
                 '&middot; links open in your default browser.</footer>'
                 % VERSION)
    parts.append("</body></html>")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Collect Chrome windows/tabs organized by tab group "
                    "into an HTML report for the Default profile.")
    ap.add_argument("--data-dir", default=None,
                    help="Chrome profile data directory (default: auto-detect)")
    ap.add_argument("--outdir", default=".",
                    help="Output directory (default: current directory)")
    ap.add_argument("--json", action="store_true",
                    help="Also write parsed data as "
                         "chrome_tabs_Default_v%s.json" % VERSION)
    ap.add_argument("--keep-all", action="store_true",
                    help="Keep all windows without prompting "
                         "(same behaviour as chrome_report_v1.1.py)")
    ap.add_argument("--no-filter", action="store_true",
                    help="Do not drop duplicate windows or windows contained "
                         "in larger ones before prompting")
    ap.add_argument("--preserve_order", "--preserve-order", dest="preserve_order",
                    choices=("ON", "OFF"), default="ON",
                    help="ON (default) lists tabs in Chrome's tab strip order "
                         "so groups stay contiguous; OFF lists ungrouped tabs "
                         "first, then groups A-Z")
    args = ap.parse_args(argv)
    preserve_order = args.preserve_order == "ON"

    data_dir = args.data_dir or default_data_dir()
    if not os.path.isdir(data_dir):
        sys.exit("Data directory not found: %s" % data_dir)

    profile_dir = os.path.join(data_dir, DEFAULT_PROFILE)
    if not os.path.exists(os.path.join(profile_dir, "Preferences")):
        sys.exit("Default profile not found under %s" % data_dir)

    profile = collect_profile(profile_dir, DEFAULT_PROFILE)

    total_windows = len(profile["windows"])
    total_tabs = sum(len(w["rows"]) for w in profile["windows"])
    total_groups = len(profile["group_names"])

    print("Profile:  %s" % profile["profile"])
    print("Windows:  %d" % total_windows)
    print("Tabs:     %d" % total_tabs)
    print("Groups:   %d" % total_groups)
    if profile["skipped"]:
        print("  warning: skipped %s"
              % "; ".join("(%s, %s)" % (os.path.basename(p), reason)
                          for p, reason in profile["skipped"]))
        print("           re-run in a few seconds if recent tabs are "
              "missing")

    if not args.no_filter:
        profile["windows"], dropped = filter_windows(profile["windows"])
        if dropped:
            print()
            print("Filtering windows (duplicates and windows contained in "
                  "others):")
            for index, reason in dropped:
                print("  Window %d dropped — %s" % (index + 1, reason))
            print("  %d of %d windows remain."
                  % (len(profile["windows"]), total_windows))
        if not profile["windows"]:
            sys.exit("All windows were filtered out — nothing to write.")

    profile["windows"] = ask_keep_windows(profile["windows"], args.keep_all)
    if not profile["windows"]:
        sys.exit("All windows dismissed — nothing to write.")
    profile["group_names"] = sorted(
        {row["group"] for win in profile["windows"]
         for row in win["rows"] if row["group"]})

    if not os.path.isdir(args.outdir):
        os.makedirs(args.outdir)

    generated = time.strftime("%Y-%m-%d %H:%M:%S")
    html_path = os.path.join(args.outdir, output_file_name("html"))
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(profile, generated, preserve_order))
    print("Report written to %s" % html_path)
    print("Tab order: %s" % ("Chrome strip order" if preserve_order
                             else "grouped order (ungrouped first, A-Z)"))

    if args.json:
        json_path = os.path.join(args.outdir, output_file_name("json"))
        data = {
            "profile": profile["profile"],
            "generated": generated,
            "order": "ON" if preserve_order else "OFF",
            "files": profile["files"],
            "groups": profile["group_names"],
            "windows": [{
                "id": w["id"],
                "name": w.get("name") or "Window %d" % (windex + 1),
                "active": w["active"],
                "tabs": ordered_rows(w, preserve_order),
            } for windex, w in enumerate(profile["windows"])],
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print("JSON written to %s" % json_path)


if __name__ == "__main__":
    main()