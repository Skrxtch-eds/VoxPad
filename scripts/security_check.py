"""Scan tracked files and release app modules without printing matched secrets."""
import argparse
import hashlib
import json
from importlib import metadata
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen
import zipfile

from build_runtime_portable import PACKAGES
from build_windows import ROOT, version

PATTERNS = {
    'github-token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'aws-access-id': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'openai-token': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b',
    'hf-token': rb'\bhf_[A-Za-z0-9]{30,}\b',
    'credential-url': rb'https?://[^\s/:]+:[^\s/@]+@',
}


def scan(name, data):
    return [dict(file=name, kind=kind, line=data[:match.start()].count(b'\n')+1)
            for kind, pattern in PATTERNS.items() for match in re.finditer(pattern, data)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--osv', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    findings = []
    for name in filter(None, paths):
        path = ROOT/name
        if path.is_file():
            findings.extend(scan(name, path.read_bytes()))
    unwanted = []
    archive_hash = None
    dependencies = {metadata.metadata(name)['Name']: metadata.version(name) for name in PACKAGES}
    if args.archive:
        with args.archive.open('rb') as stream:
            archive_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        with zipfile.ZipFile(args.archive) as package:
            dependencies = json.loads(package.read('VoxPad/BUILD-MANIFEST.json'))['dependencies']
            for name in package.namelist():
                basename = name.rsplit('/', 1)[-1]
                if ('/data/' in name or basename.startswith('.env') or
                        basename in ('settings.json', 'history.json', 'smoke-test.json') or
                        name.endswith(('.sqlite', '.sqlite3', '.db', '.raw', '.pem', '.key', '.pfx', '.p12'))):
                    unwanted.append(name)
                if 'codex' in name.lower():
                    unwanted.append(name)
                if name.startswith('VoxPad/app/') and name.endswith(('.py', '.qml', '.json', '.txt', '.md', '.ini', '.yml')):
                    findings.extend(scan(name, package.read(name)))
    queries = [dict(package=dict(name=name, ecosystem='PyPI'), version=value)
               for name, value in dependencies.items()]
    advisories = []
    if args.osv:
        request = Request('https://api.osv.dev/v1/querybatch',
                          data=json.dumps(dict(queries=queries)).encode(),
                          headers={'Content-Type': 'application/json', 'User-Agent': 'VoxPad-security-check'})
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
        for query, value in zip(queries, result['results']):
            if value.get('next_page_token'):
                raise RuntimeError('OSV results incomplete. Inspect pagination before publishing.')
            if value.get('vulns'):
                advisories.append(dict(package=query, vulnerabilities=value['vulns']))
    report = dict(version=version(), secret_findings=findings, unwanted_archive_files=unwanted,
                  archive_sha256=archive_hash, dependencies=queries, osv_checked=args.osv,
                  dependency_advisories=advisories)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(findings or unwanted or advisories))


if __name__ == '__main__':
    raise SystemExit(main())
