(function () {
  'use strict';

  var REPORT_SRC = 'tab-organiser-report';
  var EXT_SRC = 'tab-organiser-ext';

  var COLORS = {
    grey: '#5f6368', blue: '#1a73e8', red: '#ea4335', yellow: '#fbbc04',
    green: '#34a853', pink: '#ff6699', purple: '#a142f4', cyan: '#24c1e0',
    orange: '#e37400'
  };

  function reply(id, ok, payload) {
    var message = {src: EXT_SRC, id: id};
    if (ok) {
      message.ok = true;
      message.result = payload || {};
    } else {
      message.ok = false;
      message.error = (payload && payload.message) || String(payload);
    }
    window.postMessage(message, '*');
  }

  function hexColor(value) {
    var text = String(value || '').trim().toLowerCase();
    if (!text) { return null; }
    if (Object.prototype.hasOwnProperty.call(COLORS, text)) { return COLORS[text]; }
    if (/^#?[0-9a-f]{6}$/.test(text)) {
      return text[0] === '#' ? text : '#' + text;
    }
    if (/^#?[0-9a-f]{3}$/.test(text)) {
      var short = text[0] === '#' ? text.slice(1) : text;
      return '#' + short[0] + short[0] + short[1] + short[1] + short[2] + short[2];
    }
    return null;
  }

  function cleanUrls(urls) {
    var out = [];
    (urls || []).forEach(function (url) {
      var text = String(url == null ? '' : url).trim();
      if (!text) { return; }
      if (!/^(https?|file|chrome|about|edge|view-source):/i.test(text)) {
        if (/^[\w-]+(\.[\w-]+)+([/?#].*)?$/.test(text)) { text = 'https://' + text; }
        else { throw new Error('invalid URL: ' + text); }
      }
      if (out.indexOf(text) === -1) { out.push(text); }
    });
    return out;
  }

  function tabGroupOptions(overrides) {
    var options = {newWindow: true};
    var source = overrides || {};
    var color = hexColor(source.color);
    if (color) { options.color = color; }
    var title = String(source.title == null ? '' : source.title).trim();
    if (title) { options.title = title; }
    return options;
  }

  function openGroup(payload) {
    var urls = cleanUrls(payload && payload.urls);
    if (!urls.length) { throw new Error('this group has no tabs to open'); }
    var groupId = -1;
    var title = String((payload && payload.group) || '').trim();

    return chrome.tabs.create({url: urls}).then(function (first) {
      groupId = first.id;
      return chrome.tabs.group({tabIds: [first.id]});
    }).then(function (id) {
      groupId = id;
      var update = {groupId: groupId, newWindow: true};
      var color = hexColor(payload && payload.color);
      if (color) { update.color = color; }
      if (title) { update.title = title; }
      return chrome.tabGroups.update(groupId, update);
    }).then(function () {
      return {action: 'open-group', tabs: urls.length, groupId: groupId,
              title: title, color: hexColor(payload && payload.color) || ''};
    });
  }

  function openWindow(payload) {
    var ungrouped = cleanUrls(payload && payload.ungrouped);
    var groups = (payload && payload.groups) || [];
    var prepared = [];
    groups.forEach(function (group) {
      var urls = cleanUrls(group && group.urls);
      if (urls.length) { prepared.push({group: group, urls: urls}); }
    });

    if (!ungrouped.length && !prepared.length) {
      throw new Error('this window has no tabs to open');
    }

    var win = null;
    var createdIds = [];
    var groupIds = [];

    var allUrls = ungrouped.slice();
    prepared.forEach(function (entry) {
      allUrls = allUrls.concat(entry.urls);
    });

    return chrome.windows.create({url: allUrls})
      .then(function (created) {
        win = created;
        return chrome.tabs.query({windowId: win.id});
      })
      .then(function (tabs) {
        var byUrl = {};
        tabs.forEach(function (tab) {
          var key = String(tab.url || '').trim();
          if (!key) { return; }
          if (!byUrl[key]) { byUrl[key] = []; }
          byUrl[key].push(tab.id);
        });
        prepared.forEach(function (entry) {
          var ids = [];
          entry.urls.forEach(function (url) {
            var bucket = byUrl[url];
            if (bucket && bucket.length) { ids.push(bucket.shift()); }
          });
          if (ids.length) { createdIds.push(ids); }
        });
        return createdIds.reduce(function (chain, ids, index) {
          return chain.then(function () {
            return chrome.tabs.group({tabIds: ids}).then(function (id) {
              groupIds.push(id);
              return chrome.tabGroups.update(id, tabGroupOptions({
                color: prepared[index].group.color,
                title: prepared[index].group.group
              }));
            });
          });
        }, Promise.resolve());
      })
      .then(function () {
        return {action: 'open-window', windowId: win ? win.id : null,
                tabs: ungrouped.length + prepared.reduce(
                    function (sum, entry) { return sum + entry.urls.length; }, 0),
                groups: groupIds.length,
                ungrouped: ungrouped.length};
      });
  }

  function handle(action, payload) {
    switch (action) {
      case 'ping':
        return Promise.resolve({action: 'ping', version: chrome.runtime.getManifest().version,
                                userAgent: navigator.userAgent});
      case 'open-group':
        return openGroup(payload);
      case 'open-window':
        return openWindow(payload);
      default:
        return Promise.reject(new Error('unknown action: ' + action));
    }
  }

  function markReady() {
    document.documentElement.setAttribute('data-tab-organiser-ext', 'ready');
  }

  window.addEventListener('message', function (event) {
    var data = event.data;
    if (event.source !== window || !data || data.src !== REPORT_SRC || !data.id) {
      return;
    }
    var action = data.action;
    Promise.resolve()
      .then(function () { return handle(action, data.payload); })
      .then(function (result) { reply(data.id, true, result); })
      .catch(function (err) {
        reply(data.id, false, {message: err && err.message ? err.message : String(err)});
      });
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markReady);
  } else {
    markReady();
  }
})();
