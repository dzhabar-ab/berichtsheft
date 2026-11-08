"""Feinschliff der Word-Vorlage (src/template.json).
- Innenabstand (wie bei „Betriebliche Tätigkeiten“: 103 twips) für Name, Abteilung, Datum vom/bis,
  Stundenfelder und die Abwesenheitszeile
- „Ausbildungswoche vom“ / „bis“ und die Datumsfelder vertikal mittig
Aufruf: python3 tools/patch_template.py src/template.json
"""
import json, re, sys

PAD = 103
path = sys.argv[1]
t = json.load(open(path, encoding='utf-8'))


def add_ind(tc):
    """Linken/rechten Einzug in jedem Absatz der Zelle setzen."""
    def fix_p(m):
        ppr = m.group(0)
        ppr = re.sub(r'<w:ind [^>]*/>', '', ppr)
        ind = '<w:ind w:start="%d" w:end="%d"/>' % (PAD, PAD)
        if '<w:jc ' in ppr:
            return ppr.replace('<w:jc ', ind + '<w:jc ', 1)
        if '<w:rPr>' in ppr:
            return ppr.replace('<w:rPr>', ind + '<w:rPr>', 1)
        return ppr.replace('</w:pPr>', ind + '</w:pPr>')
    return re.sub(r'<w:pPr>.*?</w:pPr>', fix_p, tc, flags=re.S)


def v_center(tc):
    def fix(m):
        tcpr = re.sub(r'<w:vAlign [^>]*/>', '', m.group(0))
        return tcpr.replace('</w:tcPr>', '<w:vAlign w:val="center"/></w:tcPr>')
    tc = re.sub(r'<w:tcPr>.*?</w:tcPr>', fix, tc, count=1, flags=re.S)
    # Abstand oben entfernen, damit der Text wirklich mittig sitzt
    return re.sub(r'<w:spacing w:before="\d+" w:after="0"/>', '<w:spacing w:before="0" w:after="0"/>', tc)


def patch_cells(xml, rules):
    def fix(m):
        tc = m.group(0)
        for test, funcs in rules:
            if test(tc):
                for f in funcs:
                    tc = f(tc)
        return tc
    return re.sub(r'<w:tc>.*?</w:tc>', fix, xml, flags=re.S)


has = lambda s: (lambda tc: s in tc)
label = lambda s: (lambda tc: s in re.sub(r'<[^>]+>', '', tc))

week_rules = [
    (has('@@NAME@@'), [add_ind]),
    (has('@@ABT@@'), [add_ind]),
    (has('@@VOM@@'), [add_ind, v_center]),
    (has('@@BIS@@'), [add_ind, v_center]),
    (label('Ausbildungswoche vom:'), [v_center]),
    (lambda tc: re.sub(r'<[^>]+>', '', tc).strip() == 'bis:', [v_center]),
    (has('@@H_B@@'), [add_ind]),
    (has('@@H_U@@'), [add_ind]),
    (has('@@H_S@@'), [add_ind]),
]
abs_rules = [
    (has('@@ABS_LABEL@@'), [add_ind]),
    (has('@@ABS_H@@'), [add_ind, v_center]),
]
before = t['week']
t['week'] = patch_cells(t['week'], week_rules)

# Kopf-Tabelle: Spalte 1 (Beschriftungen) etwas schmaler, Spalte 2 (Jahr / Datum vom) breiter,
# damit das Datum mit Innenabstand in eine Zeile passt. Gesamtbreite bleibt gleich.
SHIFT = 250
def widen(tbl):
    if '@@VOM@@' not in tbl or '<w:gridCol w:w="3250"/><w:gridCol w:w="1137"/>' not in tbl:
        return tbl
    tbl = tbl.replace('<w:gridCol w:w="3250"/><w:gridCol w:w="1137"/>',
                      '<w:gridCol w:w="%d"/><w:gridCol w:w="%d"/>' % (3250 - SHIFT, 1137 + SHIFT), 1)
    tbl = tbl.replace('<w:tcW w:w="3250" w:type="dxa"/>', '<w:tcW w:w="%d" w:type="dxa"/>' % (3250 - SHIFT))
    tbl = tbl.replace('<w:tcW w:w="1137" w:type="dxa"/>', '<w:tcW w:w="%d" w:type="dxa"/>' % (1137 + SHIFT))
    tbl = tbl.replace('<w:tcW w:w="6023" w:type="dxa"/>', '<w:tcW w:w="%d" w:type="dxa"/>' % (6023 + SHIFT))
    return tbl
t['week'] = re.sub(r'<w:tbl>.*?</w:tbl>', lambda m: widen(m.group(0)), t['week'], count=1, flags=re.S)
t['absRow'] = patch_cells(t['absRow'], abs_rules)

# Kopf-Tabelle so breit wie die Haupttabelle (Einzug 98, Breite 9642).
# Die zusätzliche Breite bekommt die letzte Spalte (Abteilung / Datum bis / Name).
def full_width(tbl):
    if '@@VOM@@' not in tbl or '<w:tblW w:w="9273" w:type="dxa"/>' not in tbl:
        return tbl
    extra = 9642 - 9273
    tbl = tbl.replace('<w:tblW w:w="9273" w:type="dxa"/>', '<w:tblW w:w="9642" w:type="dxa"/>', 1)
    tbl = tbl.replace('<w:tblInd w:w="149" w:type="dxa"/>', '<w:tblInd w:w="98" w:type="dxa"/>', 1)
    tbl = tbl.replace('<w:gridCol w:w="2269"/></w:tblGrid>', '<w:gridCol w:w="%d"/></w:tblGrid>' % (2269 + extra), 1)
    tbl = tbl.replace('<w:tcW w:w="2269" w:type="dxa"/>', '<w:tcW w:w="%d" w:type="dxa"/>' % (2269 + extra))
    tbl = tbl.replace('<w:tcW w:w="4252" w:type="dxa"/>', '<w:tcW w:w="%d" w:type="dxa"/>' % (4252 + extra))
    tbl = re.sub(r'<w:tcW w:w="(6273|6023)" w:type="dxa"/>', lambda m: '<w:tcW w:w="%d" w:type="dxa"/>' % (int(m.group(1)) + extra), tbl)
    return tbl
t['week'] = re.sub(r'<w:tbl>.*?</w:tbl>', lambda m: full_width(m.group(0)), t['week'], count=1, flags=re.S)
json.dump(t, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
print('week changed:', before != t['week'])
