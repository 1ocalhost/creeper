import os
import sys
import hashlib
import urllib.request as url_req
from pathlib import Path

CUR_DIR = Path(__file__).parent

did_setup_proxy = False


def file_sha256sum(path):
    sha256 = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()
    except FileNotFoundError:
        pass


def try_setup_proxy():
    global did_setup_proxy
    if did_setup_proxy:
        return
    did_setup_proxy = True

    http_proxy = os.environ.get('http_proxy')
    print(f'env http_proxy={http_proxy}')

    if not http_proxy:
        return

    proxy = url_req.ProxyHandler({
        'http': http_proxy,
        'https': http_proxy,
    })
    opener = url_req.build_opener(proxy)
    url_req.install_opener(opener)


def _download_hook(blocknum, blocksize, totalsize):
    readsofar = blocknum * blocksize
    if totalsize > 0:
        is_done = (readsofar >= totalsize)
        if is_done:
            percent_text = '100'
        else:
            percent = readsofar * 1e2 / totalsize
            percent_text = '%.1f' % percent

        s = '\r%5s%% %*d / %d' % (
            percent_text, len(str(totalsize)), readsofar, totalsize)
        sys.stderr.write(s)
        if is_done:
            sys.stderr.write('\n')
    else:  # total size is unknown
        sys.stderr.write('read %d\n' % (readsofar,))


def download(dependency, path):
    assert isinstance(path, Path)
    url = dependency['download_url']
    try_setup_proxy()
    path.parent.mkdir(parents=True, exist_ok=True)

    print(f'Downloading {path} from {url}...')
    try:
        url_req.urlretrieve(url, path, _download_hook)
    except BaseException:
        path.unlink()
        raise

    hash_ = file_sha256sum(path)
    assert hash_
    dependency['sha256'] = hash_


def main():
    top_dir = Path(CUR_DIR).parent
    manifest = read_manifest()
    changed = False

    for dependency in manifest['dependencies']:
        full_path = top_dir / dependency['path']
        real_hash = file_sha256sum(full_path)
        if real_hash != dependency['sha256']:
            download(dependency, full_path)
            changed = True

    if changed:
        write_manifest(manifest)


if __name__ == '__main__':
    sys.path.append(str(CUR_DIR))
    from manifest import read_manifest, write_manifest
    main()
