"""Advance only verified Paimon dialogue; stop on choices, HUD, or unknown UI."""
import importlib.util, json, time
from pathlib import Path
s=importlib.util.spec_from_file_location('bridge',Path(__file__).with_name('birds-eye-steer.py'))
b=importlib.util.module_from_spec(s); s.loader.exec_module(b)
seen={}
o=b.send(b.read(),'observe')
for _ in range(16):
    rows=o['ocr']
    speaker=any(r['text']=='Paimon' and 700<r['x']<1200 and 800<r['y']<900 for r in rows)
    auto=any(r['text']=='Auto' and r['x']<200 and r['y']<100 for r in rows)
    lines=[r['text'] for r in rows if 890<r['y']<1020 and not r['text'].startswith('UID')]
    if not(speaker and auto and lines):
        print(json.dumps({'stopped':'not verified Paimon dialogue','frame':o['frameId'],'ocr':[r['text'] for r in rows]})); break
    if any(400<r['y']<800 and r['x']>900 and len(r['text'])>3 for r in rows):
        print(json.dumps({'stopped':'possible dialogue choice','frame':o['frameId']})); break
    signature='|'.join(lines)
    if seen.get(signature,0)>=2:
        print(json.dumps({'stopped':'dialogue did not advance','frame':o['frameId']})); break
    seen[signature]=seen.get(signature,0)+1
    print(json.dumps({'frame':o['frameId'],'subtitle':signature}),flush=True)
    o=b.send(o,'keyPress',key='VK_SPACE')
    time.sleep(2)
    o=b.send(o,'observe')
print(str(b.ROOT/o['screenshotPath']))
