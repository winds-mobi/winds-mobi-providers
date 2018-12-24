MONGODB_URL = 'mongodb://localhost:27017/windmobile'

REDIS_URL = 'redis://localhost:6379/0'

WINDMOBILE_LOG_DIR = None

GOOGLE_API_KEY = ''

WINDLINE_URL = ''

CHECKWX_API_KEY = ''

SENTRY_URL = ''

try:
    from local_settings import *  # noqa
except ImportError:
    pass
