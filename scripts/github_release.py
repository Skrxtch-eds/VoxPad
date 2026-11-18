"""Publish verified release assets using the existing Git credential manager session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from build_windows import ROOT, version

REPOSITORY = 'Skrxtch-eds/VoxPad'


def github_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc not in ('api.github.com', 'uploads.github.com'):
        raise ValueError('GitHub credentials may only be sent to the GitHub API.')
    return url


class GitHubRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        github_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(method, path, payload=None, binary=None):
    url = github_url('https://api.github.com/repos/' + REPOSITORY + path
                     if not path or path.startswith('/') else path)
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, check=True, env=environment)
    credential = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    headers = {'Authorization': 'Bearer ' + credential['password'], 'User-Agent': 'VoxPad-release',
               'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    if binary:
        data = binary.read_bytes()
        headers['Content-Type'] = 'application/octet-stream'
    with build_opener(GitHubRedirects()).open(Request(url, data=data, headers=headers, method=method), timeout=600) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, help='Verified commit SHA')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    release = version()
    tag = 'v' + release
    body = (ROOT/'docs/releases'/f'{release}.md').read_text('utf-8')
    entry = next((item for item in request('GET', '/releases') if item['tag_name'] == tag), None)
    if entry is None:
        entry = request('POST', '/releases', dict(tag_name=tag, target_commitish=args.target,
                        name='VoxPad ' + release, body=body, draft=True))
    if not entry['draft']:
        raise SystemExit('Release already published. Refusing to replace public assets.')
    existing = {asset['name']: asset for asset in entry['assets']}
    assets = [ROOT/'outputs'/f'VoxPad-{release}-Setup-x64.exe',
              ROOT/'outputs'/f'VoxPad-{release}-Windows-x64-runtime.zip']
    for asset in [item for path in assets for item in (path, path.with_suffix(path.suffix+'.sha256'))]:
        if asset.name in existing:
            with asset.open('rb') as stream:
                digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
            if existing[asset.name].get('digest') != digest:
                raise SystemExit('Draft asset differs or lacks a digest. Inspect before retry: ' + asset.name)
            continue
        print('Uploading ' + asset.name, flush=True)
        request('POST', entry['upload_url'].split('{')[0] + '?name=' + asset.name, binary=asset)
    if args.publish:
        entry = request('PATCH', '/releases/' + str(entry['id']),
                        dict(draft=False, body=body, make_latest='true', target_commitish=args.target))
    print(entry['html_url'], flush=True)


if __name__ == '__main__':
    main()
