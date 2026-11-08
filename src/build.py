"""Baut die App aus app_src.html + docxgen.js + template.json.
python3 build.py <template.json> <out_preview.html> [<out_github_index.html>]
"""
import json, sys, os
here = os.path.dirname(os.path.abspath(__file__))
tpl = json.load(open(sys.argv[1], encoding='utf-8'))
src = open(os.path.join(here, 'app_src.html'), encoding='utf-8').read()
gen = open(os.path.join(here, 'docxgen.js'), encoding='utf-8').read()

def js_safe(s):
    # "</script" und "<!--" dürfen in einem <script> nicht roh vorkommen
    return s.replace('</', '<\\/').replace('<!--', '<\\!--')

tjs = 'window.BH_TEMPLATE = ' + js_safe(json.dumps(tpl, ensure_ascii=False)) + ';'
assert '</script' not in tjs.lower()
out = src.replace('/*@@TEMPLATE@@*/', tjs).replace('/*@@DOCXGEN@@*/', js_safe(gen))
open(sys.argv[2], 'w', encoding='utf-8').write(out)
if len(sys.argv) > 3:
    drive = open(os.path.join(here, 'drive.js'), encoding='utf-8').read()
    inj = ('<script src="https://accounts.google.com/gsi/client" async defer></script>\n'
           '<script src="config.js"></script>\n<script>' + js_safe(drive) + '</script>\n')
    marker = '<script src="https://cdnjs.cloudflare.com'
    assert marker in out
    gh = out.replace(marker, inj + marker, 1)
    head, rest = gh.split('<style>', 1)
    full = ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            + head + '<style>' + rest.split('</style>', 1)[0] + '</style>\n</head>\n<body>\n'
            + rest.split('</style>', 1)[1] + '\n</body>\n</html>\n')
    open(sys.argv[3], 'w', encoding='utf-8').write(full)
print('ok', len(out))
