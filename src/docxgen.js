/* Berichtsheft – Word-Generator (läuft im Browser und in Node).
 * buildDocx(data, template, JSZip) -> Promise<Uint8Array>
 * data = { settings:{name, logo, mySig, ausbilderSigs:[...]}, weeks:[...] }
 * Bilder: { bytes:Uint8Array, ext:'png'|'jpg', w, h }
 */
(function (root) {
  'use strict';

  var EMU_PER_PX = 9525;
  var SIG_MAX_W = 1300000, SIG_MAX_H = 520000;      // Unterschrift-Box
  var LOGO_H = 368300, LOGO_MAX_W = 2400000;        // Logo im Kopf
  // Zeilenhöhen der drei Abschnitte (twips) – wie im Original
  var STD = { B: 2279, U: 2278, S: 2280 };
  var ABS_ROW = 400;
  var CHARS_PER_LINE = 78, LINE_TW = 232, CELL_PAD_TW = 90;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/[<]/g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function parseISO(iso) { var p = iso.split('-'); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
  function addDays(iso, n) { var d = parseISO(iso); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function de(iso) { if (!iso) return ''; var p = iso.split('-'); return p[2] + '.' + p[1] + '.' + p[0]; }

  /** Textfeld -> Liste von {lvl, text}. Zeile mit "-" am Anfang = Unterpunkt. */
  function parseItems(text) {
    var out = [];
    String(text || '').split(/\r?\n/).forEach(function (line) {
      if (!line.trim()) return;
      var m = line.match(/^\s*[-–o]\s+(.*)$/);
      if (m) { out.push({ lvl: 1, text: m[1].trim() }); return; }
      out.push({ lvl: 0, text: line.replace(/^\s*[•·*]\s*/, '').trim() });
    });
    return out;
  }

  function hoursStr(h) {
    if (h === null || h === undefined || h === '') return '';
    var n = Number(String(h).replace(',', '.'));
    if (!isFinite(n) || n === 0) return '';
    return String(h).trim();
  }

  var RPR = '<w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>';
  function bulletP(it) {
    return '<w:p><w:pPr><w:pStyle w:val="Normal"/><w:widowControl w:val="false"/><w:numPr><w:ilvl w:val="' + it.lvl +
      '"/><w:numId w:val="55"/></w:numPr><w:autoSpaceDE w:val="false"/>' + RPR + '</w:pPr><w:r>' + RPR +
      '<w:t xml:space="preserve">' + esc(it.text) + '</w:t></w:r></w:p>';
  }
  var EMPTY_P = '<w:p><w:pPr><w:pStyle w:val="Normal"/>' + RPR + '</w:pPr></w:p>';

  function estimateTw(items) {
    var lines = 0;
    items.forEach(function (it) {
      var cap = it.lvl ? CHARS_PER_LINE - 6 : CHARS_PER_LINE;
      lines += Math.max(1, Math.ceil(it.text.length / cap));
    });
    return lines * LINE_TW + CELL_PAD_TW;
  }

  /** Mindesthöhen so verteilen, dass die Woche möglichst auf eine Seite passt. */
  function rowHeights(itemsByKey, hasAbsence) {
    var std = { B: STD.B, U: STD.U, S: STD.S };
    if (hasAbsence) std.S -= ABS_ROW;
    var total = std.B + std.U + std.S;
    var need = {}, sumNeed = 0, sumMax = 0;
    ['B', 'U', 'S'].forEach(function (k) {
      need[k] = estimateTw(itemsByKey[k]);
      sumNeed += need[k];
      sumMax += Math.max(need[k], std[k]);
    });
    if (sumMax <= total) return std;
    if (sumNeed >= total) return { B: need.B, U: need.U, S: need.S };
    // Restplatz proportional zu den Standardhöhen verteilen
    var rest = total - sumNeed, out = {};
    ['B', 'U', 'S'].forEach(function (k) { out[k] = Math.round(need[k] + rest * std[k] / (STD.B + STD.U + STD.S)); });
    return out;
  }

  function fitBox(w, h, maxW, maxH) {
    var cx = w * EMU_PER_PX, cy = h * EMU_PER_PX;
    var s = Math.min(maxW / cx, maxH / cy);
    return { cx: Math.round(cx * s), cy: Math.round(cy * s) };
  }

  function drawing(rid, id, box) {
    return '<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="' + box.cx + '" cy="' + box.cy +
      '"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="' + id + '" name="Unterschrift ' + id +
      '"/><wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>' +
      '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">' +
      '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="' + id + '" name="Unterschrift ' + id +
      '"/><pic:cNvPicPr><a:picLocks noChangeAspect="1" noChangeArrowheads="1"/></pic:cNvPicPr></pic:nvPicPr><pic:blipFill><a:blip r:embed="' + rid +
      '"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr bwMode="auto"><a:xfrm><a:off x="0" y="0"/><a:ext cx="' + box.cx + '" cy="' + box.cy +
      '"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>';
  }

  function run(inner) { return '<w:r>' + RPR + inner + '</w:r>'; }

  function signDate(week) { return week.sign && week.sign.date ? week.sign.date : addDays(week.monday, 7); }

  function buildDocx(data, tpl, JSZip) {
    var settings = data.settings || {};
    var weeks = (data.weeks || []).slice().sort(function (a, b) { return a.monday < b.monday ? -1 : 1; });
    var zip = new JSZip();
    var _file = zip.file.bind(zip);
    zip.file = function (p, c) { return _file(p, c, { createFolders: false }); };
    var rels = [], relIds = {}, media = {}, docPrId = 1000;

    function imageRel(key, img) {
      if (relIds[key]) return relIds[key];
      var n = rels.length + 1, file = 'sig' + n + '.' + img.ext, rid = 'rIdImg' + n;
      rels.push('<Relationship Id="' + rid + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/' + file + '"/>');
      media[file] = img.bytes;
      relIds[key] = rid;
      return rid;
    }
    function sigRuns(key, img, dateIso) {
      var out = run('<w:t xml:space="preserve">' + esc(de(dateIso)) + '  </w:t>');
      if (img) out += run(drawing(imageRel(key, img), ++docPrId, fitBox(img.w, img.h, SIG_MAX_W, SIG_MAX_H)));
      return out;
    }
    var aus = {};
    (settings.ausbilderSigs || []).forEach(function (s) { aus[s.id] = s; });

    var body = weeks.map(function (w, i) {
      var items = { B: parseItems(w.b && w.b.text), U: parseItems(w.u && w.u.text), S: parseItems(w.s && w.s.text) };
      var hasAbs = !!(w.absence && (w.absence.type || w.absence.text));
      var rh = rowHeights(items, hasAbs);
      var x = tpl.week;
      x = x.replace('<!--PBB-->', i === 0 ? '' : '<w:pageBreakBefore/>');
      x = x.replace('@@NAME@@', esc(settings.name || ''))
        .replace('@@JAHR@@', esc(w.jahr || ''))
        .replace('@@ABT@@', esc(w.abteilung || ''))
        .replace('@@VOM@@', de(w.monday))
        .replace('@@BIS@@', de(addDays(w.monday, 6)));
      ['B', 'U', 'S'].forEach(function (k) {
        var sec = w[k.toLowerCase()] || {};
        x = x.replace('@@RH_' + k + '@@', String(rh[k]))
          .replace('<!--ITEMS_' + k + '-->', items[k].length ? items[k].map(bulletP).join('') : EMPTY_P)
          .replace('@@H_' + k + '@@', esc(hoursStr(sec.hours)));
      });
      var absXml = '';
      if (hasAbs) {
        var label = w.absence.type === 'Sonstiges' || !w.absence.type ? (w.absence.text || '') : w.absence.type;
        absXml = tpl.absRow.replace('@@ABS_LABEL@@', esc(label)).replace('@@ABS_H@@', esc(hoursStr(w.absence.hours)));
      }
      x = x.replace('<!--ABSENCE_ROW-->', absXml);
      // Unterschriften
      var sign = w.sign || {}, d = signDate(w), runs = '';
      if (sign.me) runs += sigRuns('me', settings.mySig, d);
      if (sign.ausbilderId) {
        runs += run('<w:tab/>');
        runs += sigRuns('aus:' + sign.ausbilderId, aus[sign.ausbilderId] || null, d);
      }
      var sigP = '<w:p><w:pPr><w:pStyle w:val="BodyText"/><w:tabs><w:tab w:val="left" w:pos="5889"/></w:tabs>' +
        '<w:spacing w:before="0" w:after="0"/><w:ind w:start="216"/>' + RPR + '</w:pPr>' + runs + '</w:p>';
      x = x.replace('<!--SIG_PARA-->', sigP);
      return x;
    }).join('');

    var endP = '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/><w:rPr><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr></w:pPr></w:p>';
    zip.file('word/document.xml', tpl.docPrefix + body + endP + tpl.docSuffix);

    var now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    Object.keys(tpl.files).forEach(function (p) {
      var c = tpl.files[p];
      if (p === 'word/_rels/document.xml.rels') c = c.replace('</Relationships>', rels.join('') + '</Relationships>');
      if (p === 'docProps/core.xml') c = c.split('@@NAME@@').join(esc(settings.name || '')).split('@@NOW@@').join(now);
      zip.file(p, c);
    });
    // Logo
    var logo = settings.logo, logoFile, lb;
    if (logo) {
      logoFile = 'logo.' + logo.ext;
      var cx = Math.round(LOGO_H * logo.w / logo.h), cy = LOGO_H;
      if (cx > LOGO_MAX_W) { cy = Math.round(cy * LOGO_MAX_W / cx); cx = LOGO_MAX_W; }
      lb = { cx: cx, cy: cy };
      media[logoFile] = logo.bytes;
    } else {
      logoFile = 'logo.png'; lb = { cx: 12700, cy: 12700 };
      media[logoFile] = TRANSPARENT_PNG();
    }
    ['word/header1.xml', 'word/header2.xml'].forEach(function (p) {
      zip.file(p, tpl.files[p].split('@@LOGO_CX@@').join(lb.cx).split('@@LOGO_CY@@').join(lb.cy));
    });
    ['word/_rels/header1.xml.rels', 'word/_rels/header2.xml.rels'].forEach(function (p) {
      zip.file(p, tpl.files[p].replace('@@LOGO_FILE@@', logoFile));
    });
    Object.keys(media).forEach(function (f) { zip.file('word/media/' + f, media[f]); });
    return zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
  }

  function TRANSPARENT_PNG() {
    var b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
    if (typeof atob === 'function') { var s = atob(b64), a = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i); return a; }
    return new Uint8Array(Buffer.from(b64, 'base64'));
  }

  root.BerichtsheftDocx = { buildDocx: buildDocx, parseItems: parseItems, addDays: addDays, de: de, signDate: signDate };
})(typeof window !== 'undefined' ? window : module.exports);
