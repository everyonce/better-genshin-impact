"""One patrol lease's optional trial of a measured horizontal camera response."""
import math

from hybrid_routes import route_heading


class PatrolCameraTrial:
    """Allow a calibrated turn only once the previous accepted mouse input has settled."""

    def __init__(self, calibration):
        self.calibration = calibration
        self.previous_request = None
        self.previous_deadline = None
        self.previous_end = None

    def accepted(self, request_id, observed_at, step):
        """Track every admitted mouse step, including small P2P movement corrections."""
        if step.get('mouseDx', 0) or step.get('mouseDy', 0):
            self.previous_request = request_id
            self.previous_deadline = observed_at + 150
            self.previous_end = None

    def receipt(self, receipt):
        """Only a terminal for the last admitted mouse request clears the pending barrier."""
        ended = receipt.get('endedAtMs')
        if (self.previous_request and receipt.get('requestId') == self.previous_request
                and type(ended) in (int, float) and math.isfinite(ended)):
            self.previous_end = ended

    def propose(self, selection, target, observed_at):
        """Produce a changed pulse in the native direction, preserving all other controls."""
        step = selection['step']
        if (selection['owner'] != 'hybrid-native' or selection['reason'] != 'nativeHeading'
                or step.get('durationMs') != 100 or step.get('keys') != [] or step.get('mouseDy') != 0
                or self.previous_request and self.previous_end is None):
            return None
        elapsed = (observed_at - max(self.previous_end, self.previous_deadline)
                   if self.previous_request else None)
        pose = selection['pose']
        error = (route_heading(pose, target) - pose['yawDegrees'] + 180) % 360 - 180
        dx = self.calibration.suggest(error, ms_since_last_mouse=math.inf if elapsed is None else elapsed)
        native = step['mouseDx']
        if type(dx) is not int or abs(dx) > 250 or dx*native <= 0 or dx == native:
            return None
        return dict(checkpointId=self.calibration.checkpoint_id, nativeMouseDx=native, proposedMouseDx=dx,
                    errorDegrees=error, msSinceLastMouse=elapsed, previousMouseRequestId=self.previous_request,
                    selected=True)
