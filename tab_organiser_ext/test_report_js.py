"""Headless check of the v1.4 report page: scripts parse, popups build, and the
grouped view keeps ungrouped tabs first then groups in Chrome's order.

Run from this directory:  python test_report_js.py
"""
import html as html_module
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPORT = os.path.join(ROOT, "chrome_report_v1.4.py")
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

PROBE = r"""
<script>
window.__log = [];
function say(text) { window.__log.push(text); }

window.addEventListener('error', function (event) {
  say('JS ERROR: ' + event.message + ' @' + event.lineno + ':' + event.colno);
});

function chips(section) {
  return Array.prototype.slice.call(section.querySelectorAll('.chip-act'));
}
function rows(section) {
  return Array.prototype.slice.call(section.querySelectorAll('tbody tr'));
}
function groupOf(tr) {
  var chip = tr.querySelector('td.group .chip');
  return (chip && !chip.classList.contains('none'))
    ? chip.getAttribute('data-group') : '';
}
function openWindows() {
  return window.__opened = window.__opened || [];
}
window.__nativeOpen = window.open;

window.open = function (url, target) {
  var doc = {title: '', body: '', closed: false,
             document: {open: function () {}, close: function () {}}};
  doc.document.write = function (html) { doc.body = html; };
  openWindows().push(doc);
  return doc;
};

window.__run = function () {
  var installUrl = window.__installUrl || '(not injected)';
  say('TAB_ORGANISER=' + (window.TAB_ORGANISER ? 'present' : 'MISSING'));
  say('installUrl=' + installUrl);
  say('open-window buttons=' +
      document.querySelectorAll('[data-action="open-window"]').length);
  say('window.open stubbed=' +
      (window.open !== window.__nativeOpen));
  var sections = Array.prototype.slice.call(
    document.querySelectorAll('section.window'));
  var section = sections.filter(function (s) { return chips(s).length; })[0]
    || sections[0];
  if (!section) { say('no window section found'); return; }
  var name = section.querySelector('.wname').textContent;
  var allRows = rows(section);
  var firstChip = chips(section)[0];

  say('section=' + name + ' rows=' + allRows.length + ' chips=' + chips(section).length);
  say('groupOf(firstRow)=' + JSON.stringify(groupOf(allRows[0])));
  say('data-pos sequence ok=' + (Array.prototype.map.call(allRows, function (tr) {
    return Number(tr.getAttribute('data-pos'));
  }).join(',') === Array.prototype.map.call(allRows, function (_tr, i) {
    return i + 1;
  }).join(',')));

  var winButton = section.querySelector('[data-action="open-window"]');
  say('winButton found=' + !!winButton);
  if (winButton) { winButton.click(); }
  say('open-window clicked, popups=' + openWindows().length);
  if (openWindows().length) {
    var html = openWindows()[0].body;
    say('popup has group sections=' + (html.match(/<section class="window">/g) || []).length);
    say('popup has core script=' + (html.indexOf('tab-organiser-report') >= 0));
    say('popup has unescaped token=' + (html.indexOf('CORE_JS') >= 0));
    say('popup has install url=' + (html.indexOf(installUrl) >= 0));
    var order = [];
    allRows.forEach(function (tr) { order.push(groupOf(tr)); });
    var expected = [];
    order.forEach(function (g) {
      if (g === '') {
        if (expected[expected.length - 1] !== 'ungrouped') { expected.push('ungrouped'); }
      } else if (expected[expected.length - 1] !== g) { expected.push(g); }
    });
    expected = ['ungrouped'].concat(expected.filter(function (g) {
      return g !== 'ungrouped';
    }));
    var titles = [];
    var body = html.substring(html.indexOf('<body>'));
    var re = /<section class="window"><div class="window-head"><h3>(.*?)<\/h3>/g;
    var found;
    while ((found = re.exec(body)) !== null) { titles.push(found[1]); }
    var expectedTitles = expected.map(function (g) {
      var count = order.filter(function (x) {
        return g === 'ungrouped' ? x === '' : x === g;
      }).length;
      return g === 'ungrouped'
        ? name + ' - ungrouped (' + count + ')'
        : g + ' (' + count + ')';
    });
    say('popup titles=' + JSON.stringify(titles));
    say('expected titles=' + JSON.stringify(expectedTitles));
    say('popup order matches=' + (titles.join('|') === expectedTitles.join('|')));
  }

  say('badge html=' + JSON.stringify(
      document.getElementById('ext-status').innerHTML));
  say('badge link href=' + (function () {
    var link = document.querySelector('#ext-status a');
    return link ? link.getAttribute('href') : 'NONE';
  }()));
  say('badge link target=' + (function () {
    var link = document.querySelector('#ext-status a');
    return link ? link.getAttribute('target') : 'NONE';
  }()));
  say('badge link text=' + (function () {
    var link = document.querySelector('#ext-status a');
    return link ? link.textContent : 'NONE';
  }()));
  say('badge text=' + document.getElementById('ext-status').textContent);
  say('badge rel=' + (function () {
    var link = document.querySelector('#ext-status a');
    return link ? link.getAttribute('rel') : 'NONE';
  }()));

  firstChip.click();
  say('open-group clicked, popups=' + openWindows().length);
  if (openWindows().length > 1) {
    var groupHtml = openWindows()[1].body;
    var wanted = firstChip.getAttribute('data-group');
    var matching = rows(section).filter(function (tr) { return groupOf(tr) === wanted; });
    var links = (groupHtml.match(/class="url-text"/g) || []).length;
    say('group popup "' + wanted + '" rows=' + links + ' expected=' + matching.length);
  }
  say('DONE');
};
</script>
"""

RESULT = r"""
<script>
window.addEventListener('load', function () {
  window.setTimeout(function () {
    try {
      window.__run();
    } catch (err) {
      window.__log.push('THROWN: ' + err.message);
    }
    var out = document.createElement('pre');
    out.id = 'probe';
    out.textContent = window.__probeStart + JSON.stringify(window.__log) + window.__probeEnd;
    document.body.appendChild(out);
  }, 6000);
});
</script>
"""


def find_chrome():
    for candidate in CHROME_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def main():
    chrome = find_chrome()
    if not chrome:
        print("FAIL: chrome.exe not found")
        return 1
    spec = importlib.util.spec_from_file_location("r14", REPORT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    profile = m.collect_profile(m.default_data_dir() + r"\Default", "Default")
    profile["windows"], _dropped = m.filter_windows(profile["windows"])
    profile["windows"] = m.assign_default_names(profile["windows"])
    if not profile["windows"]:
        print("FAIL: no windows after filtering")
        return 1

    tmp = tempfile.mkdtemp(prefix="reportjs")
    doc = m.render_html(profile, "2026-10-04 12:00:00", True)
    ext_dir = os.path.join(ROOT, "tab_organiser_ext")
    install_page = os.path.join(ext_dir, "install.html")
    if not os.path.isfile(install_page):
        print("FAIL: install.html missing at %s" % install_page)
        return 1
    install_url = "file:///" + quote(install_page.replace("\\", "/"), safe="/:")
    print("expected install url: %s" % install_url)
    if install_url not in doc:
        print("FAIL: report does not contain the install url")
        return 1

    page = os.path.join(tmp, "report.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(doc)
        fh.write('<script>window.__installUrl = %s;</script>\n'
                 % json.dumps(install_url))
        fh.write(PROBE.replace("window.__run = function", "window.__probeStart ="
                              " ['QQPROBE', 'STARTQQ'].join(''); window.__probeEnd ="
                              " ['QQPROBE', 'ENDQQ'].join('');\nwindow.__run = function", 1))
        fh.write(RESULT)

    run = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
         "--disable-extensions", "--allow-file-access-from-files",
         "--user-data-dir=" + os.path.join(tmp, "profile"),
         "--virtual-time-budget=20000", "--dump-dom", page],
        capture_output=True, timeout=240)
    dom = run.stdout.decode("utf-8", "replace")
    match = re.search(r"QQPROBESTARTQQ(.*?)QQPROBEENDQQ", dom, re.S)
    if not match:
        print("FAIL: probe produced no output")
        print(dom[-2500:])
        return 1
    log = json.loads(html_module.unescape(match.group(1)))

    fails = 0
    text = "\n".join(log)
    for line in log:
        print("   " + line)
    if "JS ERROR" in text or "THROWN" in text:
        print("FAIL: script error in report page")
        fails += 1
    if "DONE" not in log:
        print("FAIL: probe did not finish")
        fails += 1
    checks = {
        "rows and chips counted": "rows=" in text and "chips=" in text,
        "chrome order preserved (data-pos 1..n)": "data-pos sequence ok=true" in text,
        "open-window popup built": "open-window clicked, popups=1" in text,
        "popup contains group sections": "popup has group sections=" in text
        and "sections=0" not in text,
        "popup embeds the core bridge": "popup has core script=true" in text,
        "popup has no unexpanded tokens": "popup has unescaped token=false" in text,
        "popup section order = ungrouped then groups in strip order":
            "popup order matches=true" in text,
        "open-group popup built": "open-group clicked, popups=2" in text,
        "group popup row count matches": re.search(
            r"group popup .* rows=(\d+) expected=\1", text) is not None,
        "badge names the extension":
            "badge link text=" + m.extension_display_name(ext_dir) in text,
        "badge link points at install.html":
            "badge link href=" + install_url in text,
        "badge link opens in a new tab": 'badge link target=_blank' in text,
        "badge keeps the surrounding wording":
            text.count("extension not installed - ") >= 1
            and "Chrome-side actions disabled" in text,
        "popup carries the install url": "popup has install url=true" in text,
        "badge link carries rel=noopener": "badge rel=noopener" in text,
    }
    for label, ok in checks.items():
        print("%-4s %s" % ("PASS" if ok else "FAIL", label))
        if not ok:
            fails += 1
    print("\nfailures: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
