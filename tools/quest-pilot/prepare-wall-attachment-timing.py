"""Add a distinct guarded W600 attachment observation without touching other draft changes."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root / 'BetterGenshinImpact/User/JsScript/ActOnePilot'


def once(value, old, new):
    if value.count(old) != 1:
        raise RuntimeError(f'Expected exactly one anchor: {old[:100]}')
    return value.replace(old, new, 1)


bgi_path = source / 'bgi.js'
bgi = bgi_path.read_text(encoding='utf-8')
old_name = 'WallStaminaTiming'
new_name = 'WallAttachmentTiming'
old_marker = '        runActTwoWallStaminaTiming: async function(initial,observe){'
next_marker = '        runActTwoRiddleMount: async function(initial,observe){'
old_method = bgi[bgi.index(old_marker):bgi.index(next_marker, bgi.index(old_marker))]
new_method = old_method.replace(old_name, new_name).replace('wall-stamina-timing', 'wall-attachment-timing')
new_method = once(new_method, "frame-0013.json", "frame-0010.json")
new_method = once(new_method, "frame-0013.png", "frame-0010.png")
new_method = once(new_method, "actTwoWallTimingRelease", "actTwoWallAttachmentRelease")
new_method = once(new_method, "timingProbe:true", "attachmentTimingProbe:true")
new_method = once(new_method, "keyDown('VK_W');},", "keyDown('VK_W');return Date.now();},")
bgi = once(bgi, next_marker, new_method + next_marker)
old = "if(value.mission==='questStep'&&value.step==='actTwoWallStaminaTiming')names.push('act-two-wall-stamina-timing.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi = once(bgi, old, old + "\n            if(value.mission==='questStep'&&value.step==='actTwoWallAttachmentTiming')names.push('act-two-wall-attachment-timing.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi = once(bgi, "'actTwoWallLowRelease','actTwoWallStaminaTiming'].indexOf(request.step)>=0&&climbing", "'actTwoWallLowRelease','actTwoWallStaminaTiming','actTwoWallAttachmentTiming'].indexOf(request.step)>=0&&climbing")
bgi = once(bgi, "'actTwoWallLowRelease','actTwoWallStaminaTiming','actTwoMapClose'", "'actTwoWallLowRelease','actTwoWallStaminaTiming','actTwoWallAttachmentTiming','actTwoMapClose'")
bgi_path.write_text(bgi, encoding='utf-8')

mission_path = source / 'mission.js'
mission = mission_path.read_text(encoding='utf-8')
old = "        if(name==='actTwoWallStaminaTiming')return api.runActTwoWallStaminaTiming(observation,observe);"
mission = once(mission, old, old + "\n        if(name==='actTwoWallAttachmentTiming')return api.runActTwoWallAttachmentTiming(observation,observe);")
mission_path.write_text(mission, encoding='utf-8')
print('Added distinct W600 attachment timing dispatch')
