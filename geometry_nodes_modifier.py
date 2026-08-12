"""Compatibility helpers for Geometry Nodes modifier interface values."""


_MISSING = object()


def _rna_input(modifier, identifier):
    """Return Blender 5.2's RNA wrapper for a modifier input, if available."""
    interface = getattr(modifier, "properties", None)
    inputs = getattr(interface, "inputs", None)
    if inputs is None:
        return None
    return getattr(inputs, identifier, None)


def has_modifier_input(modifier, identifier):
    if not modifier or not identifier:
        return False

    socket = _rna_input(modifier, identifier)
    if socket is not None and hasattr(socket, "value"):
        return True

    try:
        return identifier in modifier
    except TypeError:
        return False


def get_modifier_input(modifier, identifier, default=None):
    if not modifier or not identifier:
        return default

    socket = _rna_input(modifier, identifier)
    if socket is not None and hasattr(socket, "value"):
        return socket.value

    try:
        value = modifier.get(identifier, _MISSING)
    except TypeError:
        return default
    return default if value is _MISSING else value


def set_modifier_input(modifier, identifier, value):
    if not modifier or not identifier:
        return False

    socket = _rna_input(modifier, identifier)
    if socket is not None and hasattr(socket, "value"):
        socket.value = value
        return True

    try:
        if identifier not in modifier:
            return False
        modifier[identifier] = value
        return True
    except TypeError:
        return False
