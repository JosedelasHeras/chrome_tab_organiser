"""Headless check of the v1.41 editor: the grip is the drag source, stray drags
are cancelled, drag reordering works inside a window and across windows,
data-pos renumbering, sort auto-uncheck on real drags only, and a clean save.

Run from this directory:  python test_editor_js.py
"""
import html as html_module
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR = os.path.join(HERE, "chrome_report_edit_v1.41.py")
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

# A v1.4-style report: rows carry data-pos, windows are data-window sections.
FIXTURE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Fixture</title>
<style>
body{font-family:Arial,sans-serif;margin:12px}
section.window{margin-bottom:18px}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ddd;padding:3px 5px;text-align:left;vertical-align:top}
tr{height:22px}
.chip{display:inline-block;padding:1px 5px;color:#fff}
.chip.none{background:#e8eaed}
</style></head>
<body>
<p class="stats">fixture</p>
<section class="window" data-window="0">
  <div class="window-head"><h3 class="wname">Window 1</h3>
    <span class="win-meta"></span></div>
  <div class="window-actions"></div>
  <table><thead><tr><th>Group</th><th>Tab</th><th>URL</th></tr></thead>
  <tbody>
    <tr data-pos="1"><td class="group"><span class="chip" style="background:#1a73e8">ChIP</span></td><td class="tab"><a href="https://a.example/">Alpha</a></td><td class="url"><a class="url-text" href="https://a.example/">https://a.example/</a></td></tr>
    <tr data-pos="2"><td class="group"><span class="chip" style="background:#1a73e8">ChIP</span></td><td class="tab"><a href="https://b.example/">Bravo</a></td><td class="url"><a class="url-text" href="https://b.example/">https://b.example/</a></td></tr>
    <tr data-pos="3"><td class="group"><span class="chip" style="background:#0b8043">RNA</span></td><td class="tab"><a href="https://c.example/">Charlie</a></td><td class="url"><a class="url-text" href="https://c.example/">https://c.example/</a></td></tr>
    <tr data-pos="4"><td class="group"><span class="chip none"></span></td><td class="tab"><a href="https://d.example/">Delta</a></td><td class="url"><a class="url-text" href="https://d.example/">https://d.example/</a></td></tr>
  </tbody></table>
</section>
<section class="window" data-window="1">
  <div class="window-head"><h3 class="wname">Window 2</h3>
    <span class="win-meta"></span></div>
  <div class="window-actions"></div>
  <table><thead><tr><th>Group</th><th>Tab</th><th>URL</th></tr></thead>
  <tbody>
    <tr data-pos="1"><td class="group"><span class="chip" style="background:#e8710a">ChIP</span></td><td class="tab"><a href="https://e.example/">Echo</a></td><td class="url"><a class="url-text" href="https://e.example/">https://e.example/</a></td></tr>
    <tr data-pos="2"><td class="group"><span class="chip" style="background:#e8710a">ChIP</span></td><td class="tab"><a href="https://f.example/">Foxtrot</a></td><td class="url"><a class="url-text" href="https://f.example/">https://f.example/</a></td></tr>
  </tbody></table>
</section>
</body></html>
"""

# A legacy v1.3-era report: no data-pos anywhere.
LEGACY = re.sub(r' data-pos="\d+"', "", FIXTURE)

STUB = r"""
<script>
window.__log = [];
function say(t) { window.__log.push(t); }
window.addEventListener('error', function (e) {
  say('JS ERROR: ' + e.message + ' @' + e.lineno + ':' + e.colno);
});
var __files = window.__files || {};
window.fetch = function (url, opts) {
  var u = String(url);
  if (u.indexOf('/api/files') === 0) {
    return Promise.resolve({ json: function () {
      return Promise.resolve({ ok: true, files: ['fixture.html', 'legacy.html'] });
    }});
  }
  if (u.indexOf('/api/load') === 0) {
    var m = /name=([^&]*)/.exec(u);
    var key = decodeURIComponent(m ? m[1] : '');
    var body = __files[key] || '';
    return Promise.resolve({ json: function () {
      return Promise.resolve({ ok: true, name: key, html: body });
    }});
  }
  return Promise.resolve({ json: function () {
    return Promise.resolve({ ok: true, name: 'x.html', path: 'x', bytes: 1 });
  }});
};
</script>
"""

TAIL = r"""
<script>doLoad('fixture.html');</script>
"""

PROBE = r"""
<script>
window.__probeStart = ['QQPROBE', 'STARTQQ'].join('');
window.__probeEnd = ['QQPROBE', 'ENDQQ'].join('');

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
function wins() { return FDOC.querySelectorAll('section.window'); }
function rowsOf(w) { return Array.prototype.slice.call(w.querySelectorAll('tbody tr')); }
function titlesOf(w) {
  return rowsOf(w).map(function (tr) {
    var a = tr.querySelector('td.tab a');
    return a ? a.textContent.trim() : '(none)';
  }).join(',');
}
function posOf(w) {
  return rowsOf(w).map(function (tr) {
    var p = tr.getAttribute('data-pos');
    return p === null ? 'null' : p;
  }).join(',');
}
function seqOk(w) {
  var p = rowsOf(w).map(function (tr) { return tr.getAttribute('data-pos'); });
  return p.join(',') === p.map(function (_v, i) { return String(i + 1); }).join(',');
}
function newDT() { try { return new DataTransfer(); } catch (e) { return null; } }
function fire(el, type, y, dt) {
  el.dispatchEvent(new DragEvent(type, {
    bubbles: true, cancelable: true, composed: true,
    clientX: 20, clientY: y === undefined ? 0 : y,
    dataTransfer: dt
  }));
}
function gripOf(tr) { return tr.querySelector('.ce-grip'); }
function cellOf(tr) { return tr.querySelector('td.tab'); }
function clickGrip(tr) {
  var g = gripOf(tr);
  g.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
  g.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
}

/* the grip is the drag source: dragstart fires on it, not on the row.
   Small waits let the deferred dragstart state apply and settle, matching
   real event timing (the v1.41 fix defers DOM changes out of dragstart). */
async function dragRowTo(srcTr, dstTr, after) {
  var dt = newDT();
  fire(gripOf(srcTr), 'dragstart', 0, dt);
  await sleep(10);
  var r = dstTr.getBoundingClientRect();
  var y = after ? (r.bottom - 1) : (r.top + 1);
  fire(cellOf(dstTr), 'dragover', y, dt);
  fire(dstTr.closest('tbody'), 'drop', y, dt);
  fire(gripOf(srcTr), 'dragend', y, dt);
  await sleep(10);
}

async function waitDoc(pred, label) {
  for (var i = 0; i < 300; i++) {
    if (FDOC && wins().length && rowsOf(wins()[0]).length && pred()) return true;
    await sleep(50);
  }
  say('TIMEOUT waiting for ' + label);
  return false;
}

window.__run = async function () {
  try {
    var w1 = wins()[0], w2 = wins()[1];
    say('windows=' + wins().length);
    say('rows w1=' + rowsOf(w1).length + ' w2=' + rowsOf(w2).length);
    say('order w1=' + titlesOf(w1));
    say('order w2=' + titlesOf(w2));

    var total = rowsOf(w1).length + rowsOf(w2).length;
    say('grips=' + FDOC.querySelectorAll('.ce-grip').length + ' expected=' + total);
    say('grip is ce-inject=' +
        (gripOf(rowsOf(w1)[0]).classList.contains('ce-inject')));
    say('grip css present=' +
        (FDOC.getElementById('ce-css').textContent.indexOf('ce-grip') >= 0));
    /* v1.41: the grip is the drag source, so it must be draggable up front */
    say('grip draggable=true=' +
        Array.prototype.every.call(FDOC.querySelectorAll('.ce-grip'),
          function (g) { return g.draggable === true; }));
    say('rows draggable=false=' +
        Array.prototype.every.call(FDOC.querySelectorAll('tbody tr'),
          function (r) { return r.draggable === false; }));

    /* a drag that does not originate from a grip must be cancelled */
    var strayDT = newDT();
    fire(cellOf(rowsOf(w1)[0]), 'dragstart', 0, strayDT);
    say('stray drag cancelled=' +
        (FDOC.querySelectorAll('tr.ce-dragging').length === 0));
    say('stray drag no state=' + (typeof dragRow === 'undefined' || !dragRow));
    say('order unchanged after stray=' + titlesOf(w1));

    /* drag the first row of w1 down to the end of w1 */
    await dragRowTo(rowsOf(w1)[0], rowsOf(w1)[3], true);
    say('after move w1=' + titlesOf(w1));
    say('after move data-pos=' + posOf(w1));
    say('after move seq ok=' + seqOk(w1));
    say('dragging cleared=' +
        (FDOC.querySelectorAll('tr.ce-dragging').length === 0));
    say('dropzone cleared=' +
        (FDOC.querySelectorAll('tbody.ce-dropzone').length === 0));

    /* drag a w1 row into w2 */
    await dragRowTo(rowsOf(w1)[0], rowsOf(w2)[1], true);
    say('cross w1=' + titlesOf(w1) + ' | w2=' + titlesOf(w2));
    say('cross seq w1=' + seqOk(w1) + ' w2=' + seqOk(w2));
    say('cross counts w1=' + rowsOf(w1).length + ' w2=' + rowsOf(w2).length);

    /* delete renumbers */
    rowsOf(w1)[0].querySelector('.ce-del').click();
    say('after delete w1=' + titlesOf(w1) + ' data-pos=' + posOf(w1));

    /* insert renumbers */
    openInsert(null, 0);
    fGroup.value = 'ChIP';
    fTitle.value = 'Inserted';
    fUrl.value = 'https://new.example/';
    doInsert();
    say('after insert w1=' + titlesOf(w1) + ' data-pos=' + posOf(w1));

    /* group sort: a mere grip click must NOT discard the sorted view */
    sortChk.checked = true;
    sortChk.dispatchEvent(new Event('change'));
    say('sorted w1=' + titlesOf(w1));
    clickGrip(rowsOf(w1)[0]);
    say('sort stays checked after click=' + (sortChk.checked === true));
    /* an actual drag does replace it */
    await dragRowTo(rowsOf(w1)[0], rowsOf(w1)[rowsOf(w1).length - 1], true);
    say('sort unchecked after drag=' + (sortChk.checked === false));

    /* Chrome never dispatches drop when the mouse is released over a chip,
       a link, or another grip. dragend alone must still commit and renumber
       (v1.41 fix). */
    var noDropTr = rowsOf(w1)[0];
    var noDropDT = newDT();
    fire(gripOf(noDropTr), 'dragstart', 0, noDropDT);
    await sleep(10);
    var lastTr = rowsOf(w1)[rowsOf(w1).length - 1];
    var rEnd = lastTr.getBoundingClientRect();
    fire(cellOf(lastTr), 'dragover', rEnd.bottom - 1, noDropDT);
    fire(gripOf(noDropTr), 'dragend', rEnd.bottom - 1, noDropDT);
    await sleep(10);
    say('dragend-only commit=' + titlesOf(w1));
    say('dragend-only pos=' + posOf(w1));
    say('dragend-only seq ok=' + seqOk(w1));
    say('dragend-only state clean=' +
        (FDOC.querySelectorAll('tr.ce-dragging').length === 0 &&
         FDOC.querySelectorAll('tbody.ce-dropzone').length === 0 &&
         !FDOC.documentElement.classList.contains('ce-drag-live')));

    /* save leaves no editor chrome behind */
    var out = serializeReport();
    say('save has ce-grip=' + (out.indexOf('ce-grip') >= 0));
    say('save has ce-css=' + (out.indexOf('ce-css') >= 0));
    say('save has contenteditable=' + (out.indexOf('contenteditable') >= 0));
    say('save has grip glyph=' + (out.indexOf('\u283f') >= 0));
    say('save keeps data-pos=' + (out.indexOf('data-pos="1"') >= 0));
    say('editor usable after save=' +
        (FDOC.querySelectorAll('.ce-grip').length ===
         rowsOf(wins()[0]).length + rowsOf(wins()[1]).length));

    /* a legacy report without data-pos stays without */
    doLoad('legacy.html');
    await waitDoc(function () {
      return FDOC.querySelectorAll('[data-pos]').length === 0 &&
             rowsOf(wins()[0]).length === 4;
    }, 'legacy report');
    var lw1 = wins()[0], lw2 = wins()[1];
    say('legacy data-pos count=' + FDOC.querySelectorAll('[data-pos]').length);
    await dragRowTo(rowsOf(lw1)[0], rowsOf(lw1)[3], true);
    say('legacy after drag=' + titlesOf(lw1));
    say('legacy after drag data-pos=' + FDOC.querySelectorAll('[data-pos]').length);
    rowsOf(lw1)[0].querySelector('.ce-del').click();
    say('legacy after delete data-pos=' +
        FDOC.querySelectorAll('[data-pos]').length);
    openInsert(null, 0);
    fGroup.value = '';
    fTitle.value = 'LegacyAdded';
    fUrl.value = 'https://legacy.example/';
    doInsert();
    say('legacy after insert data-pos=' +
        FDOC.querySelectorAll('[data-pos]').length);
    say('legacy rows after insert=' + rowsOf(lw1).length);

    say('DONE');
  } catch (err) {
    say('THROWN: ' + err.message);
  }
};
</script>
"""

RESULT = r"""
<script>
window.addEventListener('load', function () {
  window.setTimeout(function () {
    Promise.resolve(window.__run()).then(function () {
      var out = document.createElement('pre');
      out.id = 'probe';
      out.textContent = window.__probeStart +
        JSON.stringify(window.__log) + window.__probeEnd;
      document.body.appendChild(out);
    });
  }, 500);
});
</script>
"""

def find_chrome():
    for candidate in CHROME_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def build_checks():
    return [
        ("both fixture windows loaded", lambda t: "windows=2" in t),
        ("grip on every row",
         lambda t: re.search(r"grips=(\d+) expected=\1\b", t) is not None),
        ("grip carries ce-inject", lambda t: "grip is ce-inject=true" in t),
        ("grip styles injected", lambda t: "grip css present=true" in t),
        ("grip is draggable from the start (v1.41 fix)",
         lambda t: "grip draggable=true=true" in t),
        ("rows are never draggable (editing stays untouched)",
         lambda t: "rows draggable=false=true" in t),
        ("stray drag from a tab cell is cancelled",
         lambda t: "stray drag cancelled=true" in t
         and "stray drag no state=true" in t),
        ("stray drag leaves the order alone",
         lambda t: "order unchanged after stray=Alpha,Bravo,Charlie,Delta" in t),
        ("drag down reorders the window",
         lambda t: "after move w1=Bravo,Charlie,Delta,Alpha" in t),
        ("drag renumbers data-pos",
         lambda t: "after move data-pos=1,2,3,4" in t and "after move seq ok=true" in t),
        ("drag clears its own state",
         lambda t: "dragging cleared=true" in t and "dropzone cleared=true" in t),
        ("drag across windows moves the tab",
         lambda t: "cross w1=Charlie,Delta,Alpha | w2=Echo,Foxtrot,Bravo" in t),
        ("cross-window row counts correct",
         lambda t: "cross counts w1=3 w2=3" in t),
        ("both windows renumbered after a cross-window drop",
         lambda t: "cross seq w1=true w2=true" in t),
        ("delete renumbers data-pos",
         lambda t: "after delete w1=Delta,Alpha data-pos=1,2" in t),
        ("insert renumbers data-pos",
         lambda t: "after insert w1=Inserted,Delta,Alpha data-pos=1,2,3" in t),
        ("group sort reorders the window",
         lambda t: "sorted w1=Delta,Inserted,Alpha" in t),
        ("a mere grip click keeps the sort checked (v1.41 fix)",
         lambda t: "sort stays checked after click=true" in t),
        ("an actual drag unchecks the sort",
         lambda t: "sort unchecked after drag=true" in t),
        ("dragend alone commits without a drop event (v1.41 fix)",
         lambda t: "dragend-only commit=Alpha,Delta,Inserted" in t),
        ("dragend alone renumbers data-pos",
         lambda t: "dragend-only pos=1,2,3" in t
         and "dragend-only seq ok=true" in t),
        ("dragend leaves no live state behind",
         lambda t: "dragend-only state clean=true" in t),
        ("save strips the grip", lambda t: "save has ce-grip=false" in t),
        ("save strips injected css", lambda t: "save has ce-css=false" in t),
        ("save strips contenteditable",
         lambda t: "save has contenteditable=false" in t),
        ("save strips the grip glyph",
         lambda t: "save has grip glyph=false" in t),
        ("save keeps data-pos", lambda t: "save keeps data-pos=true" in t),
        ("editor usable after save",
         lambda t: "editor usable after save=true" in t),
        ("legacy report has no data-pos",
         lambda t: "legacy data-pos count=0" in t),
        ("legacy drag adds no data-pos",
         lambda t: "legacy after drag data-pos=0" in t),
        ("legacy delete adds no data-pos",
         lambda t: "legacy after delete data-pos=0" in t),
        ("legacy insert adds no data-pos",
         lambda t: "legacy after insert data-pos=0" in t),
        ("legacy insert still works", lambda t: "legacy rows after insert=4" in t),
    ]


def main():
    chrome = find_chrome()
    if not chrome:
        print("FAIL: chrome.exe not found")
        return 1
    if not os.path.isfile(EDITOR):
        print("FAIL: %s missing" % EDITOR)
        return 1
    spec = importlib.util.spec_from_file_location("e14", EDITOR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    page_src = m.PAGE_HTML
    for token in ("ce-grip", "onDragStart", "renumberAll"):
        if token not in page_src:
            print("FAIL: editor page is missing %s" % token)
            return 1

    # "/"-safe escaping keeps a literal </body> inside the fixtures from
    # confusing the tag insertion below.
    files = json.dumps({"fixture.html": FIXTURE, "legacy.html": LEGACY})
    files = files.replace("</", "<\\/")
    stub = STUB.replace("var __files = window.__files || {};",
                        "var __files = %s;" % files)
    page = page_src.replace("<body>", "<body>\n" + stub, 1)
    head, sep, tail = page.rpartition("</body>")
    if not sep:
        print("FAIL: editor page has no </body>")
        return 1
    page = head + PROBE + TAIL + RESULT + sep + tail

    tmp = tempfile.mkdtemp(prefix="editorjs")
    path = os.path.join(tmp, "editor.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)

    run = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
         "--disable-extensions", "--allow-file-access-from-files",
         "--user-data-dir=" + os.path.join(tmp, "profile"),
         "--virtual-time-budget=25000", "--dump-dom", path],
        capture_output=True, timeout=300)
    dom = run.stdout.decode("utf-8", "replace")
    match = re.search(r"QQPROBESTARTQQ(.*?)QQPROBEENDQQ", dom, re.S)
    if not match:
        print("FAIL: probe produced no output")
        print(dom[-3000:])
        return 1
    log = json.loads(html_module.unescape(match.group(1)))

    text = "\n".join(log)
    for line in log:
        print("   " + line)

    fails = 0
    if "JS ERROR" in text or "THROWN" in text:
        print("FAIL: script error in editor page")
        fails += 1
    if "TIMEOUT" in text:
        print("FAIL: probe timed out")
        fails += 1
    if "DONE" not in log:
        print("FAIL: probe did not finish")
        fails += 1

    checks = build_checks()
    for label, test in checks:
        ok = test(text)
        print("%-4s %s" % ("PASS" if ok else "FAIL", label))
        if not ok:
            fails += 1
    print("\nchecks: %d  failures: %d" % (len(checks), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
