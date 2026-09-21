"""Versioned candidate inventory checksum; consistency, never attestation."""
import hashlib
import json
import re

FORMAT = 'iim.extensions.v2'


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
