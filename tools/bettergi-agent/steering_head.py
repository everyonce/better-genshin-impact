"""CPU-only, observational steering classifier for one qualified BetterGI frame."""
import hashlib
import json
import math
from pathlib import Path

from hybrid_routes import route_heading


CLASSES = ('forward', 'turnLeft', 'turnRight')
FEATURES = ('bias', 'signedBearingError', 'absoluteBearingError', 'distance',
            'p2pForward', 'p2pOtherKeys', 'p2pHorizontal', 'p2pVertical')
FORMAT = 'bettergi-route-steering-v1'


def finite(value):
    """Exclude bools, missing measurements and invalid floating point evidence."""
    return type(value) in (float, int) and math.isfinite(value)


def features(frame, goal_xy, raw_steps):
    """Use only the selected source pose, current waypoint and visual policy's raw proposal."""
    pose = frame.get('navigationPose') or {}
    gate = frame.get('frameWorldReadiness') or {}
    motion = frame.get('motionEvidence') or {}
    source = frame.get('sourceFrame') or {}
    if (not isinstance(goal_xy, (list, tuple)) or len(goal_xy) != 2
            or not all(finite(v) for v in goal_xy)
            or type(frame.get('frameId')) is not int or pose.get('frameId') != frame['frameId']
            or not source.get('captureEpoch') or type(source.get('timestamp100ns')) is not int
            or gate.get('ready') is not True or gate.get('sourceFrameId') != frame['frameId']
            or gate.get('sourceFrame') != source or frame.get('inputAvailable') is not True
            or pose.get('state') != 'valid' or pose.get('layerId') != 'City_102'
            or motion.get('status') != 'normal' or motion.get('spaceKeyMatched') is not False
            or not all(finite(pose.get(k)) for k in ('x', 'y', 'yawDegrees', 'positionConfidence', 'yawConfidence'))
            or not .99 <= pose['positionConfidence'] <= 1 or not .2 <= pose['yawConfidence'] <= 1
            or not 0 <= pose['yawDegrees'] < 360 or not isinstance(raw_steps, list) or len(raw_steps) != 1):
        return None
    step = raw_steps[0]
    if (not isinstance(step, dict) or not isinstance(step.get('keys'), list)
            or not all(isinstance(k, str) for k in step['keys'])
            or not all(finite(step.get(k)) for k in ('mouseDx', 'mouseDy'))):
        return None
    delta = (route_heading(pose, goal_xy) - pose['yawDegrees'] + 180) % 360 - 180
    keys = step['keys']
    return (1., max(-6., min(6., delta / 10)), min(6., abs(delta) / 10),
            min(1., math.hypot(goal_xy[0]-pose['x'], goal_xy[1]-pose['y']) / 20),
            float(keys == ['W']), float(bool(keys) and keys != ['W']),
            max(-1., min(1., step['mouseDx'] / 50)), max(-1., min(1., step['mouseDy'] / 50)))


class SteeringHead:
    """Three-class linear softmax head. Its public API produces no controller action."""
    def __init__(self, checkpoint):
        """Reject incompatible or non-finite weights before accepting shadow requests."""
        weights = checkpoint.get('weights')
        if (checkpoint.get('format') != FORMAT or checkpoint.get('classes') != list(CLASSES)
                or checkpoint.get('features') != list(FEATURES) or checkpoint.get('deployment') != 'shadow-only'
                or not isinstance(weights, list) or len(weights) != len(CLASSES)
                or not all(isinstance(row, list) and len(row) == len(FEATURES) and all(map(finite, row)) for row in weights)):
            raise ValueError('Invalid steering checkpoint')
        self.weights = weights
        self.checkpoint = checkpoint
        self.checkpoint_id = None

    @classmethod
    def load(cls, path):
        """Read portable JSON weights without importing training frameworks."""
        data = Path(path).read_bytes()
        head = cls(json.loads(data))
        head.checkpoint_id = hashlib.sha256(data).hexdigest()
        return head

    def classify(self, row):
        """Return the argmax and softmax score for a qualified feature vector."""
        scores = [sum(w*x for w, x in zip(weights, row)) for weights in self.weights]
        best = max(range(len(scores)), key=scores.__getitem__)
        return dict(actionClass=CLASSES[best], confidence=1/sum(math.exp(s-scores[best]) for s in scores))

    def predict(self, frame, goal_xy, raw_steps):
        """Predict from one contemporaneous pose and P2P proposal, or abstain."""
        row = features(frame, goal_xy, raw_steps)
        return None if row is None else self.classify(row)
