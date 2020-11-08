import time
from creeper.env import APP_NAME
from threading import Thread


def check_update(tray_icon):
    def worker():
        time.sleep(1)
        msg = f'{APP_NAME} updated! '
        tray_icon.sys_notify(APP_NAME, msg, 'info')

    if False:
        Thread(target=worker).start()
