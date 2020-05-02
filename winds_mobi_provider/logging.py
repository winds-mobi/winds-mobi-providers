import logging
import logging.config
import logging.handlers
from os import path

import yaml

from settings import LOG_DIR


def get_logger(name):
    if LOG_DIR:
        with open(path.join(path.dirname(path.abspath(__file__)), 'logging_file.yml')) as f:
            dict = yaml.load(f, Loader=yaml.FullLoader)
            dict['handlers']['file']['filename'] = path.join(path.expanduser(LOG_DIR), f'{name}.log')
            logging.config.dictConfig(dict)
    else:
        with open(path.join(path.dirname(path.abspath(__file__)), 'logging_console.yml')) as f:
            logging.config.dictConfig(yaml.load(f, Loader=yaml.FullLoader))
    return logging.getLogger(name)
