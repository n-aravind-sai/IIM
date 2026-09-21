"""Candidate-reviewed session rules; never inferred from device presence."""
from .detectors import signal

def validate_policy(value):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {'allowed_apps', 'max_displays', 'phase'}:
        raise ValueError('Invalid session policy')
    apps = value.get('allowed_apps', [])
    limit = value.get('max_displays')
    phase = value.get('phase', 'discussion')
    if not isinstance(apps, list) or len(apps) > 30 or any(
        not isinstance(a, str) or not a.strip() or len(a) > 80 or any(c in a for c in '/\\\n\r') for a in apps
    ):
        raise ValueError('Provide up to 30 executable names without paths')
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 8):
        raise ValueError('Display limit must be an integer from 1 to 8')
    if phase not in ('discussion', 'independent', 'open_book'):
        raise ValueError('Invalid interview phase')
    return {'allowed_apps': sorted({a.strip().casefold().removesuffix('.exe') for a in apps}),
            'max_displays': limit, 'phase': phase}

def apply_policy(result, policy):
    # Preserve observations and explicitly explain why an agreed executable is unweighted.
    for item in result.signals:
        if result.detector == 'ProcessDetector' and item.evidence.get('process') in policy['allowed_apps'] and not item.evidence.get('permitted_by_session_policy'):
            item.weight = 0
            item.evidence['permitted_by_session_policy'] = True
            item.limitation += ' Candidate-reviewed session rules permit this executable name; identity is not authenticated.'
    count = result.metrics.get('active_displays')
    limit = policy['max_displays']
    if result.detector == 'VirtualDisplayDetector' and result.status in ('partial', 'available') and limit is not None and isinstance(count, int) and count > limit and not any(s.title == 'Display inventory exceeds session limit' for s in result.signals):
        result.signals.append(signal(result.detector, 'display_limit', 'Display inventory exceeds session limit',
            .7, 0, {'observed': count, 'allowed': limit}, 'The reported display inventory exceeds the agreed limit.',
            'Inventory may represent adapters rather than physical monitors. Review topology; excluded from index.'))
    return result
