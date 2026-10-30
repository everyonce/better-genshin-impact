"""Explicit duration, storage and route caps for ordinary and endurance destination leases."""
from dataclasses import dataclass


@dataclass(frozen=True)
class QueueLimits:
    """Bound one lease without changing its input, freshness, thermal or endpoint rules."""
    profile: str
    seconds: int
    batches: int
    legs: int
    recording_mib: int


STANDARD = QueueLimits('standard-v1', 600, 12, 96, 160)
ENDURANCE = QueueLimits('endurance-v1', 900, 40, 256, 384)


def queue_limits(profile=None):
    """Read an explicit profile; absent fields retain the original historical limits."""
    if profile is None or profile == STANDARD.profile:
        return STANDARD
    if profile == ENDURANCE.profile:
        return ENDURANCE
    raise ValueError('Unknown destination queue limits profile')
