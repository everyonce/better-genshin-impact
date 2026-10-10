"""Bounded NPC-follow controller using the existing BetterGI observation bridge.

This file defines an opt-in controller only. It sends no input unless invoked.
Use --confirmed-npc only after visually confirming Paimon at the marker in the
current scene; otherwise the marker must have a nearby distance label.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
APP = Path(os.environ.get("BETTERGI_PILOT_APP_DIR", REPO / "artifacts" / "release-r8" / "BetterGI-English-win-x64")).expanduser().resolve()
ROOT = APP / "User" / "JsScript" / "OpeningQuestPilot"
DOTNET = Path(os.environ.get("DOTNET_HOST_PATH", Path.home() / ".codex" / "tools" / "dotnet8" / "dotnet.exe")).expanduser()
DISTANCE_RE = re.compile(r"^\s*(\d{1,3})\s*m\s*$", re.IGNORECASE)


def load_steer():
    spec = importlib.util.spec_from_file_location("birds_eye_steer", BASE / "birds-eye-steer.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load birds-eye-steer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


steer = load_steer()


def world_candidates(o):
    screenshot = ROOT / o["screenshotPath"]
    command = [
        str(DOTNET), "exec",
        "--runtimeconfig", str(APP / "BetterGI.runtimeconfig.json"),
        "--depsfile", str(APP / "BetterGI.deps.json"),
        str(APP / "VisionProbe.dll"), str(screenshot),
    ]
    result = json.loads(subprocess.check_output(command, text=True))[0]
    if result.get("error"):
        raise RuntimeError("VisionProbe failed: " + result["error"])
    return result.get("world_marker_candidates") or []


def nearby_distance(o, marker):
    """Return the nearest OCR distance label below and close to a marker."""
    cx, cy = marker["center"]["x"], marker["center"]["y"]
    found = []
    for row in o.get("ocr", []):
        match = DISTANCE_RE.fullmatch(row.get("text", ""))
        if not match:
            continue
        tx = row.get("x", 0) + row.get("width", 0) / 2
        ty = row.get("y", 0) + row.get("height", 0) / 2
        dx, dy = abs(tx - cx), ty - cy
        if dx <= 120 and 15 <= dy <= 180:
            found.append((dx + dy * 0.25, int(match.group(1))))
    return min(found)[1] if found else None


def validate_marker(o, confirmed_npc):
    # Existing bridge guard: active game window/HUD, session 5, quest transition,
    # and health checks. Call for every frame immediately before any action.
    steer.world_hud(o)
    candidates = world_candidates(o)
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one world gold marker; found {len(candidates)}")
    marker = candidates[0]
    x = marker["center"]["x"]
    y = marker["center"]["y"]
    if not (450 <= x <= 1470 and 180 <= y <= 720):
        raise RuntimeError(f"Marker reached the stop boundary at ({x:.0f},{y:.0f})")
    distance = nearby_distance(o, marker)
    if distance is None and not confirmed_npc:
        raise RuntimeError("No nearby 1-3 digit meter label; use --confirmed-npc only after visual confirmation")
    return marker, distance


def run(confirmed_npc=False):
    actions = 0
    movements = 0
    consecutive_turns = 0

    # Obtain a new screenshot first. The current observation is HUD-checked
    # before requesting the fresh observe action through the authorized bridge.
    o = steer.read()
    steer.world_hud(o)
    o = steer.send(o, "observe")
    actions += 1

    while actions < 10:
        marker, distance = validate_marker(o, confirmed_npc)
        cx = marker["center"]["x"]
        error = cx - 960.0
        status = {
            "frame": o["frameId"], "marker_center": marker["center"],
            "distance_m": distance, "horizontal_error": round(error, 1),
            "actions": actions, "movement_holds": movements,
        }
        print(json.dumps(status), flush=True)

        if distance is not None and distance < 3:
            print(json.dumps({"stop": "within_3m", **status}), flush=True)
            return
        if abs(error) > 80:
            if consecutive_turns >= 2:
                print(json.dumps({"stop": "two_turn_limit_without_alignment", **status}), flush=True)
                return
            dx = max(-250, min(250, round(error * 0.65)))
            # validate_marker above calls world_hud immediately before action.
            o = steer.send(o, "moveMouseBy", dx=dx, dy=0)
            actions += 1
            consecutive_turns += 1
            continue

        if movements >= 4:
            print(json.dumps({"stop": "movement_hold_limit", **status}), flush=True)
            return
        # validate_marker above calls world_hud immediately before action.
        o = steer.send(o, "hold", key="VK_W", ms=800)
        actions += 1
        movements += 1
        consecutive_turns = 0

    print(json.dumps({"stop": "action_limit", "actions": actions, "movement_holds": movements}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirmed-npc", action="store_true",
        help="Override missing marker-distance OCR after visually confirming Paimon at the unique marker.",
    )
    args = parser.parse_args()
    run(args.confirmed_npc)
