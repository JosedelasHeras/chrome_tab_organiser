#!/usr/bin/env python3
"""chrome_report.py — dump Chrome windows, tabs & tab groups into an HTML report.

Reads Chrome's own session-recovery files (the SNSS format written into
  <data dir>\\<profile>\\Sessions\\
while Chrome runs) and produces a self-contained HTML report. For every
window it lists each tab organised by tab group (group | tab name | url).

Usage:
  python chrome_report.py [--data-dir PATH] [--profile NAME]...
                          [--output PATH] [--json [PATH]] [--no-prompt]

Examples:
  python chrome_report.py --no-prompt
  python chrome_report.py --profile "Profile 1" --ask-names
  python chrome_report.py --json report.json --no-prompt

Notes:
  - Only the standard library is used; no pip installs required.
  - Window names are taken from your input at the prompt (or auto-derived
    from the active tab title when run non-interactively).
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

SNSS_MAGIC = b"SNSS"

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


def find_profiles(data_dir):
    profiles = []
    for name in sorted(os.listdir(data_dir)):
        if name in ("System Profile", "Guest Profile", "Snapshots"):
            continue
        session_dir = os.path.join(data_dir, name, "Sessions")
        if os.path.isdir(session_dir):
            profiles.append(name)
    return profiles


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
    groups = sorted(g["name"] for g in state.groups.values() if g["name"])
    return {"profile": profile_name, "files": used, "skipped": skipped,
            "windows": windows, "state": state,
            "group_names": groups}


def auto_window_name(rows, index):
    for row in rows:
        if row["active"] and row["title"]:
            return row["title"]
    for row in rows:
        if row["title"]:
            return row["title"]
    return "Window %d" % (index + 1)


def ask_window_names(collected):
    print()
    print("Name each window (press Enter to accept the suggested name).")
    print()
    names = {}
    counter = 0
    windows_total = sum(len(c["windows"]) for c in collected)
    for profile in collected:
        for windex, win in enumerate(profile["windows"]):
            counter += 1
            name = auto_window_name(win["rows"], windex)
            title = next((r["title"] for r in win["rows"] if r["active"]
                          and r["title"]), name)
            print("  [%d/%d] %s - Window %d (%d tabs)"
                  % (counter, windows_total, profile["profile"],
                     win["id"], len(win["rows"])))
            try:
                resp = input("    name [%s]: " % title).strip()
            except (EOFError, KeyboardInterrupt):
                names[(profile["profile"], win["id"])] = name
                continue
            names[(profile["profile"], win["id"])] = resp or name
    print()
    return names


def escape(text):
    return html.escape(text or "", quote=True)


def render_html(collected, names, generated):
    total_windows = sum(len(c["windows"]) for c in collected)
    total_tabs = sum(len(w["rows"]) for c in collected
                     for w in c["windows"])
    total_groups = len(set(g for c in collected for g in c["group_names"]))

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang=\"en\">")
    parts.append("<head>")
    parts.append("<meta charset=\"utf-8\">")
    parts.append("<meta name=\"viewport\" "
                 "content=\"width=device-width, initial-scale=1\">")
    parts.append("<title>Chrome windows &amp; tabs report</title>")
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
      h2.profile { margin:8px 0 4px; font-size:17px; border-bottom:2px solid
      var(--line); padding-bottom:6px; }
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
      footer { color:var(--mut); font-size:12px; padding:0 32px 32px; }
    </style>""")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<header>")
    parts.append("<h1>Chrome windows &amp; tabs report</h1>")
    parts.append('<div class="meta">Generated %s</div>' % escape(generated))
    parts.append('<div class="stats">%d windows &middot; %d tabs &middot; '
                 '%d tab groups across %d profile(s)</div>'
                 % (total_windows, total_tabs, total_groups,
                    len(collected)))
    parts.append("</header>")

    parts.append("<main>")
    for profile in collected:
        parts.append('<h2 class="profile">Profile: %s</h2>'
                     % escape(profile["profile"]))
        if profile["skipped"]:
            parts.append('<div class="profile-meta">Could not read '
                         '%d session file(s) %s: %s</div>'
                         % (len(profile["skipped"]),
                            escape("; ".join("(%s, %s)" % (
                                os.path.basename(p), reason)
                                for p, reason in profile["skipped"])),
                            "re-run in a few seconds if recent tabs are "
                            "missing"))
        else:
            parts.append('<div class="profile-meta">Sources: %s</div>'
                         % escape(", ".join(
                             os.path.basename(p)
                             for p in profile["files"])))

        for windex, win in enumerate(profile["windows"]):
            name = names.get((profile["profile"], win["id"]),
                             auto_window_name(win["rows"], windex))
            tabs_in_window = len(win["rows"])
            group_names = sorted({r["group"] for r in win["rows"]
                                  if r["group"]})
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

            ordered = list(enumerate(win["rows"]))
            ordered.sort(key=lambda pair: (
                    (1 if pair[1]["group"] else 0),
                    pair[1]["group"] or "",
                    pair[0]))

            parts.append('<table>')
            parts.append('<thead><tr><th>Group</th><th>Tab</th>'
                         '<th>URL</th></tr></thead>')
            parts.append('<tbody>')
            for _pos, row in ordered:
                if row["group"]:
                    color = GROUP_COLORS.get(row["color"], "#5f6368")
                    chip = ('<span class="chip" style="background:%s">%s</span>'
                            % (color, escape(row["group"])))
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
                parts.append('<tr><td class="group">%s</td>'
                             '<td class="tab">%s%s</td>'
                             '<td class="url">%s</td></tr>'
                             % (chip, star, tab_cell, url_cell))
            parts.append('</tbody></table>')
            parts.append('</section>')
    parts.append("</main>")

    parts.append('<footer>Report generated by chrome_report.py &middot; '
                 'links open in your default browser.</footer>')
    parts.append("</body></html>")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Collect Chrome windows/tabs organized by tab group "
                    "into an HTML report.")
    ap.add_argument("--data-dir", default=None,
                    help="Chrome profile data directory (default: auto-detect)")
    ap.add_argument("--profile", action="append", default=[], metavar="NAME",
                    help="Only include this profile (repeatable; "
                         "default: all profiles)")
    ap.add_argument("--output", default="chrome_tabs_report.html",
                    help="Output HTML file (default: chrome_tabs_report.html)")
    ap.add_argument("--json", nargs="?", const="__auto__", default=None,
                    metavar="PATH", help="Also write parsed data as JSON")
    ap.add_argument("--no-prompt", action="store_true",
                    help="Do not ask for window names; auto-name windows "
                         "from their active tab title")
    ap.add_argument("--ask-names", action="store_true",
                    help="Always prompt for window names even when input "
                         "is not a terminal")
    args = ap.parse_args(argv)

    data_dir = args.data_dir or default_data_dir()
    if not os.path.isdir(data_dir):
        sys.exit("Data directory not found: %s" % data_dir)

    profiles = find_profiles(data_dir)
    if not profiles:
        sys.exit("No Chrome profiles found under %s" % data_dir)
    if args.profile:
        wanted = set(p.lower() for p in args.profile)
        profiles = [p for p in profiles if p.lower() in wanted]
        if not profiles:
            sys.exit("Requested profile(s) not found: %s"
                     % ", ".join(args.profile))

    collected = []
    for name in profiles:
        profile_dir = os.path.join(data_dir, name)

        _pref = os.path.join(profile_dir, "Preferences")
        if not os.path.exists(_pref):
            continue
        collected.append(collect_profile(profile_dir, name))

    if not collected:
        sys.exit("Nothing parsed - no usable session files.")

    total_windows = sum(len(c["windows"]) for c in collected)
    total_tabs = sum(len(w["rows"]) for c in collected for w in c["windows"])
    total_groups = len(set(g for c in collected for g in c["group_names"]))

    print("Profiles: %s" % ", ".join(c["profile"] for c in collected))
    print("Windows:  %d" % total_windows)
    print("Tabs:     %d" % total_tabs)
    print("Groups:   %d" % total_groups)
    for c in collected:
        if c["skipped"]:
            print("  warning: skipped %s"
                  % "; ".join("(%s, %s)" % (os.path.basename(p), reason)
                              for p, reason in c["skipped"]))
            print("           re-run in a few seconds if recent tabs are "
                  "missing")

    should_ask = args.ask_names or (not args.no_prompt and sys.stdin.isatty())
    if should_ask:
        names = ask_window_names(collected)
    else:
        names = {}
        for c in collected:
            for windex, win in enumerate(c["windows"]):
                names[(c["profile"], win["id"])] = auto_window_name(
                    win["rows"], windex)

    generated = time.strftime("%Y-%m-%d %H:%M:%S")
    html_text = render_html(collected, names, generated)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    print("Report written to %s" % args.output)

    if args.json:
        json_path = args.json
        if json_path == "__auto__":
            json_path = os.path.splitext(args.output)[0] + ".json"
        data = []
        for c in collected:
            data.append({
                "profile": c["profile"],
                "files": c["files"],
                "groups": c["group_names"],
                "windows": [{
                    "id": w["id"],
                    "active": w["active"],
                    "name": names.get((c["profile"], w["id"]), ""),
                    "tabs": w["rows"],
                } for w in c["windows"]],
            })
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print("JSON written to %s" % json_path)


if __name__ == "__main__":
    main()