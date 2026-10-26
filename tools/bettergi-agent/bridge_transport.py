"""Identify pipe I/O failures without replacing the caller's actual exception."""

_ORIGIN = object()
_KEY = '_bettergi_named_pipe_origin'
_VETO = '_bettergi_no_reconnect'


def pipe_io(operation, call, *args, **kwargs):
    """Called only at Bridge's local named-pipe open/read/write operations."""
    if operation not in ('open', 'read', 'write'):
        raise ValueError('Unknown named-pipe operation')
    try:
        return call(*args, **kwargs)
    except OSError as error:
        error.__dict__[_KEY] = (_ORIGIN, operation)
        raise


def pipe_eof(message):
    """Create EOF evidence only after the owned pipe returns zero bytes."""
    error = EOFError(message)
    error.__dict__[_KEY] = (_ORIGIN, 'eof')
    return error


def transport_origin(error):
    """Do not infer provenance from an error number, message or exception chain."""
    if not isinstance(error, (OSError, EOFError)):
        return None
    origin = error.__dict__.get(_KEY)
    if type(origin) is tuple and len(origin) == 2 and origin[0] is _ORIGIN:
        return origin[1]
    return None


def forbid_reconnect(error, reason):
    """Retain a terminal ownership/evidence condition on the original exception."""
    error.__dict__.setdefault(_VETO, reason)


def is_transport_failure(error):
    """Only explicitly identified pipe loss with no terminal veto permits retry."""
    return transport_origin(error) is not None and _VETO not in error.__dict__
