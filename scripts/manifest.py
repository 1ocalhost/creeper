import json
from pathlib import Path


def get_top_dir_path():
    cur_dir = Path(__file__).parent
    return cur_dir.parent


TOP_DIR = get_top_dir_path()
MANIFEST_FILE = TOP_DIR / 'manifest.json'
APP_CONF_FILE = TOP_DIR / 'data/conf/vendor/app_conf.json'


def read_manifest():
    with open(MANIFEST_FILE) as f:
        manifest_text = f.read(1024*1024)
        manifest = json.loads(manifest_text)

    return manifest


def write_manifest(data):
    with open(MANIFEST_FILE, 'w') as f:
        manifest_text = json.dumps(data, indent=4)
        f.write(manifest_text)


def read_app_conf():
    return json.loads(APP_CONF_FILE.read_text())
