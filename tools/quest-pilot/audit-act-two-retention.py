"""Read-only runtime capture audit; never changes a gameplay checkpoint or deletes files."""
import json,os,shutil
from pathlib import Path
from datetime import datetime,timezone
root=Path(os.environ.get('BETTERGI_PILOT_APP_DIR','artifacts/release-r18/BetterGI-English-win-x64'))/'User/JsScript/ActOnePilot'
groups={k:dict(images=0,bytes=0) for k in ['recent','pinned']}
for line in (root/'capture-retention.tsv').read_text().splitlines():
 f=line.split('\t')
 if len(f)>=5 and (root/f[0]).is_file():
  g=groups['pinned' if f[4]=='1' else 'recent'];g['images']+=1;g['bytes']+=(root/f[0]).stat().st_size
a=dict(utc=datetime.now(timezone.utc).isoformat(),freeBytes=shutil.disk_usage(root).free,**groups,permanentDeletion=False)
a['withinPolicy']=a['freeBytes']>=2*1024**3 and groups['recent']['images']<=256 and groups['recent']['bytes']<=512*1024**2 and groups['pinned']['images']<=32 and groups['pinned']['bytes']<=64*1024**2
Path('artifacts/act-two-current-retention-audit.json').write_text(json.dumps(a,indent=2),encoding='utf-8')
print(json.dumps(a))
