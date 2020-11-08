import time

from creeper.env import ENV_NO_BACKEND, PATH_PAC_TPL
from creeper.impl.win_pac_setting import set_pac_setting


with open(PATH_PAC_TPL, 'r') as f:
    _pac_template = f.read()


class PACServer:
    def __init__(self, app):
        self.app = app
        self.pac_filename = 'proxy.pac'

    def api_path(self):
        return f'/{self.pac_filename}'

    def get_script(self, host):
        script = _pac_template.replace('{{proxy}}', host)
        return 'application/x-ns-proxy-autoconfig', script

    def pac_file_url(self):
        return self.app.base_url() + '/' + self.pac_filename

    def update_sys_setting(self, enabled):
        if ENV_NO_BACKEND:
            return True

        if not enabled:
            return set_pac_setting(None, False)

        no_cache = '?no_cache=' + str(time.time())
        url = self.pac_file_url() + no_cache

        return set_pac_setting(url, True)
