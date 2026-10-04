"""Stub test for tab_organiser_ext/content.js.

Runs the real content.js against fake chrome.* APIs inside headless Chrome and
checks the postMessage bridge, URL cleaning and group/window creation.

Run from this directory:  python test_content_js.py
"""
import html as html_module
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "content.js")
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome():
    for candidate in CHROME_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None

STUBS = r"""
<script>
window.__calls = [];
window.__fail = null;
window.__nextTab = 100;
window.__nextWin = 500;
window.__nextGroup = -1;
window.__groups = {};
window.__tabs = [];

function makeTab(id, url, windowId, index) {
  return {id: id, url: url, windowId: windowId, index: index, active: false};
}

window.chrome = {
  runtime: {getManifest: function () { return {version: '1.4'}; }},
  windows: {
    create: function (opts) {
      if (window.__fail === 'windows.create') {
        window.__fail = null;
        return Promise.reject(new Error('no new windows allowed'));
      }
      var wid = window.__nextWin++;
      var urls = opts.url || [];
      window.__calls.push({api: 'windows.create', url: urls.slice()});
      var tabs = urls.map(function (u, i) {
        var tab = makeTab(window.__nextTab++, u, wid, i);
        window.__tabs.push(tab);
        return tab;
      });
      return Promise.resolve({id: wid, tabs: tabs});
    }
  },
  tabs: {
    create: function (opts) {
      var urls = opts.url || [];
      window.__calls.push({api: 'tabs.create', url: urls.slice()});
      var tab = makeTab(window.__nextTab++, urls[0], 0, 0);
      window.__tabs.push(tab);
      return Promise.resolve(tab);
    },
    query: function (info) {
      return Promise.resolve(window.__tabs.filter(function (tab) {
        return tab.windowId === info.windowId;
      }));
    },
    group: function (opts) {
      var gid = window.__nextGroup--;
      window.__groups[gid] = {id: gid, tabIds: (opts.tabIds || []).slice()};
      window.__calls.push({api: 'tabs.group', tabIds: (opts.tabIds || []).slice()});
      return Promise.resolve(gid);
    }
  },
  tabGroups: {
    update: function (gid, opts) {
      window.__groups[gid] = Object.assign({}, window.__groups[gid], opts);
      window.__calls.push({api: 'tabGroups.update', id: gid,
                           opts: JSON.parse(JSON.stringify(opts))});
      return Promise.resolve(window.__groups[gid]);
    }
  }
};
</script>
"""

DRIVER = r"""
<script>
window.__begin = ['QQJSON', 'STARTQQ'].join('');
window.__end = ['QQJSON', 'ENDQQ'].join('');
function call(action, payload) {
  return new Promise(function (resolve, reject) {
    var id = 'req-' + Math.random().toString(36).slice(2);
    function onMessage(event) {
      var data = event.data;
      if (event.source !== window || !data || data.src !== 'tab-organiser-ext'
          || data.id !== id) { return; }
      window.removeEventListener('message', onMessage);
      if (data.ok) { resolve(data.result); } else { reject(new Error(data.error)); }
    }
    window.addEventListener('message', onMessage);
    window.postMessage({src: 'tab-organiser-report', id: id, action: action,
                        payload: payload || {}}, '*');
  });
}

var CASES = [
  {name: 'ping', action: 'ping', payload: {},
   check: function (r) { return r && r.version === '1.4'; }},
  {name: 'open-group', action: 'open-group',
   payload: {group: 'alpha', color: '#1a73e8',
             urls: ['https://example.com/a1', 'https://example.com/a2']},
   check: function (r) { return r && r.tabs === 2 && typeof r.groupId === 'number'; }},
  {name: 'open-group named colour', action: 'open-group',
   payload: {group: 'beta', color: 'blue',
             urls: ['https://example.com/b1', 'https://example.com/b2']},
   check: function (r) { return r && r.tabs === 2 && r.color === '#1a73e8'; }},
  {name: 'open-group unknown colour', action: 'open-group',
   payload: {group: 'g', color: 'chartreuse', urls: ['https://example.com/g1']},
   check: function (r) { return r && r.tabs === 1; }},
  {name: 'open-group dedups urls', action: 'open-group',
   payload: {group: 'z', urls: ['https://example.com/z1', 'https://example.com/z1',
                                'https://example.com/z2']},
   check: function (r) { return r && r.tabs === 2; }},
  {name: 'open-group empty', action: 'open-group',
   payload: {group: 'x', urls: []}, wantError: true},
  {name: 'open-group bad url', action: 'open-group',
   payload: {group: 'y', urls: ['definitely not a url']}, wantError: true},
  {name: 'open-window', action: 'open-window',
   payload: {ungrouped: ['https://example.com/p1', 'https://example.com/p2'],
             groups: [{group: 'alpha', color: '#1a73e8',
                       urls: ['https://example.com/a1']},
                      {group: 'beta', color: 'e37400',
                       urls: ['https://example.com/b1', 'https://example.com/b2']}]},
   check: function (r) { return r && r.tabs === 5 && r.groups === 2; }},
  {name: 'open-window all grouped', action: 'open-window',
   payload: {ungrouped: [],
             groups: [{group: 'only',
                       urls: ['https://example.com/o1', 'https://example.com/o2']}]},
   check: function (r) { return r && r.tabs === 2 && r.groups === 1 && r.ungrouped === 0; }},
  {name: 'open-window empty', action: 'open-window',
   payload: {ungrouped: [], groups: []}, wantError: true},
  {name: 'open-window api error', action: 'open-window',
   payload: {ungrouped: ['https://example.com/e1'], groups: []},
   prep: function () { window.__fail = 'windows.create'; }, wantError: true},
  {name: 'unknown action', action: 'nope', payload: {}, wantError: true}
];

var steps = [];
var queue = CASES.slice();

function next() {
  if (!queue.length) { return finish(); }
  var testCase = queue.shift();
  if (testCase.prep) { testCase.prep(); }
  call(testCase.action, testCase.payload).then(function (result) {
    var ok = false;
    if (testCase.wantError) { ok = false; }
    else {
      try { ok = !!testCase.check(result); } catch (err) { ok = false; }
    }
    steps.push({name: testCase.name, ok: ok, result: result,
                calls: window.__calls.slice()});
  }, function (err) {
    steps.push({name: testCase.name, ok: !!testCase.wantError,
                error: err.message, calls: window.__calls.slice()});
  }).then(next);
}

function finish() {
  var out = document.createElement('pre');
  out.id = 'result';
  out.textContent = window.__begin + JSON.stringify(
    {steps: steps, calls: window.__calls, groups: window.__groups,
     ready: document.documentElement.getAttribute('data-tab-organiser-ext')})
    + window.__end;
  document.body.appendChild(out);
}

window.addEventListener('load', function () { window.setTimeout(next, 50); });
</script>
"""


def main():
    chrome = find_chrome()
    if not chrome:
        print("FAIL: chrome.exe not found in %s" % CHROME_CANDIDATES)
        return 1
    content = open(CONTENT, encoding="utf-8").read()
    tmp = tempfile.mkdtemp(prefix="contentjs")
    page = os.path.join(tmp, "test.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write("<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>\n")
        fh.write(STUBS)
        fh.write("<script>%s</script>\n" % content)
        fh.write(DRIVER)
        fh.write("</body></html>\n")

    result = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--disable-extensions",
         "--user-data-dir=" + os.path.join(tmp, "profile"),
         "--virtual-time-budget=15000", "--dump-dom", page],
        capture_output=True, text=True, timeout=240)
    dom = result.stdout
    match = re.search(r"QQJSONSTARTQQ(.*?)QQJSONENDQQ", dom, re.S)
    if not match:
        print("FAIL: driver produced no result")
        print(dom[-3000:])
        return 1
    raw = match.group(1)
    if not raw.strip():
        print("FAIL: result payload empty")
        index = dom.find("QQJSONSTARTQQ")
        print(repr(dom[max(0, index - 200):index + 400]))
        return 1
    data = json.loads(html_module.unescape(raw))

    fails = 0
    if data.get("ready") != "ready":
        print("FAIL: content script did not set data-tab-organiser-ext")
        fails += 1
    for step in data["steps"]:
        detail = step.get("error") or json.dumps(step.get("result"))
        print("%-4s %-26s %s" % ("PASS" if step["ok"] else "FAIL",
                                 step["name"], detail))
        if not step["ok"]:
            fails += 1

    calls = data["calls"]
    updates = [c for c in calls if c["api"] == "tabGroups.update"]
    groups = [c for c in calls if c["api"] == "tabs.group"]
    print("\napi calls: %d (windows.create=%d tabs.create=%d tabs.group=%d "
          "tabGroups.update=%d)" % (
              len(calls),
              sum(1 for c in calls if c["api"] == "windows.create"),
              sum(1 for c in calls if c["api"] == "tabs.create"),
              len(groups), len(updates)))

    titles = [u["opts"].get("title") for u in updates if "title" in u["opts"]]
    for expected in ("alpha", "beta", "only", "g", "z"):
        if expected not in titles:
            print("FAIL: group title %r never applied (%s)" % (expected, titles))
            fails += 1
    colors = [u["opts"].get("color") for u in updates if "color" in u["opts"]]
    bad = [c for c in colors if not re.fullmatch(r"#[0-9a-f]{6}", c or "")]
    if bad:
        print("FAIL: colours not normalised: %s" % bad)
        fails += 1
    if updates and any(u["opts"].get("newWindow") is not True for u in updates):
        print("FAIL: tabGroups.update must set newWindow:true")
        fails += 1
    if not groups:
        print("FAIL: no tabs.group calls recorded")
        fails += 1

    print("\nfailures: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
