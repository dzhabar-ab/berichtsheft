"""Liest einen Berichtsheft-.docx (IHK-Vorlage) und erzeugt Daten im App-Format (JSON).
Bilder (Logo, Unterschriften) werden als data-URLs mitgegeben.
Aufruf: python3 import_docx.py <docx> <out.json>
"""
import sys, re, json, zipfile, base64, datetime, struct, hashlib
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
q = lambda t: W + t

src, out = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src)
doc = etree.fromstring(z.read('word/document.xml'))
rels = etree.fromstring(z.read('word/_rels/document.xml.rels'))
relmap = {r.get('Id'): r.get('Target') for r in rels}


def T(e): return ''.join(t.text or '' for t in e.iter(q('t')))
def pstyle(p):
    s = p.find(q('pPr') + '/' + q('pStyle'))
    return s.get(q('val')) if s is not None else None
def de2iso(s):
    s = re.sub(r'\.+', '.', s.strip())
    try: return datetime.datetime.strptime(s, '%d.%m.%Y').date().isoformat()
    except ValueError: return None

def img_info(path):
    data = z.read('word/' + path)
    ext = 'png' if data[:8] == b'\x89PNG\r\n\x1a\n' else 'jpg'
    if ext == 'png':
        w, h = struct.unpack('>II', data[16:24])
    else:
        i = 2; w = h = 0
        while i < len(data):
            if data[i] != 0xFF: i += 1; continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', data[i + 5:i + 9]); break
            i += 2 + struct.unpack('>H', data[i + 2:i + 4])[0]
    mime = 'image/png' if ext == 'png' else 'image/jpeg'
    return {'dataUrl': 'data:%s;base64,%s' % (mime, base64.b64encode(data).decode()), 'w': w, 'h': h, 'ext': ext,
            'hash': hashlib.md5(data).hexdigest()}

body = doc.find(q('body'))
kids = list(body)
heads = [i for i, k in enumerate(kids) if k.tag == q('p') and T(k).strip() and (pstyle(k) in ('Heading2', 'berschrift2', 'Überschrift2') or T(k).strip().startswith('Ausbildungsnachweis (w'))]
weeks = []; name = ''; me_imgs = {}; aus_imgs = {}
for hi, start in enumerate(heads):
    end = heads[hi + 1] if hi + 1 < len(heads) else len(kids)
    blk = kids[start:end]
    tbls = [k for k in blk if k.tag == q('tbl')]
    if len(tbls) < 2: continue
    hrows = [[T(tc).strip() for tc in tr.findall(q('tc'))] for tr in tbls[0].findall(q('tr'))]
    name = name or hrows[0][1]
    monday = de2iso(hrows[2][1])
    if not monday: continue
    trs = tbls[1].findall(q('tr'))
    def sec(ri):
        tcs = trs[ri].findall(q('tc'))
        lines = []
        for p in tcs[0].findall(q('p')):
            t = re.sub(r'\s+', ' ', T(p)).strip()
            if not t: continue
            il = p.find('.//' + q('ilvl'))
            lines.append(('- ' if il is not None and il.get(q('val')) != '0' else '') + t)
        return {'text': '\n'.join(lines), 'hours': T(tcs[-1]).strip()}
    wk = {'id': monday, 'monday': monday, 'jahr': hrows[1][1], 'abteilung': hrows[1][3],
          'b': sec(1), 'u': sec(3), 's': sec(5), 'absence': None, 'sign': {'me': False, 'ausbilderId': None, 'date': None}}
    if len(trs) > 6:
        tcs = trs[6].findall(q('tc'))
        label = re.sub(r'\s+', ' ', T(tcs[0])).strip(); hrs = T(tcs[-1]).strip()
        if label or hrs:
            typ = label if label in ('Urlaub', 'Krank', 'Feiertage') else 'Sonstiges'
            wk['absence'] = {'type': typ, 'text': '' if typ != 'Sonstiges' else label, 'hours': hrs}
    # Unterschriften: Absätze zwischen Inhaltstabelle und Unterschriftentabelle
    if len(tbls) >= 3:
        i0, i1 = blk.index(tbls[1]), blk.index(tbls[2])
        items = []
        for p in blk[i0 + 1:i1]:
            for el in p.iter(q('t'), q('drawing'), q('tab')):
                if el.tag == q('t'):
                    for d in re.findall(r'\d\d\.\d\d\.+\d{4}', el.text or ''): items.append(('d', de2iso(d)))
                elif el.tag == q('drawing'):
                    blip = el.find('.//' + A + 'blip'); items.append(('i', relmap.get(blip.get(R + 'embed'))))
                else: items.append(('tab', None))
        groups = [[], []]; g = 0; nd = 0
        for k, v in items:
            if k == 'tab' and (groups[0]): g = 1; continue
            if k == 'd':
                nd += 1
                if nd == 2: g = 1
            if k != 'tab': groups[g].append((k, v))
        dates = [v for k, v in items if k == 'd' and v]
        if dates and dates[0] != datetime.date.fromisoformat(monday).__add__(datetime.timedelta(days=7)).isoformat():
            wk['sign']['date'] = dates[0]
        mi = [v for k, v in groups[0] if k == 'i']; ai = [v for k, v in groups[1] if k == 'i']
        if mi or any(k == 'd' for k, _ in groups[0]):
            wk['sign']['me'] = True
            if mi: me_imgs[mi[0]] = me_imgs.get(mi[0], 0) + 1
        if ai:
            inf = img_info(ai[0]); key = inf['hash']
            if key not in aus_imgs: aus_imgs[key] = dict(inf, id='aus%d' % (len(aus_imgs) + 1), name='Ausbilder/in %d' % (len(aus_imgs) + 1))
            wk['sign']['ausbilderId'] = aus_imgs[key]['id']
    weeks.append(wk)

settings = {'name': name, 'logo': None, 'mySig': None, 'ausbilderSigs': []}
if me_imgs:
    settings['mySig'] = img_info(max(me_imgs, key=me_imgs.get))
for v in aus_imgs.values():
    v.pop('hash', None); settings['ausbilderSigs'].append(v)
if settings['mySig']: settings['mySig'].pop('hash', None)
# Logo aus der Kopfzeile
for hn in ('word/_rels/header1.xml.rels', 'word/_rels/header2.xml.rels'):
    try:
        hr = etree.fromstring(z.read(hn))
        for r in hr:
            if r.get('Type', '').endswith('/image'):
                settings['logo'] = img_info(r.get('Target')); settings['logo'].pop('hash', None); break
    except KeyError: pass
    if settings['logo']: break
deps = []
for w in weeks:
    if w['abteilung'] and w['abteilung'] not in deps: deps.append(w['abteilung'])
settings['abteilungen'] = deps
settings['lastAbteilung'] = weeks[-1]['abteilung'] if weeks else ''
settings['lastJahr'] = weeks[-1]['jahr'] if weeks else '1'
json.dump({'version': 1, 'settings': settings, 'weeks': weeks}, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
print('weeks', len(weeks), 'aus sigs', len(settings['ausbilderSigs']), 'mySig', bool(settings['mySig']), 'logo', bool(settings['logo']))
print('signed me', sum(w['sign']['me'] for w in weeks), 'aus', sum(bool(w['sign']['ausbilderId']) for w in weeks),
      'custom dates', [(w['monday'], w['sign']['date']) for w in weeks if w['sign']['date']])
print('absences', [(w['monday'], w['absence']) for w in weeks if w['absence']])
