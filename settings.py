MONGODB_URL = 'mongodb://localhost:27017/windmobile'
REDIS_URL = 'redis://localhost:6379/0'

WINDMOBILE_LOG_DIR = None
SENTRY_URL = ''

GOOGLE_API_KEY = ''
WINDLINE_SQL_URL = ''
CHECKWX_API_KEY = ''
ROMMA_KEY = ''

try:
    from local_settings import *  # noqa
except ImportError:
    pass
