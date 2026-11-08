import re, json, copy, os, sys
from lxml import etree
SRC=sys.argv[1]; OUT=sys.argv[2]
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
q=lambda t: W+t
def rd(p): return open(os.path.join(SRC,p),encoding='utf-8').read()
x=etree.parse(os.path.join(SRC,'word/document.xml')); root=x.getroot(); b=root.find(q('body'))
kids=list(b)
def T(e): return ''.join(t.text or '' for t in e.iter(q('t')))
def pstyle(p):
    s=p.find(q('pPr')+'/'+q('pStyle')); return s.get(q('val')) if s is not None else None
heads=[i for i,k in enumerate(kids) if k.tag==q('p') and pstyle(k)=='Heading2']
# week 2 block (has pageBreakBefore)
blk=[copy.deepcopy(k) for k in kids[heads[1]:heads[2]]]
# absence row from first content table with 7 rows
absrow=None
for i in range(len(heads)):
    end=heads[i+1] if i+1<len(heads) else len(kids)
    tb=[k for k in kids[heads[i]:end] if k.tag==q('tbl')]
    if len(tb)>1 and len(tb[1].findall(q('tr')))>6: absrow=copy.deepcopy(tb[1].findall(q('tr'))[6]); break
assert absrow is not None
def set_tok(p,tok):
    runs=[r for r in p.iter(q('r')) if r.find(q('t')) is not None]
    if not runs:
        r=etree.SubElement(p,q('r')); rp=etree.SubElement(r,q('rPr'))
        for tg in ('sz','szCs'): e=etree.SubElement(rp,q(tg)); e.set(q('val'),'20')
        etree.SubElement(r,q('t')); runs=[r]
    for r in runs[1:]: r.getparent().remove(r)
    ts=runs[0].findall(q('t'))
    for t in ts[1:]: runs[0].remove(t)
    ts[0].text=tok
tbls=[k for k in blk if k.tag==q('tbl')]
hdr,cont,sig=tbls
hrows=hdr.findall(q('tr'))
def cellp(tr,ci): return tr.findall(q('tc'))[ci].find(q('p'))
for (ri,ci,tok) in [(0,1,'@@NAME@@'),(1,1,'@@JAHR@@'),(1,3,'@@ABT@@'),(2,1,'@@VOM@@'),(2,3,'@@BIS@@')]:
    tc=hrows[ri].findall(q('tc'))[ci]
    ps=tc.findall(q('p'))
    for p in ps[1:]: tc.remove(p)
    set_tok(ps[0],tok)
crows=cont.findall(q('tr'))
for tr in crows[6:]: cont.remove(tr)
for ri,key in [(1,'B'),(3,'U'),(5,'S')]:
    tcs=crows[ri].findall(q('tc'))
    tc=tcs[0]
    for p in tc.findall(q('p')): tc.remove(p)
    tc.append(etree.Comment('ITEMS_'+key))
    hc=tcs[-1]; hps=hc.findall(q('p'))
    for p in hps[1:]: hc.remove(p)
    set_tok(hps[0],'@@H_'+key+'@@')
    h=crows[ri].find(q('trPr')+'/'+q('trHeight')); h.set(q('val'),'@@RH_'+key+'@@'); h.set(q('hRule'),'atLeast')
cont.append(etree.Comment('ABSENCE_ROW'))
# absence row tokens
atcs=absrow.findall(q('tc'))
for tc,tok in [(atcs[0],'@@ABS_LABEL@@'),(atcs[-1],'@@ABS_H@@')]:
    ps=tc.findall(q('p'))
    for p in ps[1:]: tc.remove(p)
    set_tok(ps[0],tok)
h=absrow.find(q('trPr')+'/'+q('trHeight')); h.set(q('val'),'400'); h.set(q('hRule'),'atLeast')
# signature paragraph -> marker
i_cont=blk.index(cont); i_sig=blk.index(sig)
sigp=[k for k in blk[i_cont+1:i_sig] if k.tag==q('p')][-1]
assert re.search(r'\d\d\.\d\d',T(sigp))
idx=blk.index(sigp); blk[idx]=etree.Comment('SIG_PARA')
# drop everything after sig table (should be nothing)
blk=blk[:blk.index(sig)+1]
# serialize via a container in the real document to avoid ns decls
for k in list(b):
    if k.tag!=q('sectPr'): b.remove(k)
sect=b.find(q('sectPr'))
for k in blk: sect.addprevious(k)
sect.addprevious(etree.Comment('END_WEEKS'))
sect.addprevious(etree.Comment('FRAG_ABS'))
sect.addprevious(absrow)
sect.addprevious(etree.Comment('/FRAG_ABS'))
s=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True).decode('utf-8')
pre,rest=s.split('<w:body>',1); pre+= '<w:body>'
week,rest=rest.split('<!--END_WEEKS-->',1)
absxml=rest.split('<!--FRAG_ABS-->',1)[1].split('<!--/FRAG_ABS-->',1)[0]
suffix=rest.split('<!--/FRAG_ABS-->',1)[1]  # sectPr + closing
week=week.replace('<w:pageBreakBefore/>','<!--PBB-->')
assert '<!--PBB-->' in week
# ---- other parts ----
files={}
keep=['[Content_Types].xml','_rels/.rels','word/styles.xml','word/settings.xml','word/fontTable.xml','word/theme/theme1.xml',
      'word/header1.xml','word/header2.xml','word/footer1.xml','word/footer2.xml',
      'word/_rels/header1.xml.rels','word/_rels/header2.xml.rels','word/numbering.xml','word/_rels/document.xml.rels']
for p in keep: files[p]=rd(p)
# content types: drop image overrides
files['[Content_Types].xml']=re.sub(r'<Override PartName="/word/media/[^"]+" ContentType="[^"]+"/>','',files['[Content_Types].xml'])
if 'Extension="jpg"' not in files['[Content_Types].xml']:
    files['[Content_Types].xml']=files['[Content_Types].xml'].replace('<Default Extension="png"','<Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="png"')
# document rels: drop image rels
files['word/_rels/document.xml.rels']=re.sub(r'<Relationship Id="[^"]+" Type="[^"]+/image" Target="[^"]+"/>','',files['word/_rels/document.xml.rels'])
# header rels: logo placeholder
for hp in ('word/_rels/header1.xml.rels','word/_rels/header2.xml.rels'):
    files[hp]=files[hp].replace('media/image5.png','media/@@LOGO_FILE@@')
for hp in ('word/header1.xml','word/header2.xml'):
    h=files[hp]
    h=re.sub(r'<wp:extent cx="1665605" cy="368300"/>','<wp:extent cx="@@LOGO_CX@@" cy="@@LOGO_CY@@"/>',h)
    h=re.sub(r'<a:ext cx="1665605" cy="368300"/>','<a:ext cx="@@LOGO_CX@@" cy="@@LOGO_CY@@"/>',h)
    h=re.sub(r'<a:srcRect[^/]*/>','',h)
    assert h.count('@@LOGO_CX@@')==2, hp
    files[hp]=h
# numbering: keep only numId 1 and 55 and their abstracts
num=files['word/numbering.xml']
nx=etree.fromstring(num.encode())
keepnum={'1','55'}; keepab=set()
for n in nx.findall(q('num')):
    if n.get(q('numId')) in keepnum: keepab.add(n.find(q('abstractNumId')).get(q('val')))
    else: nx.remove(n)
for a in nx.findall(q('abstractNum')):
    if a.get(q('abstractNumId')) not in keepab: nx.remove(a)
files['word/numbering.xml']=re.sub(r'(<w:pStyle w:val="[^"]*"/>)(<w:numFmt w:val="[^"]*"/>)',r'\2\1',etree.tostring(nx,xml_declaration=True,encoding='UTF-8',standalone=True).decode())
files['docProps/core.xml']=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
 '<dc:title>Ausbildungsnachweis</dc:title><dc:creator>@@NAME@@</dc:creator><cp:lastModifiedBy>@@NAME@@</cp:lastModifiedBy>'
 '<dcterms:created xsi:type="dcterms:W3CDTF">@@NOW@@</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">@@NOW@@</dcterms:modified></cp:coreProperties>')
files['docProps/app.xml']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Berichtsheft</Application></Properties>'
# footer: hardcoded page count "64" cached values -> fine (fields update). check personal data
allt=json.dumps(files,ensure_ascii=False)+week+absxml
for bad in [w for w in os.environ.get('BH_CHECK_WORDS','').split(',') if w]:
    if bad in allt: print('WARNING personal/content left:',bad)
tpl={'files':files,'docPrefix':pre,'docSuffix':suffix,'week':week,'absRow':absxml}
json.dump(tpl,open(OUT,'w',encoding='utf-8'),ensure_ascii=False)
print('ok', {k:len(v) for k,v in files.items()}, len(week), len(absxml), len(json.dumps(tpl)))
