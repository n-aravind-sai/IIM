import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

parser=argparse.ArgumentParser(description='Explicitly upload a completed, candidate-reviewed audit bundle.')
parser.add_argument('file',type=Path);parser.add_argument('--url',required=True)
parser.add_argument('--consent-to-upload',action='store_true');parser.add_argument('--local-dev',action='store_true')
args=parser.parse_args()
if not args.consent_to_upload:parser.error('Candidate approval is required: --consent-to-upload')
parsed=urlsplit(args.url)
if parsed.scheme!='https' and not(args.local_dev and parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')):
    parser.error('Use HTTPS; --local-dev permits HTTP only on loopback')
token=os.environ.get('REPORT_WRITE_TOKEN','')
if len(token)<32:parser.error('Set REPORT_WRITE_TOKEN in the environment')
if args.file.stat().st_size>8*1024*1024:parser.error('Report exceeds 8 MB')
data=json.dumps({'consent_to_upload':True,'bundle':json.loads(args.file.read_text())}).encode()
request=Request(args.url.rstrip('/')+'/v1/reports',data=data,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
with build_opener(NoRedirect).open(request,timeout=20) as response:print(response.read().decode())
