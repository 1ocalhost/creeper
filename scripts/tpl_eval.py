import os
import sys
import datetime
from pathlib import Path

CUR_DIR = Path(__file__).parent


def main():
    now = datetime.datetime.now()
    build_tag = now.strftime("%Y%m%d_%H%M")[2:]

    manifest = read_manifest()
    name = manifest['name']
    major_ver = manifest['version']
    file_name = f'{name}-{major_ver}-{build_tag}.exe'

    cmd = sys.argv[1]
    cmd = cmd.replace('{out_name}', file_name)
    exit(os.system(cmd))


if __name__ == '__main__':
    sys.path.append(str(CUR_DIR))
    from manifest import read_manifest
    main()
