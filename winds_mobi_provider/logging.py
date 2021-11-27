import logging
from logging.config import dictConfig
from pathlib import Path

import yaml

HERE = Path(__file__).parents[0]


def configure_logger(name):
    with open(Path(HERE, "logging.yml"), "r") as file:
        dictConfig(yaml.load(file, Loader=yaml.FullLoader))
    return logging.getLogger(name)
