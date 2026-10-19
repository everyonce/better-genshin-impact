"""Hotload the tested stamina contour filter into retained R18, preserving rollback."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
name='climb-stamina.js'
source=root/'BetterGenshinImpact/User/JsScript/ActOnePilot'/name
target=root/'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot'/name
rollback=root/'artifacts/release-r18/rollback-stamina-contour-filter'
new=source.read_bytes();old=target.read_bytes()
if new==old:raise RuntimeError('Contour filter already deployed')
if b'function substantialBoxes(boxes)' not in new or b'function substantialBoxes(boxes)' in old:raise RuntimeError('Unexpected detector revision')
rollback.mkdir(parents=True,exist_ok=True)
(rollback/name).write_bytes(old)
manifest={'path':str(target),'previousSha256':hashlib.sha256(old).hexdigest(),'newSha256':hashlib.sha256(new).hexdigest(),'scriptRestartRequired':False,'liveClimbValidation':False}
(rollback/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
target.write_bytes(new)
if target.read_bytes()!=new:raise RuntimeError('Detector hotload did not persist')
print(json.dumps(manifest))
