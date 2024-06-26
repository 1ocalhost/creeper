import os
import json
import shutil
import hashlib
import asyncio
from tempfile import mkstemp
from subprocess import call, Popen, PIPE, CREATE_NO_WINDOW

from creeper.env import CONF_DIR, TMP_DIR, BIN_DIR, FILE_CUR_NODE_JSON
from creeper.impl.win_utils import get_win_machine_guid
from creeper.utils import AttrDict, \
    split_no_empty, run_async, write_json_file

POPEN_GENERAL_PARAM = dict(
    stdout=PIPE, stderr=PIPE, creationflags=CREATE_NO_WINDOW
)

BACKEND_LOCAL_ADDR = '127.0.0.2'


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


class BackendUtilitySSLike(BackendUtility):
    def __init__(self, *args):
        super().__init__(*args)

    def make_conf_data(self, data):
        return {
            **data.conf,
            'timeout': 300,
        }

    def make_args(self, conf_file=None):
        bin_file, conf_file_ = self.common_args(conf_file)
        return [
            bin_file,
            '-c', conf_file_,
            '-b', BACKEND_LOCAL_ADDR,
            '-l', '0',
        ]


class BackendUtilitySS(BackendUtilitySSLike):
    def __init__(self):
        super().__init__('sswin.exe', 'ss.json')


class BackendUtilitySSR(BackendUtilitySSLike):
    def __init__(self):
        super().__init__('ssrwin.exe', 'ssr.json')


class BackendUtilityV2Ray(BackendUtility):
    INBOUND = {
        'port': 0,
        'listen': BACKEND_LOCAL_ADDR,
        'protocol': 'socks'
    }

    def __init__(self):
        super().__init__('v2ray.exe', 'vmess.json')

    def _stream_setting(self, data):
        result = {'network': data.net}
        if data.net == 'tcp':
            pass
        elif data.net == 'ws':
            result['wsSettings'] = {
                'connectionReuse': True,
                'path': data.path,
                'headers': {
                    'Host': data.host
                }
            }
        elif data.net == 'h2':
            result['httpSettings'] = {
                'path': data.path,
                'host': [data.host],
            }
        else:
            raise TypeError(f'unsupported type: {data.net}')

        if data.tls == 'tls':
            tls_settings = {'allowInsecure': True}
            if data.host:
                tls_settings['serverName'] = data.host

            result['security'] = 'tls'
            result['tlsSettings'] = tls_settings

        return result

    def make_conf_data(self, data):
        data = AttrDict(data.conf)
        user = {
            'id': data.id,
            'alterId': int(data.aid),
            'security': 'auto',
            'level': 0
        }

        outbound = {
            'protocol': 'vmess',
            'settings': {
                'vnext': [{
                    'address': data.add,
                    'port': int(data.port),
                    'users': [user]
                }]
            },
            'streamSettings': self._stream_setting(data)
        }

        return {
            'inbounds': [self.INBOUND],
            'outbounds': [outbound],
        }

    def make_args(self, conf_file=None):
        bin_file, conf_file_ = self.common_args(conf_file)
        return [bin_file, '-c', conf_file_]


class BackendUtilitys:
    def __init__(self):
        self.utilitys = {
            'ss': BackendUtilitySS(),
            'ssr': BackendUtilitySSR(),
            'vmess': BackendUtilityV2Ray(),
        }

    def check(self):
        for util in self.utilitys.values():
            util.check()

    def clear_all(self):
        for util in self.utilitys.values():
            util.clear_all()

    def bin_args(self, type_, conf_file):
        util = self.utilitys[type_]
        bin_file = util.backend_uid_exe_path
        return util.build_args(bin_file, conf_file)

    def guess_util(self):
        for util in self.utilitys.values():
            if util.conf_file.is_file():
                return util

    def get_util(self, conf=None):
        if conf is None:
            return self.guess_util()
        return self.utilitys[conf.type]

    def get_full_conf(self, conf):
        for type_, util in self.utilitys.items():
            if type_ == conf.type:
                conf_data = util.make_conf_data(conf)
                return util.conf_file, conf_data

    def switch_conf_file(self, conf):
        for util in self.utilitys.values():
            util.conf_file.unlink(True)

        write_json_file(CONF_DIR / FILE_CUR_NODE_JSON, conf)
        full_conf = self.get_full_conf(conf)
        if full_conf:
            conf_file, conf_data = full_conf
            write_json_file(conf_file, conf_data)

    async def restart(self, backend, conf):
        self.switch_conf_file(conf)
        if backend:
            backend.quit()
            await backend.start_async()


backend_utilitys = BackendUtilitys()


class Backend:
    def __init__(self):
        self.process = None
        self.host = BACKEND_LOCAL_ADDR
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

    def start(self, **kwargs):
        return run_async(self.start_async(**kwargs))

    def find_listen_port(self):
        addr_list = find_listen_addr_by_pid(self.process.pid)
        for host, port in addr_list:
            if host == self.host:
                return port

    async def start_async(self, conf=None, timeout=5):
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
        conf_data = self.backend_util.make_conf_data(conf)
        fd, path = mkstemp('.json')
        with os.fdopen(fd, 'w') as fp:
            fp.write(json.dumps(conf_data, indent=4))

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
