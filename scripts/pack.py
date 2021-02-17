import os
import sys
import json
import datetime
import zipfile
from pathlib import Path

CUR_DIR = Path(__file__).parent
APP_ZIP = 'app.zip'
VERSION_FILE = 'data/html/version.json'


def write_verison(ver):
    ver_data = json.dumps(ver, indent=4).encode()

    with zipfile.ZipFile(APP_ZIP, 'a') as zf:
        with zf.open(VERSION_FILE, 'w') as f:
            f.write(ver_data)

    with open('../' + VERSION_FILE, 'wb') as f:
        f.write(ver_data)


def main():
    now = datetime.datetime.now()
    build_tag = now.strftime("%Y%m%d_%H%M")[2:]

    manifest = read_manifest()
    name = manifest['name']
    major_ver = manifest['version']
    write_verison({
        'name': name,
        'verison': major_ver,
        'build': build_tag,
    })

    file_name = f'{name}-{major_ver}-{build_tag}.exe'
    cmd = f'installer.py.exe push {APP_ZIP} {file_name}'
    exit(os.system(cmd))


if __name__ == '__main__':
    sys.path.append(str(CUR_DIR))
    from manifest import read_manifest
    main()
