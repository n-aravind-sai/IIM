import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from worker.audit import verify

parser=argparse.ArgumentParser(description='Verify a signed interview audit export.')
parser.add_argument('file',type=Path)
parser.add_argument('--trusted-key',help='Independently pinned base64 Ed25519 public key')
args=parser.parse_args()
valid=verify(json.loads(args.file.read_text()),args.trusted_key)
print('VALID - '+('pinned key and event chain verified' if args.trusted_key else 'internal consistency only; source identity is not authenticated') if valid else 'INVALID - signature, chain or expected key mismatch')
raise SystemExit(0 if valid else 1)
