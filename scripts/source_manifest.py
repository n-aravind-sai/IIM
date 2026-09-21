"""Verify release bytes, or regenerate the manifest from tracked source files."""
import hashlib
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
manifest = root / 'SOURCE-SHA256.txt'

def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if '--write' in sys.argv:
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    rows = [f'{checksum(root / name)}  {name}' for name in sorted(names)
            if name and name != manifest.name]
    manifest.write_text('\n'.join(rows) + '\n')
else:
    failures = []
    rows = manifest.read_text().splitlines()
    for row in rows:
        expected, name = row.split('  ', 1)
        path = root / name
        if not path.is_file() or checksum(path) != expected:
            failures.append(name)
    if failures:
        raise SystemExit('Checksum mismatch: ' + ', '.join(failures))
    print(f'Verified {len(rows)} source checksums')
