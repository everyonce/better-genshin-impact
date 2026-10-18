"""Offline regression runner. Requires the existing validated OpenCV runtime."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
from PIL import Image, ImageEnhance

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'artifacts/release-r18/BetterGI-English-win-x64'
REF=ROOT/'Test/ActOnePilot/fixtures/hideout-return/checkpoint-6.jpg'
SCRIPT=ROOT/'tools/quest-pilot/compare-route-anchor.ps1'
started=time.monotonic()
results=[]

def compare(name,path,heading=37,expected=False,reference=REF,expect_error=False):
    result=subprocess.run(['pwsh','-NoProfile','-File',str(SCRIPT),'-RuntimeDirectory',str(RUNTIME),
        '-ReferenceImage',str(reference),'-CandidateImage',str(path),'-ReferenceHeading','37',
        '-CandidateHeading',str(heading)],capture_output=True,text=True,encoding='utf-8',timeout=25)
    if expect_error:
        assert result.returncode!=0,(name,result.stdout)
        results.append(dict(name=name,passed=True,missingReferenceRejected=True));return
    assert result.returncode==0,(name,result.stderr)
    report=json.loads(result.stdout.strip())
    assert report['anchorAligned'] is expected,(name,report)
    assert report['gameplayAuthorized'] is False
    results.append(dict(name=name,passed=True,result=report))

with tempfile.TemporaryDirectory(prefix='bettergi-route-anchor-') as directory:
    p=Path(directory)
    changed=p/'brightness-and-jpeg.jpg'
    ImageEnhance.Brightness(Image.open(REF)).enhance(.85).save(changed,quality=70)
    compare('reference with exposure and JPEG perturbation',changed,expected=True)
    compare('same image but wrong approach heading',REF,heading=71)
    compare('entrance image is not a shelf anchor',ROOT/'Test/ActOnePilot/fixtures/hideout-return/checkpoint-7.jpg',heading=39)
    blank=p/'no-terrain.jpg';Image.new('RGB',(1280,720),'gray').save(blank)
    compare('no terrain evidence',blank)
    compare('missing upper landing reference',REF,reference=p/'unavailable-upper-landing.jpg',expect_error=True)
    for name,path,heading in [
        ('actual failed pre-hop view5079',RUNTIME/'User/JsScript/ActOnePilot/observations/mvcuzen8-drrh7eb3gqe/frame-5079.png',71),
        ('actual stalled seam5116',ROOT/'artifacts/hideout-seam-failure/5116.jpg',129),
        ('retired narrow upper shelf4821',ROOT/'artifacts/hideout-elevation-failure/4821.jpg',54)]:
        if path.exists():compare(name,path,heading)

report=dict(passed=len(results),failed=0,elapsedMs=round((time.monotonic()-started)*1000),gameplayInputs=0,tests=results)
(ROOT/'artifacts/act-two-route-anchor-regression-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['passed','failed','elapsedMs','gameplayInputs']}))
