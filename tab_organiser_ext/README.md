# Tab Organiser extension (companion for chrome_report v1.4)

Adds **"Open … in Chrome"** buttons to `chrome_report_v1.4.html` reports, so a
window or a single tab group from the report can be opened as a **real Chrome
window with real Chrome tab groups**.

It **copies** — it never moves, closes or reorders anything in the source
windows.

## Why an extension?

Chrome does not offer a scripting API for creating tab groups in an already
running browser. Public CDP commands stop short of group creation, and Chrome
is not running with a remote debugging port here. Only an extension with the
`tabs` + `tabGroups` + `windows` permissions can do it from a local report page.

## Install (once)

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select this `tab_organiser_ext` folder.
4. Open the extension's details page and turn on
   **Allow access to file URLs** — the report is a `file://` page.
5. Reopen the report. The badge in the top right turns green and reads
   *extension connected*. Until then the Chrome-side buttons stay disabled;
   the plain "Open window (grouped)" popups keep working.

Test it any time by opening `selftest.html` from this folder. It runs six real
API calls (ping, single group, colour mapping, dedup, empty input, invalid URL,
grouped window, API failure) and prints PASS/FAIL for each.

## Automated tests (no extension install needed)

```
python test_content_js.py    # runs content.js against stub chrome.* APIs
python test_report_js.py     # runs the report page's JS in headless Chrome
```

`test_content_js.py` needs only Python and Chrome; both scripts use a temporary
profile and delete nothing of yours.

## What the buttons do

| Button | Effect |
| --- | --- |
| `Open window (grouped)` | Opens the window's tabs in a second **browser window**, arranged as ungrouped tabs first, then one section per group in Chrome's own group order. No extension needed. |
| `Open window in Chrome` | Opens a **real Chrome window**; ungrouped tabs first, then one real Chrome tab group per report group, with the group title and colour. |
| group chip | Opens just that group in a second browser window. |
| `Open group in Chrome` | Opens that group as a new Chrome window containing a single real Chrome tab group (title + colour preserved). |

Opening more than 40 tabs at once asks for confirmation first.

## Permissions

- `tabs` — read/create tabs.
- `tabGroups` — create and title/colour groups.
- `windows` — create the target windows.
- host access to `file:///*`, `localhost`, `127.0.0.1` — the report page only.

No network access, no storage, no background script, no telemetry.

## Notes

- Tab order follows the report: with `--preserve_order ON` (default) that is
  Chrome's own tab strip order, so groups stay contiguous.
- URLs that are missing a scheme get `https://` prefixed; duplicates within one
  action are collapsed; `about:blank` is used when a window's tabs are all
  grouped.
- Group colours from the report are mapped onto Chrome's 8 group colours.
