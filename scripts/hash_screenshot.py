"""Offline byte-integrity helper; does not capture a screen or attest its completeness."""
import argparse
import hashlib
import hmac
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('file',type=Path);parser.add_argument('--expected-sha256')
args=parser.parse_args()
with args.file.open('rb') as source:
    hasher=hashlib.sha256()
    for chunk in iter(lambda: source.read(1024*1024), b''):
        hasher.update(chunk)
    digest=hasher.hexdigest()
print('SHA-256:',digest)
if args.expected_sha256:
    matched=hmac.compare_digest(digest,args.expected_sha256.lower())
    print('MATCH - identical bytes to the reference digest' if matched else 'MISMATCH - bytes differ from reference')
    raise SystemExit(0 if matched else 1)
print('This does not establish when, how, or whether a complete desktop was captured.')
