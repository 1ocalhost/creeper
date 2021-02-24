import os
import sys
import json
import datetime
import zipfile
from pathlib import Path

CUR_DIR = Path(__file__).parent
INSTALLER_PY = 'installer.py.exe'
APP_ZIP = 'app.zip'
VERSION_FILE = 'data/html/version.json'


def write_verison_file(ver):
    ver_data = json.dumps(ver, indent=4).encode()

    with zipfile.ZipFile(APP_ZIP, 'a') as zf:
        with zf.open(VERSION_FILE, 'w') as f:
            f.write(ver_data)

    with open('../' + VERSION_FILE, 'wb') as f:
        f.write(ver_data)


def u8to16(u8):
    return b''.join([b'%c\0' % x for x in u8])


def fill_installer_ver(installer_ver):
    TPL_BUF_SIZE = 260
    assert len(installer_ver) < TPL_BUF_SIZE
    BLOCK_SIZE = 100 * 1024
    template = u8to16(b'{{app_version}}')
    padding = len(template) - 1
    offset = 0

    def overwrite(index):
        f.seek(index)
        f.write(b'\0' * TPL_BUF_SIZE)
        f.seek(index)
        ver_data = u8to16(installer_ver.encode())
        f.write(ver_data)

    with open(INSTALLER_PY, 'rb+') as f:
        while True:
            f.seek(offset)
            block = f.read(BLOCK_SIZE + padding)
            if not block:
                return False

            index = block.find(template)
            if index != -1:
                overwrite(offset + index)
                return True

            offset += len(block)


def main():
    now = datetime.datetime.now()
    build_tag = now.strftime("%Y%m%d_%H%M")[2:]

    manifest = read_manifest()
    name = manifest['name']
    major_ver = manifest['version']
    write_verison_file({
        'name': name,
        'verison': major_ver,
        'build': build_tag,
    })

    file_name = f'{name}-{major_ver}-{build_tag}.exe'
    installer_ver = f' ({major_ver}-{build_tag})'
    assert fill_installer_ver(installer_ver)

    cmd = f'{INSTALLER_PY} push {APP_ZIP} {file_name}'
    exit(os.system(cmd))


if __name__ == '__main__':
    sys.path.append(str(CUR_DIR))
    from manifest import read_manifest
    main()
