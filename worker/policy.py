"""Versioned, candidate-declared rules; never an authorization to collect more."""
import copy

PHASES = ('discussion', 'coding', 'open_book', 'collaboration')
FIELDS = {'version', 'phase', 'allowed_apps', 'phase_apps', 'max_displays', 'context'}


def _apps(value):
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError('Use at most 50 exact executable names per list')
    names = set()
    for name in value:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError('Executable names must contain 1–100 characters')
        name = name.strip().casefold().removesuffix('.exe')
        if not name or any(c in name for c in '/\\:*?<>|"') or any(ord(c) < 32 for c in name):
            raise ValueError('Use executable names only, without paths or wildcards')
        names.add(name)
    return sorted(names)


def normalize_policy(value=None, revision=1):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError('Unknown session policy fields')
    if type(value.get('version', 1)) is not int or value.get('version', 1) != 1:
        raise ValueError('Unsupported session policy version')
    phase = value.get('phase', 'discussion')
    if phase not in PHASES:
        raise ValueError('Unknown interview phase')
    by_phase = value.get('phase_apps', {})
    if not isinstance(by_phase, dict) or set(by_phase) - set(PHASES):
        raise ValueError('Unknown phase-specific rules')
    maximum = value.get('max_displays')
    if maximum is not None and (type(maximum) is not int or not 1 <= maximum <= 8):
        raise ValueError('Declared display limit must be an integer from 1 to 8')
    context = value.get('context', '')
    if not isinstance(context, str) or len(context) > 500:
        raise ValueError('Agreed context must be at most 500 characters')
    return {'version': 1, 'revision': revision, 'phase': phase,
            'approval_status': 'unverified', 'source': 'candidate',
            'allowed_apps': _apps(value.get('allowed_apps', [])),
            'phase_apps': {p: _apps(by_phase[p]) for p in PHASES if p in by_phase},
            'max_displays': maximum, 'context': context.strip()}


def requires_identity_review(evidence):
    """Existing metadata matches are hints, never authenticated app identity."""
    original = evidence.get('original_filename')
    process = evidence.get('process')
    different_original = (isinstance(original, str) and bool(original.strip())
                          and isinstance(process, str)
                          and original.casefold().removesuffix('.exe') != process.casefold().removesuffix('.exe'))
    product = evidence.get('matched_product')
    return different_original or (isinstance(product, str) and bool(product.strip()))


def apply_policy(results, policy):
    """Return a review view while preserving the raw detector observations."""
    if policy is None:
        return results
    allowed = set(policy['allowed_apps']) | set(policy['phase_apps'].get(policy['phase'], []))
    reviewed = copy.deepcopy(results)
    for result in reviewed:
        if result.detector == 'VirtualDisplayDetector' and policy.get('max_displays') is not None:
            count = result.metrics.get('active_desktop_monitors')
            maximum = policy['max_displays']
            assessment = ('unknown' if type(count) is not int or count < 1
                          else 'exceeds_declared_limit' if count > maximum else 'no_observed_excess')
            result.metrics.update(declared_limit=maximum, declared_limit_assessment=assessment,
                                  policy_approval='unverified')
            result.detail += f" Declared maximum: {maximum}; {assessment.replace('_', ' ')}. Policy approval unverified."
            if assessment == 'exceeds_declared_limit':
                from .detectors import signal as make_signal
                result.signals.append(make_signal(result.detector, 'declared_display_limit',
                    'Observed desktop monitor count exceeds declared limit', 1, 0,
                    {'active_desktop_monitors': count, 'declared_limit': maximum, 'policy_revision': policy['revision']},
                    'The OS reports more desktop monitors than the candidate-declared maximum. Review the agreement.',
                    'The policy is unverified. Mirrored physical displays and concealed hardware are not established. Excluded from index.'))
        if result.detector != 'ProcessDetector':
            continue
        for signal in result.signals:
            process = signal.evidence.get('process', '')
            if isinstance(process, str) and process.casefold().removesuffix('.exe') in allowed:
                identity_review = requires_identity_review(signal.evidence)
                signal.evidence['session_policy'] = {
                    'revision': policy['revision'], 'phase': policy['phase'],
                    'interpretation_version': 3, 'approval_status': 'unverified',
                    'disposition': 'identity_review' if identity_review else 'pending_review',
                    'original_weight': signal.weight}
                if identity_review:
                    signal.explanation += (' The candidate declared this executable name permitted, but binary metadata also matches a review rule. '
                                           'Application identity is not authenticated; this observation remains for human review '
                                           'with its original index weight. Metadata can be changed or refer to legitimate software.')
                else:
                    signal.explanation += (' The candidate declared this executable name permitted, but independent approval '
                                           'has not been verified. The exception is pending human review; original weight is retained. '
                                           'Name matching does not authenticate the application.')
    return reviewed
