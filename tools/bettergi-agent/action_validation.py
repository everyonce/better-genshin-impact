"""Offline action-shape checks; runtime authorization/deadlines remain server-owned."""
import string

BRIDGE_KEYS = set(string.ascii_uppercase + string.digits) | {'F' + str(i) for i in range(1, 13)} | {
    'SPACE', 'SHIFT', 'LSHIFT', 'CONTROL', 'LCONTROL', 'ESC', 'ESCAPE', 'TAB',
    'LBUTTON', 'RBUTTON', 'MBUTTON', 'UP', 'DOWN', 'LEFT', 'RIGHT'}


def protocol_rejection(result, source_size):
    """Describe static incompatibility without claiming the server executed input."""
    if not result.get('parseValid'):
        return 'invalid_parse'
    if result.get('scrollUnsupported'):
        return 'unsupported_scroll'
    steps = result.get('steps', [])
    if not 1 <= len(steps) <= 6:
        return 'invalid_steps'
    duration = 0
    for step in steps:
        duration += step['durationMs']
        if not 33 <= step['durationMs'] <= 100:
            return 'invalid_interval'
        keys = set(step['keys'])
        if len(step['keys']) > 12 or not keys <= BRIDGE_KEYS:
            return 'unsupported_keys'
        if keys & {'CONTROL', 'LCONTROL'} and keys & {'ESC', 'ESCAPE'}:
            return 'reserved_hotkey'
        if abs(step['mouseDx']) > source_size[0] or abs(step['mouseDy']) > source_size[1]:
            return 'invalid_mouse_delta'
    return 'invalid_horizon' if duration > 250 else None


def action_observations(result, source_size):
    """Separate parser success, protocol shape, and an actual change in input."""
    reason = protocol_rejection(result, source_size)
    return {'protocolCompatible': reason is None, 'protocolRejection': reason,
            'noOpAction': bool(result.get('steps')) and all(
                not step['keys'] and step['mouseDx'] == 0 and step['mouseDy'] == 0
                for step in result.get('steps', []))}
