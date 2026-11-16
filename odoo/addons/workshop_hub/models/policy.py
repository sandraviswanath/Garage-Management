"""Pure validation shared by controllers/models; executable without Odoo."""
import base64
import binascii
import math

TRANSITIONS = {
    'approved': {'in_progress'},
    'assigned': {'in_progress'},
    'in_progress': {'waiting_parts', 'paused', 'completed'},
    'waiting_parts': {'in_progress'},
    'paused': {'in_progress'},
}

def technician_transition(current, target):
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError('This job status transition is not allowed.')

def positive_quantity(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('Enter a positive quantity.') from None
    if not math.isfinite(result) or result <= 0 or result > 10000:
        raise ValueError('Quantity must be greater than zero and at most 10,000.')
    return result

def photo_bytes(encoded):
    if not isinstance(encoded, str) or len(encoded) > 7_000_000:
        raise ValueError('Photo must be a JPEG or PNG up to 5 MB.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError('Invalid photo encoding.') from None
    if not raw or len(raw) > 5 * 1024 * 1024:
        raise ValueError('Photo must be up to 5 MB.')
    if raw.startswith(b'\xff\xd8\xff'):
        return raw, 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return raw, 'image/png'
    raise ValueError('Only JPEG and PNG photos are accepted.')
