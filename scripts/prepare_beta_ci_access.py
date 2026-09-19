"""Give acceptance CI temporary read-only access to exact draft assets.

No repository write permission is granted to the workflow. Signed asset URLs
expire at the hosting provider and are stored only as an encrypted Actions
secret. Neither the GitHub account token nor URL values are printed.
"""
import concurrent.futures
import http.client
import json
import subprocess
from pathlib import Path

REPO = 'AureoleLab/GaussianOS'
SECRET = 'GAUSSIANOS_BETA_ASSET_URLS'

def gh(*args):
    return subprocess.check_output(['gh', *args], text=True, encoding='utf-8').strip()

def main():
    manifest = json.loads(Path('dist/runtime-manifest.json').read_text(encoding='utf-8'))
    release = json.loads(gh('api', f'repos/{REPO}/releases/383472551'))
    if not release['draft']:
        raise RuntimeError('This helper is only for unpublished acceptance artifacts')
    names = {'GaussianOS-Core-win-x64.zip', 'GaussianOS-0.1.0-beta.1-Setup-win-x64.exe'}
    for component in manifest['components']:
        if component['required'] or component['component_id'] in {'mapanything-source', 'mapanything-environment', 'dinov2-source'}:
            names.update(p['filename'] for p in component['source']['artifact']['parts'])
    assets = {a['name']: a for a in release['assets']}
    token = gh('auth', 'token')
    def sign(name):
        asset = assets[name]
        if asset['state'] != 'uploaded':
            raise RuntimeError(f'Asset is not ready: {name}')
        connection = http.client.HTTPSConnection('api.github.com', timeout=30)
        try:
            connection.request('GET', f'/repos/{REPO}/releases/assets/{asset["id"]}', headers={
                'Authorization': 'Bearer ' + token, 'Accept': 'application/octet-stream',
                'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'GaussianOS-release-acceptance'})
            response = connection.getresponse()
            location = response.getheader('Location')
            if response.status != 302 or not location or not location.startswith('https://release-assets.githubusercontent.com/'):
                raise RuntimeError(f'No read-only redirect for {name}: HTTP {response.status}')
            return {'filename': name, 'url': location}
        finally:
            connection.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        links = list(pool.map(sign, sorted(names)))
    value = json.dumps(links)
    if len(value.encode()) > 47000:
        raise RuntimeError('Signed links exceed the Actions secret size limit')
    subprocess.run(['gh', 'secret', 'set', SECRET, '--repo', REPO], input=value, text=True, check=True)
    print(f'Configured {len(links)} expiring read-only asset links for acceptance CI.')

if __name__ == '__main__':
    main()