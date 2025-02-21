from logging.config import dictConfig
from pathlib import Path

import sentry_sdk
import yaml

from settings import ENVIRONMENT, SENTRY_URL

HERE = Path(__file__).parents[0]


def configure_logging():
    with open(Path(HERE, "logging.yml"), "r") as file:
        dictConfig(yaml.load(file, Loader=yaml.FullLoader))
    sentry_sdk.init(SENTRY_URL, environment=ENVIRONMENT)
