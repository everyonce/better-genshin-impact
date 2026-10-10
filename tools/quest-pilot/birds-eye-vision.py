"""Read-only minimap marker and camera-cone estimate from BetterGI screenshots.

Angles are screen-polar: 0=east, 90=down, 180=west, 270=up.
Usage: python birds-eye-vision.py [frame.png ...]
"""
import json
import os
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

CENTER = (168.0, 125.0)
RADIUS = 105.0


def wrap(deg):
    return deg % 360.0


def analyze(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    dx, dy = xx - CENTER[0], yy - CENTER[1]
    rad = np.hypot(dx, dy)
    inside = rad < RADIUS

    # Yellow quest diamond: hue-independent RGB predicate, selecting the
    # bright saturated yellow pixels and requiring a compact connected blob.
    r, g, b = rgb.transpose(2, 0, 1)
    yellow = inside & (rad > 18) & (r > 175) & (g > 105) & (b < 100) & (r > g * 1.10) & (g > b * 1.35)
    ys, xs = np.where(yellow)
    quest = None
    qconf = 0.0
    if len(xs) >= 12:
        qx, qy = float(xs.mean()), float(ys.mean())
        qr = math.hypot(qx - CENTER[0], qy - CENTER[1])
        if qr <= RADIUS:
            quest = wrap(math.degrees(math.atan2(qy - CENTER[1], qx - CENTER[0])))
            qconf = min(0.99, 0.65 + len(xs) / 180.0)

    # Port the source detector's cyan-character mask to the central 30x30
    # minimap crop. The game arrow is the bright BGR cyan body (B>=250,R<=10).
    # Recover its convex hull and select the enclosing triangle's three corners;
    # the narrowest triangle corner is the arrow tip, matching the source's
    # base-midpoint-to-tip vector. Keep the polygon in absolute screenshot px.
    x1, x2 = int(CENTER[0] - 15), int(CENTER[0] + 15)
    y1, y2 = int(CENTER[1] - 15), int(CENTER[1] + 15)
    crop = rgb[y1:y2, x1:x2]
    cmask = (crop[:, :, 2] >= 250) & (crop[:, :, 0] <= 10)
    points = [(int(x + x1), int(y + y1)) for y, x in zip(*np.where(cmask))]
    # One 8-connected component, found with a tiny bounded flood fill.
    comps, unseen = [], set(points)
    while unseen:
        seed = unseen.pop()
        comp, stack = [seed], [seed]
        while stack:
            px, py = stack.pop()
            for ny in range(py - 1, py + 2):
                for nx in range(px - 1, px + 2):
                    p = (nx, ny)
                    if p in unseen:
                        unseen.remove(p); comp.append(p); stack.append(p)
        comps.append(comp)
    comp = max(comps, key=len) if comps else []
    hull = []
    if len(comp) >= 8:
        pts = sorted(set(comp))
        def cross(o, a, b):
            return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
        lower = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0: lower.pop()
            lower.append(p)
        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0: upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
    tri, char_angle, char_conf = [], None, 0.0
    if 3 <= len(hull) <= 30:
        # Maximum-area triangle inscribed in the hull gives stable silhouette
        # corners despite the antialiased cyan edge.
        best = None
        for i in range(len(hull)):
            for j in range(i + 1, len(hull)):
                for k in range(j + 1, len(hull)):
                    t = (hull[i], hull[j], hull[k])
                    area2 = abs(cross(t[0], t[1], t[2]))
                    if best is None or area2 > best[0]: best = (area2, t)
        if best and best[0] >= 80:
            tri = list(best[1])
            # Port source's notch test: along each edge-midpoint -> opposite
            # corner segment, count pixels before reaching the inner cyan fill.
            # The longest initial non-cyan run identifies the hollow/notched
            # side and therefore the arrow tip.
            mx, mn, val = crop.max(axis=2), crop.min(axis=2), crop.max(axis=2)
            delta = mx - mn
            sat = delta / np.maximum(mx, 1.0)
            # OpenCV hue scale 0..179, threshold H>=93,S>=155,V>=170.
            maxidx = np.argmax(crop, axis=2)
            hue = np.zeros(crop.shape[:2], dtype=float)
            nz = delta > 0
            hue[nz & (maxidx == 0)] = ((crop[:, :, 1] - crop[:, :, 2]) / np.maximum(delta, 1) % 6)[nz & (maxidx == 0)] * 60
            hue[nz & (maxidx == 1)] = (((crop[:, :, 2] - crop[:, :, 0]) / np.maximum(delta, 1)) + 2)[nz & (maxidx == 1)] * 60
            hue[nz & (maxidx == 2)] = (((crop[:, :, 0] - crop[:, :, 1]) / np.maximum(delta, 1)) + 4)[nz & (maxidx == 2)] * 60
            hsvcyan = (hue / 2 >= 93) & (sat * 255 >= 155) & (val >= 170)
            candidates = []
            for i in range(3):
                a, b, tip = tri[i], tri[(i+1)%3], tri[(i+2)%3]
                start = ((a[0]+b[0])//2, (a[1]+b[1])//2)
                end = tip
                steps = max(abs(end[0]-start[0]), abs(end[1]-start[1]))
                gap = 0
                for t in np.linspace(0, 1, steps + 1):
                    px = int(round(start[0] + t*(end[0]-start[0]))) - x1
                    py = int(round(start[1] + t*(end[1]-start[1]))) - y1
                    if 0 <= px < 30 and 0 <= py < 30 and hsvcyan[py, px]: break
                    gap += 1
                candidates.append((gap, start, tip))
            candidates.sort(key=lambda z: z[0], reverse=True)
            gap, base, tipxy = candidates[0]
            next_gap = candidates[1][0]
            vec = np.array(tipxy, dtype=float) - np.array(base, dtype=float)
            char_angle = wrap(math.degrees(math.atan2(vec[1], vec[0])))
            margin = gap - next_gap
            char_conf = min(0.98, 0.5 + margin / 12 + min(len(comp), 120) / 600)
            if gap < 2 or margin < 2 or len(comp) < 12:
                char_angle, char_conf = None, 0.0
            else:
                tri = [tipxy, *[p for p in tri if p != tipxy]]

    # The camera wedge is a neutral gray overlay. Restrict to its annular
    # footprint to avoid the cyan player glyph and seek a coherent angular
    # concentration. A broad/weak distribution is reported as ambiguous.
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    saturation = (mx - mn) / np.maximum(mx, 1.0)
    value = rgb.mean(axis=2)
    gray = inside & (rad >= 24) & (rad <= 76) & (saturation < 0.20) & (value >= 45) & (value <= 165)
    # Angular histogram, smoothed over 11 degrees, weighted by distance from
    # the player. This emphasizes the broad visible fan over nearby clutter.
    angles = np.degrees(np.arctan2(dy, dx)) % 360
    hist = np.zeros(360, dtype=np.float64)
    bins = angles[gray].astype(int)
    np.add.at(hist, bins, np.maximum(rad[gray] - 18, 1))
    kernel = np.array([1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1], dtype=float)
    kernel /= kernel.sum()
    smooth = sum(np.roll(hist, k - 5) * kernel[k] for k in range(11))
    peak = int(np.argmax(smooth))
    # Use the local circular mean of the peak's 17-degree neighborhood.
    local = (np.arange(360) - peak + 180) % 360 - 180
    use = np.abs(local) <= 8
    weights = smooth[use]
    a = np.radians(np.arange(360)[use])
    angle = wrap(math.degrees(math.atan2(float(np.sum(weights * np.sin(a))), float(np.sum(weights * np.cos(a))))))
    total = float(smooth.sum())
    peak_share = float(smooth[use].sum() / total) if total else 0.0
    sorted_peaks = np.sort(smooth)
    dominance = float(smooth[peak] / (sorted_peaks[-2] + 1e-9)) if len(sorted_peaks) > 1 else 0.0
    # A high histogram peak can be caused by the static south/east UI shading
    # or forest trunks. Require enough concentration and a meaningful lead;
    # otherwise withhold the bearing rather than inventing a camera angle.
    cconf = min(0.99, max(0.0, 0.35 * peak_share * 360 / 17 + 0.15 * min(dominance, 2)))
    if not gray.any() or peak_share < 0.105 or dominance < 1.03 or cconf < 0.62:
        angle_out, cconf = None, 0.0
    else:
        angle_out, cconf = round(angle, 1), round(cconf, 3)

    return {
        "file": str(path),
        "camera_angle_screen_deg": angle_out,
        "camera_confidence": cconf,
        "quest_bearing_screen_deg": round(quest, 1) if quest is not None else None,
        "quest_confidence": round(qconf, 3),
        "character_angle_screen_deg": round(char_angle, 1) if char_angle is not None else None,
        "character_confidence": round(char_conf, 3),
        "character_polygon_px": tri,
        "convention": "0=east, 90=down, 180=west, 270=up",
    }


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        repo = Path(__file__).resolve().parents[2]
        app = Path(os.environ.get("BETTERGI_PILOT_APP_DIR", repo / "artifacts" / "release-r8" / "BetterGI-English-win-x64")).expanduser().resolve()
        base = app / "User" / "JsScript" / "OpeningQuestPilot" / "observations" / "mv2yv3qh-pja4f0d9w6t-9hpih71jge"
        paths = [base / "frame-0010.png", base / "frame-0011.png"]
    print(json.dumps([analyze(p) for p in paths], indent=2))
