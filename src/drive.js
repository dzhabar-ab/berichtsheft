/* Berichtsheft – Speicher in Google Drive (nur Dateien, die diese App selbst anlegt: Scope drive.file).
 * Ordner "Berichtsheft" mit zwei Dateien:
 *   berichtsheft-daten.json   – Wochen und Einstellungen (ohne Bilder)
 *   berichtsheft-bilder.json  – Logo und Unterschriften (data-URLs)
 */
(function () {
  'use strict';
  var cfg = window.BERICHTSHEFT_CONFIG;
  var API = 'https://www.googleapis.com/drive/v3/files';
  var UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files';
  var FOLDER = 'Berichtsheft', DATA = 'berichtsheft-daten.json', IMAGES = 'berichtsheft-bilder.json';
  var CACHE = 'berichtsheft-drive-cache';

  var token = null, tokenClient = null, pendingAuth = null;
  var ids = { folder: null, data: null, images: null };
  var versions = { data: null };
  var lastImagesJson = null;

  function gsiReady() {
    return new Promise(function (res, rej) {
      var n = 0;
      (function wait() {
        if (window.google && google.accounts && google.accounts.oauth2) return res();
        if (++n > 100) return rej(new Error('Google-Anmeldung konnte nicht geladen werden.'));
        setTimeout(wait, 100);
      })();
    });
  }

  function requestToken(prompt) {
    return gsiReady().then(function () {
      return new Promise(function (res, rej) {
        if (!tokenClient) {
          tokenClient = google.accounts.oauth2.initTokenClient({
            client_id: cfg.clientId, scope: cfg.scope,
            callback: function (r) {
              var p = pendingAuth; pendingAuth = null;
              if (!p) return;
              if (r.error) return p.rej(new Error(r.error_description || r.error));
              token = r.access_token; p.res(token);
            },
            error_callback: function (e) {
              var p = pendingAuth; pendingAuth = null;
              if (p) p.rej(new Error(e && e.type === 'popup_closed' ? 'Anmeldung abgebrochen.' : 'Anmeldung nicht möglich.'));
            }
          });
        }
        pendingAuth = { res: res, rej: rej };
        tokenClient.requestAccessToken({ prompt: prompt || '' });
      });
    });
  }

  function AuthError(msg) { var e = new Error(msg || 'Anmeldung abgelaufen.'); e.code = 'auth'; return e; }

  function api(url, opts) {
    if (!token) return Promise.reject(AuthError());
    opts = opts || {};
    opts.headers = Object.assign({ Authorization: 'Bearer ' + token }, opts.headers || {});
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) { token = null; throw AuthError(); }
      if (!r.ok) return r.text().then(function (t) { throw new Error('Google Drive: HTTP ' + r.status + ' ' + t.slice(0, 200)); });
      return r;
    });
  }
  function findFile(name, mime, parent) {
    var q = "name='" + name + "' and trashed=false" + (mime ? " and mimeType='" + mime + "'" : '') + (parent ? " and '" + parent + "' in parents" : '');
    return api(API + '?q=' + encodeURIComponent(q) + '&fields=files(id,version)&orderBy=createdTime&spaces=drive')
      .then(function (r) { return r.json(); }).then(function (j) { return j.files && j.files[0] || null; });
  }
  function createFile(name, mime, parent, content) {
    var meta = { name: name, mimeType: mime };
    if (parent) meta.parents = [parent];
    if (content == null) {
      return api(API + '?fields=id,version', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meta) })
        .then(function (r) { return r.json(); });
    }
    var b = 'bh' + Math.random().toString(36).slice(2);
    var body = '--' + b + '\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n' + JSON.stringify(meta) +
      '\r\n--' + b + '\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n' + content + '\r\n--' + b + '--';
    return api(UPLOAD + '?uploadType=multipart&fields=id,version', { method: 'POST', headers: { 'Content-Type': 'multipart/related; boundary=' + b }, body: body })
      .then(function (r) { return r.json(); });
  }
  function readFile(id) { return api(API + '/' + id + '?alt=media').then(function (r) { return r.text(); }); }
  function writeFile(id, content) {
    return api(UPLOAD + '/' + id + '?uploadType=media&fields=id,version', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json; charset=UTF-8' }, body: content
    }).then(function (r) { return r.json(); });
  }
  function getVersion(id) {
    return api(API + '/' + id + '?fields=version').then(function (r) { return r.json(); }).then(function (j) { return j.version; });
  }

  function split(data) {
    var s = data.settings || {};
    var images = { logo: s.logo || null, mySig: s.mySig || null, ausbilderSigs: s.ausbilderSigs || [] };
    var meta = JSON.parse(JSON.stringify(data));
    meta.settings.logo = null; meta.settings.mySig = null;
    meta.settings.ausbilderSigs = (s.ausbilderSigs || []).map(function (x) { return { id: x.id, name: x.name }; });
    return { meta: meta, images: images };
  }
  function join(meta, images) {
    var s = meta.settings || {};
    images = images || {};
    s.logo = images.logo || null; s.mySig = images.mySig || null;
    var byId = {};
    (images.ausbilderSigs || []).forEach(function (x) { byId[x.id] = x; });
    s.ausbilderSigs = (s.ausbilderSigs || []).map(function (x) { return Object.assign({}, byId[x.id] || {}, { id: x.id, name: x.name }); })
      .filter(function (x) { return x.dataUrl; });
    meta.settings = s;
    return meta;
  }
  function cache(d) { try { localStorage.setItem(CACHE, JSON.stringify(d)); } catch (e) {} }

  function locate() {
    return findFile(FOLDER, 'application/vnd.google-apps.folder', null).then(function (f) {
      return f || createFile(FOLDER, 'application/vnd.google-apps.folder', null, null);
    }).then(function (f) {
      ids.folder = f.id;
      return Promise.all([findFile(DATA, null, ids.folder), findFile(IMAGES, null, ids.folder)]);
    }).then(function (r) {
      ids.data = r[0] && r[0].id; versions.data = r[0] && r[0].version;
      ids.images = r[1] && r[1].id;
    });
  }

  var DriveStore = {
    label: 'Deine Daten liegen in deinem Google Drive im Ordner „Berichtsheft“. Die App sieht nur Dateien, die sie selbst angelegt hat.',
    needsAuth: true,
    signedIn: function () { return !!token; },
    signIn: function () { return requestToken(''); },
    signOut: function () {
      if (token && window.google && google.accounts && google.accounts.oauth2) { try { google.accounts.oauth2.revoke(token, function () {}); } catch (e) {} }
      token = null; ids = { folder: null, data: null, images: null }; versions.data = null; lastImagesJson = null;
      try { localStorage.removeItem(CACHE); } catch (e) {}
    },
    load: function () {
      return locate().then(function () {
        return Promise.all([ids.data ? readFile(ids.data) : null, ids.images ? readFile(ids.images) : null]);
      }).then(function (r) {
        if (!r[0]) return null;
        var meta = JSON.parse(r[0]), images = r[1] ? JSON.parse(r[1]) : null;
        lastImagesJson = r[1];
        var d = join(meta, images); cache(d); return d;
      });
    },
    /** true, wenn die Daten auf einem anderen Gerät geändert wurden */
    remoteChanged: function () {
      if (!token || !ids.data) return Promise.resolve(false);
      return getVersion(ids.data).then(function (v) { return versions.data != null && String(v) !== String(versions.data); });
    },
    save: function (data) {
      cache(data);
      var parts = split(data), metaJson = JSON.stringify(parts.meta), imgJson = JSON.stringify(parts.images);
      var chain = ids.folder ? Promise.resolve() : locate();
      return chain.then(function () {
        if (!ids.data) return null;
        return getVersion(ids.data).then(function (v) {
          if (versions.data != null && String(v) !== String(versions.data)) {
            var e = new Error('Auf einem anderen Gerät wurde inzwischen etwas geändert.'); e.code = 'conflict'; throw e;
          }
        });
      }).then(function () {
        if (imgJson === lastImagesJson) return null;
        var p = ids.images ? writeFile(ids.images, imgJson) : createFile(IMAGES, 'application/json', ids.folder, imgJson);
        return p.then(function (f) { ids.images = f.id; lastImagesJson = imgJson; });
      }).then(function () {
        return ids.data ? writeFile(ids.data, metaJson) : createFile(DATA, 'application/json', ids.folder, metaJson);
      }).then(function (f) { ids.data = f.id; versions.data = f.version; return true; });
    },
    adoptRemote: function () {
      if (!ids.data) return Promise.resolve();
      return getVersion(ids.data).then(function (v) { versions.data = v; });
    },
    cached: function () { try { var s = localStorage.getItem(CACHE); return s ? JSON.parse(s) : null; } catch (e) { return null; } }
  };
  window.BH_STORE = DriveStore;
})();
