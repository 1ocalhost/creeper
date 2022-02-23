import os
import sys
import hashlib
import zipfile
import urllib.request as url_req
from pathlib import Path

CUR_DIR = Path(__file__).parent
did_setup_proxy = False


def try_os_unlink(path):
    try:
        return os.unlink(path)
    except FileNotFoundError:
        pass


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

    http_proxy = os.environ.get('creeper_proxy')
    print(f'using proxy: {http_proxy}')

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


def unzip(zip_file, item_path, out_path):
    with zipfile.ZipFile(zip_file, 'r') as zip_:
        with zip_.open(item_path) as in_, open(out_path, 'wb') as out:
            while True:
                block = in_.read(1024 * 1024)
                if not block:
                    break
                out.write(block)


def uncompress(dependency, dl_path, path):
    conf = dependency.get('uncompress')
    path.unlink(missing_ok=True)

    if not conf:
        os.rename(dl_path, path)
        return

    type, item_path = conf.split('!')
    if type == 'zip':
        unzip(dl_path, item_path, path)
    else:
        raise NotImplementedError(type)


def download(dependency, path):
    assert isinstance(path, Path)
    url = dependency['download_url']
    try_setup_proxy()
    path.parent.mkdir(parents=True, exist_ok=True)

    print(f'Downloading {path} from {url}...')
    dl_path = f'{path}.downloading'

    try:
        url_req.urlretrieve(url, dl_path, _download_hook)
        uncompress(dependency, dl_path, path)
    except BaseException:
        try_os_unlink(path)
        raise
    finally:
        try_os_unlink(dl_path)

    hash_ = file_sha256sum(path)
    assert hash_
    dependency['sha256'] = hash_


def check_hash(expected, real):
    if (expected == '*'):
        return True

    return real == expected.lower()


def main():
    top_dir = Path(CUR_DIR).parent
    manifest = read_manifest()
    changed = False

    for dependency in manifest['dependencies']:
        full_path = top_dir / dependency['path']
        real_hash = file_sha256sum(full_path)
        if not check_hash(dependency['sha256'], real_hash):
            download(dependency, full_path)
            changed = True

    if changed:
        write_manifest(manifest)


if __name__ == '__main__':
    sys.path.append(str(CUR_DIR))
    from manifest import read_manifest, write_manifest
    main()
