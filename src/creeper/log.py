import logging
from logging.handlers import RotatingFileHandler

from creeper.env import IS_DEBUG, LOG_DIR

MODULE_NAME = 'creeper'
LOG_LEVEL = logging.DEBUG if IS_DEBUG else logging.INFO
LOG_FORMAT = '[%(asctime)s] [%(levelname)s] ' \
        '%(message)s (%(pathname)s:%(lineno)d)'


def _make_file_handler():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f'{MODULE_NAME}.log'

    handler = RotatingFileHandler(
        log_file, encoding='utf-8',
        maxBytes=2 * 1024 * 1024, backupCount=10)
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)
    handler.setLevel(LOG_LEVEL)
    return handler


def _init():
    logging.basicConfig(level=logging.CRITICAL, format=LOG_FORMAT)

    global logger
    logger = logging.getLogger(MODULE_NAME)
    logger.setLevel(LOG_LEVEL)

    if not IS_DEBUG:
        logger.addHandler(_make_file_handler())


_init()
