"""Versioned candidate inventory checksum; consistency, never attestation."""
import hashlib
import json
import re
from datetime import datetime

FORMAT = 'iim.extensions.v2'
BOUND_FORMAT = 'iim.extensions.v3'
MAX_AGE_SECONDS = 300


def bound_checksum(data):
    # Ordered array avoids cross-language object-key ordering differences.
    value = [BOUND_FORMAT, data['session_id'], data['exported_at'], data['browser'], data['profile'],
             checksum(clean_entries(data['extensions']))]
    encoded = json.dumps(value, ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def prepare_inventory(entries, digest, session_id, tick, imported_at):
    """Validate provenance claims and bound local freshness; no browser authentication."""
    if not isinstance(entries, dict) or entries.get('format') != BOUND_FORMAT:
        clean, checked = validate_inventory(entries, digest)
        metadata = {'format': entries.get('format', 'legacy') if isinstance(entries, dict) else 'legacy',
                    'imported_at': imported_at, 'exported_at': entries.get('exported_at') if isinstance(entries, dict) else None,
                    'session_bound': False, 'browser_authenticated': False,
                    'checksum_verified': checked, 'freshness': 'unverified', 'entry_count': len(clean)}
        # Retain only a bounded timestamp claim from older formats.
        if not isinstance(metadata['exported_at'], str) or len(metadata['exported_at']) > 80:
            metadata['exported_at'] = None
        return clean, metadata, None
    clean = clean_entries(entries.get('extensions'))
    if entries.get('session_id') != session_id:
        raise ValueError('Inventory belongs to another session; export it for the current session')
    for key in ('browser', 'profile'):
        value = entries.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100 or any(ord(c) < 32 for c in value):
            raise ValueError('Inventory requires short browser and profile labels')
    timestamp = entries.get('exported_at')
    if not isinstance(timestamp, str) or len(timestamp) > 80:
        raise ValueError('Inventory requires an export timestamp')
    try:
        exported = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if exported.tzinfo is None:
            raise ValueError()
        age = (datetime.fromisoformat(imported_at) - exported).total_seconds()
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid inventory export timestamp') from None
    if age < -60 or age >= MAX_AGE_SECONDS:
        raise ValueError('Inventory is future-dated or stale; export a fresh inventory')
    supplied = entries.get('digest')
    if not isinstance(supplied, str) or not re.fullmatch('[0-9a-fA-F]{64}', supplied) or supplied.lower() != bound_checksum(entries):
        raise ValueError('Inventory checksum does not match its contents and scope')
    metadata = {key: entries[key] for key in ('format', 'session_id', 'exported_at', 'browser', 'profile')}
    metadata.update(imported_at=imported_at, session_bound=True, browser_authenticated=False,
                    checksum_verified=True, freshness='fresh_claim', entry_count=len(clean))
    return clean, metadata, tick + MAX_AGE_SECONDS - max(0, age)


def clean_entries(entries):
    if not isinstance(entries, list) or len(entries) > 250:
        raise ValueError('Expected up to 250 extension entries')
    clean = []
    for row in entries:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not isinstance(row.get('enabled'), bool):
            raise ValueError('Each entry requires a name and enabled boolean')
        clean.append({'name': row['name'][:100], 'enabled': row['enabled']})
    return clean


def checksum(clean, format=FORMAT):
    if format == FORMAT:
        # ASCII-escaped rows, sorted by ASCII bytes, including the boolean tie-break.
        rows = sorted(json.dumps([r['name'], r['enabled']], ensure_ascii=True, separators=(',', ':')) for r in clean)
        encoded = '[' + ','.join(rows) + ']'
    elif format in (None, 'iim.extensions.v1'):
        rows = sorted([[r['name'], r['enabled']] for r in clean], key=lambda r: r[0])
        encoded = json.dumps(rows, separators=(',', ':'))
    else:
        raise ValueError('Unsupported extension inventory format; export it again with the current companion')
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def validate_inventory(entries, digest=None):
    format = None
    if isinstance(entries, dict):
        format = entries.get('format')
        digest = entries.get('digest', digest)
        entries = entries.get('extensions')
    if format not in (None, 'iim.extensions.v1', FORMAT):
        raise ValueError('Unsupported extension inventory format; export it again with the current companion')
    clean = clean_entries(entries)
    if format == FORMAT and digest is None:
        raise ValueError('Version 2 inventory requires a checksum')
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-fA-F]{64}', digest):
            raise ValueError('Expected a 64-character SHA-256 checksum')
        if checksum(clean, format) != digest.lower():
            raise ValueError('Inventory checksum does not match the file contents; export the inventory again. A checksum is not browser authentication.')
    return clean, digest is not None
