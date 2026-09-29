"""Narrow OS-source associations, never inference from names or co-occurrence."""
import hashlib
import hmac
import re

LINKABLE = frozenset(('ProcessDetector', 'OverlayDetector'))
SOURCE_KIND = 'windows_process_instance'


def source_for_process(pid, created, key):
    """Session-private pseudonym; raw PID/creation time never enter evidence."""
    if (type(pid) is not int or pid <= 0 or type(created) is not int or created <= 0
            or not isinstance(key, bytes) or len(key) != 32):
        return None
    value = f'{SOURCE_KIND}:{pid}:{created}'.encode('ascii')
    return {'kind': SOURCE_KIND, 'ref': hmac.new(key, value, hashlib.sha256).hexdigest()}


def source_ref(signal):
    if signal.detector not in LINKABLE:
        return None
    source = signal.evidence.get('source')
    if not isinstance(source, dict) or source.get('kind') != SOURCE_KIND:
        return None
    ref = source.get('ref')
    return ref if isinstance(ref, str) and re.fullmatch('[0-9a-f]{64}', ref) else None


def review_groups(results):
    """Group sampled observations of the same OS process; no duration/use claim."""
    groups = {}
    for result in results:
        if result.status not in ('partial', 'available') or result.detector not in LINKABLE:
            continue
        for signal in result.signals:
            ref = source_ref(signal) if signal.detector == result.detector else None
            if ref:
                group = groups.setdefault(ref, {'detectors': set(), 'signal_ids': set()})
                group['detectors'].add(result.detector)
                group['signal_ids'].add(signal.id)
    return [{'source_ref': ref, 'association': 'same_os_process_instance',
             'detectors': sorted(group['detectors']), 'signal_ids': sorted(group['signal_ids'])}
            for ref, group in sorted(groups.items()) if len(group['detectors']) > 1]
