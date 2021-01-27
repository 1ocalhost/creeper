import json
from pathlib import Path


def get_manifest_file_path():
    cur_dir = Path(__file__).parent
    return cur_dir.parent / 'manifest.json'


MANIFEST_FILE = get_manifest_file_path()


def read_manifest():
    with open(MANIFEST_FILE) as f:
        manifest_text = f.read(1024*1024)
        manifest = json.loads(manifest_text)

    return manifest


def write_manifest(data):
    with open(MANIFEST_FILE, 'w') as f:
        manifest_text = json.dumps(data, indent=4)
        f.write(manifest_text)
