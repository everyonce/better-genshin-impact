"""Low-cost navigation evidence from the minimap and actual execution receipts.

This is a stall heuristic for the default 16:9 HUD, not localization or a task
success score. It ignores the center player/heading marker and never treats
proposed or merely accepted inputs as executed movement.
"""
from collections import deque
import threading

import numpy as np
from PIL import Image


class NavigationProgress:
    """Compare map surroundings over three seconds of receipt-confirmed movement."""
    def __init__(self, window_ms=3000, min_movement_ms=600, difference_threshold=2.0):
        self.window_ms = window_ms
        self.min_movement_ms = min_movement_ms
        self.difference_threshold = difference_threshold
        y, x = np.mgrid[:64, :64]
        radius = np.hypot(x-32, y-32)
        self.mask = (radius >= 13) & (radius <= 28)
        self._lock = threading.Lock()
        self._movement = deque(maxlen=512)
        self._seen = deque(maxlen=512)
        self.reset()

    def reset(self):
        """Discard scene-specific evidence on loading, focus, pause, or context changes."""
        self.reference = None
        self.reference_at = None
        self.last_sample_at = None
        with self._lock:
            self._movement.clear()
            self._seen.clear()

    def receipt(self, receipt):
        """Record completed applied intervals; accepted proposals without steps add nothing."""
        identity = receipt.get('requestId')
        with self._lock:
            if identity in self._seen:
                return
            self._seen.append(identity)
            steps = receipt.get('appliedSteps', [])
            for index, step in enumerate(steps):
                keys = set(step.get('keys', []))
                moving = (('W' in keys) != ('S' in keys)) or (('A' in keys) != ('D' in keys))
                if not moving:
                    continue
                begin = step['startedAtMs']
                end = steps[index+1]['startedAtMs'] if index+1 < len(steps) else receipt['endedAtMs']
                if end > begin:
                    self._movement.append((begin, end))

    def movement_between(self, start, end):
        """Measure confirmed held movement in the same server clock as captured images."""
        with self._lock:
            while self._movement and self._movement[0][1] < start:
                self._movement.popleft()
            return sum(max(0, min(end, finish)-max(start, begin)) for begin, finish in self._movement)

    def observe(self, image, captured_at_ms):
        """Return at most five small metrics per second; no controller actions are emitted."""
        if self.last_sample_at is not None and captured_at_ms-self.last_sample_at < 200:
            return None
        self.last_sample_at = captured_at_ms
        if abs(image.width/image.height-16/9) > .02:
            return {'state': 'unavailable', 'reason': 'unsupportedHudAspectRatio'}
        normalized = image if image.size == (640, 360) else image.resize((640, 360), Image.Resampling.BILINEAR)
        patch = np.asarray(normalized.convert('L').crop((26, 6, 90, 70)), dtype=np.float32)
        values = patch[self.mask]
        if values.std() < 4:
            return {'state': 'unavailable', 'reason': 'insufficientMinimapTexture'}
        if self.reference is None:
            self.reference, self.reference_at = values.copy(), captured_at_ms
            return {'state': 'collecting', 'windowMs': 0, 'executedMovementMs': 0, 'minimapDifference': 0}
        difference = float(np.abs(values-self.reference).mean())
        elapsed = captured_at_ms-self.reference_at
        movement = self.movement_between(self.reference_at, captured_at_ms)
        state = ('moving' if difference >= self.difference_threshold else
                 'stalled' if elapsed >= self.window_ms and movement >= self.min_movement_ms else
                 'insufficientExecutedMovement' if elapsed >= self.window_ms else 'collecting')
        result = {'state': state, 'windowMs': elapsed, 'executedMovementMs': movement,
                  'minimapDifference': difference, 'differenceThreshold': self.difference_threshold}
        if state in ('moving', 'stalled', 'insufficientExecutedMovement'):
            self.reference, self.reference_at = values.copy(), captured_at_ms
        return result
