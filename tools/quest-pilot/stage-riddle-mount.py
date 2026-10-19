"""Stage only mount dispatcher hunks, leaving unrelated bgi/mission drafts intact."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
base = 'BetterGenshinImpact/User/JsScript/ActOnePilot/'

def git(*args, data=None):
    result = subprocess.run(['git', *args], cwd=root, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=True)
    return result.stdout

def one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one anchor: {old[:80]}')
    return text.replace(old, new, 1)

staged = git('diff', '--cached', '--name-only').decode().splitlines()
for name in ('bgi.js', 'mission.js'):
    if base + name in staged:
        raise RuntimeError(f'{name} already staged; inspect it first')

source = (root / base / 'bgi.js').read_text(encoding='utf-8')
marker = '        runActTwoRiddleMount: async function(initial,observe){'
lower = '        runActTwoLowerClimb: async function(initial,observe){'
adapter = source[source.index(marker):source.index(lower, source.index(marker))]
bgi_path = base + 'bgi.js'
bgi = git('show', 'HEAD:' + bgi_path).decode()
bgi = one(bgi, lower, adapter + lower)
old = "if(value.mission==='questStep'&&value.step==='actTwoLowerClimb')names.push('act-two-lower-climb.js','act-two-field.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi = one(bgi, old, old + "\n            if(value.mission==='questStep'&&value.step==='actTwoRiddleMount')names.push('act-two-riddle-mount.js','field-progress.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi = one(bgi, "['actTwoField','actTwoLowerClimb','actTwoBoundedMount'].indexOf(request.step)>=0&&climbing", "['actTwoField','actTwoLowerClimb','actTwoBoundedMount','actTwoRiddleMount'].indexOf(request.step)>=0&&climbing")
bgi = one(bgi, "'actTwoField','actTwoFieldInspect','actTwoMapClose'", "'actTwoField','actTwoFieldInspect','actTwoRiddleMount','actTwoMapClose'")
mission_path = base + 'mission.js'
mission = git('show', 'HEAD:' + mission_path).decode()
old = "        if(name==='actTwoLowerClimb')return api.runActTwoLowerClimb(observation,observe);"
mission = one(mission, old, old + "\n        if(name==='actTwoRiddleMount')return api.runActTwoRiddleMount(observation,observe);")

for name, value in ((bgi_path, bgi), (mission_path, mission)):
    blob = git('hash-object', '-w', '--stdin', data=value.encode()).decode().strip()
    git('update-index', '--cacheinfo', f'100644,{blob},{name}')
    if git('show', ':' + name) != value.encode():
        raise RuntimeError(f'Staged content mismatch: {name}')
    print(f'{name} {blob}')
