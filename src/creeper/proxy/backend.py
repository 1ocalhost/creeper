import os
import shutil
import hashlib
import asyncio
import yaml
from tempfile import mkstemp
from subprocess import call, Popen, PIPE, CREATE_NO_WINDOW

from creeper.env import CONF_DIR, TMP_DIR, BIN_DIR, FILE_CUR_NODE_JSON
from creeper.impl.win_utils import get_win_machine_guid
from creeper.utils import split_no_empty, write_json_file

POPEN_GENERAL_PARAM = dict(
    stdout=PIPE, stderr=PIPE, creationflags=CREATE_NO_WINDOW
)


def _make_backend_uid():
    m = hashlib.md5()
    machine_guid = get_win_machine_guid()
    m.update(machine_guid.encode())
    return m.hexdigest()


_backend_uid = _make_backend_uid()


def find_listen_addr_by_pid(pid):
    process = Popen(
        'netstat -anop TCP | find "LISTENING"',
        shell=True, **POPEN_GENERAL_PARAM)
    stdout, stderr = process.communicate(timeout=5)
    if process.returncode != 0:
        raise Exception(stdout, stderr)

    result = {}
    for line in split_no_empty(stdout.decode(), '\n'):
        str_list = list(split_no_empty(line, None))
        addr, pid_ = str_list[1], str_list[-1]
        result.setdefault(pid_, []).append(addr.split(':'))

    return result.get(str(pid), [])


class BackendUtility:
    def __init__(self, exe_file, conf_file):
        self.backend_exe = exe_file
        self.backend_uid = _backend_uid
        self.backend_uid_exe = self.make_uid_exe_path()
        self.backend_uid_exe_path = TMP_DIR / self.backend_uid_exe
        self.conf_file = CONF_DIR / conf_file

    def make_uid_exe_path(self):
        name_list = self.backend_exe.split('.')
        name_list.insert(-1, 'uid-' + self.backend_uid)
        return '.'.join(name_list)

    def clear_all(self):
        CODE_OK = 0
        CODE_NOT_FOUND = 128

        name = self.backend_uid_exe
        args = ['taskkill.exe', '/F', '/IM', name]
        code = call(args, **POPEN_GENERAL_PARAM)

        if code not in [CODE_OK, CODE_NOT_FOUND]:
            raise Exception(f'clear leftover failed ({code})')

    def try_copy_uid_file(self):
        dst = self.backend_uid_exe_path
        dst.parent.mkdir(parents=True, exist_ok=True)

        if not os.path.isfile(dst):
            src = BIN_DIR / self.backend_exe
            shutil.copyfile(src, dst)

    def check(self):
        self.try_copy_uid_file()
        self.clear_all()

    def common_args(self, conf_file=None):
        if conf_file is None:
            conf_file_ = str(self.conf_file)
        else:
            conf_file_ = conf_file
        return self.backend_uid_exe_path, conf_file_

    def make_conf_data(self, data):
        return self.make_conf(data.conf)


class BackendUtilityMihomo(BackendUtility):
    def __init__(self):
        super().__init__('mihomo.exe', 'mihomo.yml')

    def make_conf(self, conf):
        node_name = 'node'
        proxy_conf = dict(conf)
        proxy_conf['name'] = node_name

        data = {
            'mixed-port': 0,
            'log-level': 'silent',
            'proxies': [proxy_conf],
            'proxy-groups': [
                {
                    'name': 'GLOBAL',
                    'type': 'select',
                    'proxies': [node_name],
                }
            ],
            'mode': 'GLOBAL'
        }

        return yaml.dump(data)

    def make_args(self, conf_file=None):
        bin_file, conf_file_ = self.common_args(conf_file)
        return [bin_file, '-f', conf_file_]


# Now switching to support Mihomo as the sole backend.
class BackendUtilitys:
    def __init__(self):
        self.utility = BackendUtilityMihomo()

    def check(self):
        self.utility.check()

    def clear_all(self):
        self.utility.clear_all()

    def guess_util(self):
        util = self.utility
        if util.conf_file.is_file():
            return util

    def get_util(self, conf=None):
        if conf is None:
            return self.guess_util()
        return self.utility

    def get_full_conf(self, conf):
        util = self.utility
        conf_data = util.make_conf_data(conf)
        return util.conf_file, conf_data

    def switch_conf_file(self, conf):
        self.utility.conf_file.unlink(True)

        write_json_file(CONF_DIR / FILE_CUR_NODE_JSON, conf)
        full_conf = self.get_full_conf(conf)
        if full_conf:
            conf_file, conf_data = full_conf
            conf_file.write_text(conf_data)

    async def restart(self, backend, conf):
        self.switch_conf_file(conf)
        if backend:
            backend.quit()
            await backend.start()


backend_utilitys = BackendUtilitys()


class Backend:
    def __init__(self):
        self.process = None
        self.host = '127.0.0.1'
        self.port = None
        self.tmp_conf_file = None
        self.backend_util = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.quit()

    def quit(self):
        self.port = None
        if not self.process:
            return

        self.process.kill()
        self.process = None
        if self.tmp_conf_file:
            os.unlink(self.tmp_conf_file)
            self.tmp_conf_file = None

    def find_listen_port(self):
        addr_list = find_listen_addr_by_pid(self.process.pid)
        if addr_list:
            _, port = addr_list[0]
            return int(port)

    async def start(self, conf=None, timeout=5):
        args = self.get_args(conf)
        if not args:
            return

        self.process = Popen(args, **POPEN_GENERAL_PARAM)
        interval = 0.5
        for i in range(int(timeout / interval)):
            self.port = self.find_listen_port()
            if self.port is not None:
                break
            await asyncio.sleep(interval)
        return

    def create_tmp_conf_file(self, conf):
        util = self.backend_util
        conf_data = util.make_conf_data(conf)
        fd, path = mkstemp(util.conf_file.suffix)
        with os.fdopen(fd, 'w') as fp:
            fp.write(conf_data)

        self.tmp_conf_file = path
        return path

    def get_args(self, conf):
        self.backend_util = backend_utilitys.get_util(conf)
        if not self.backend_util:
            return

        if conf:
            conf_file = self.create_tmp_conf_file(conf)
        else:
            conf_file = None  # default file

        return self.backend_util.make_args(conf_file)
