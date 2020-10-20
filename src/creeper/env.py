import os
import json
from pathlib import Path
from types import SimpleNamespace


def env_get_bool(name):
    value = os.environ.get(name)
    try:
        int_value = int(value)
        return bool(int_value)
    except ValueError:
        return bool(value)
    except Exception:
        return False


def _get_main_dir():
    import __main__
    return Path(__main__.__file__).parent


def _load_conf(conf_file, allow_not_found):
    try:
        with open(conf_file) as f:
            data = f.read(1024 * 1024)
            return json.loads(data)
    except FileNotFoundError:
        if allow_not_found:
            return {}
        raise


class ConfMapping(SimpleNamespace):
    def __init__(self, filepath):
        conf = _load_conf(filepath, True)
        super().__init__(filepath=filepath, conf=conf)

    def __getitem__(self, key):
        return self.__getattr__(key)

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getattr__(self, key):
        return self.conf.get(key)

    def __setattr__(self, key, value):
        new_conf = self.conf
        new_conf[key] = value

        with open(self.filepath, 'w') as f:
            f.write(json.dumps(new_conf))
        super().__setattr__('conf', new_conf)


APP_NAME = 'Creeper'

ENV_NO_BACKEND = env_get_bool('CREEPER_NO_BACKEND')
IS_DEBUG = env_get_bool('CREEPER_DBG_MODE')

MAIN_DIR = _get_main_dir()
APP_DIR = MAIN_DIR.parent

_DATA_DIR = APP_DIR / 'data'
HTML_DIR = _DATA_DIR / 'html'
ICON_DIR = _DATA_DIR / 'icons'
BIN_DIR = _DATA_DIR / 'bin'
TMP_DIR = _DATA_DIR / 'tmp'
LOG_DIR = _DATA_DIR / 'log'

_CONF_ROOT_DIR = _DATA_DIR / 'conf'
CONF_DIR = _CONF_ROOT_DIR / 'user'
CONF_VENDOR_DIR = _CONF_ROOT_DIR / 'vendor'

PATH_CNIP_DB = CONF_VENDOR_DIR / 'cn_ip.txt'
PATH_PAC_TPL = CONF_VENDOR_DIR / 'pac.js'
PATH_APP_CONF = CONF_VENDOR_DIR / 'app_conf.json'

FILE_FEED_JSON = 'feed.json'
FILE_SPEED_JSON = 'speed.json'
FILE_CUR_NODE_JSON = 'cur_node.json'

APP_CONF = _load_conf(PATH_APP_CONF, False)
USER_CONF = ConfMapping(CONF_DIR / 'user_conf.json')
