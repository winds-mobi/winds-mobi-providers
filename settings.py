MONGODB_URL = 'mongodb://localhost:27017/windmobile'
REDIS_URL = 'redis://localhost:6379/0'

LOG_DIR = None
SENTRY_URL = ''

GOOGLE_API_KEY = ''
CHECKWX_API_KEY = ''
ROMMA_KEY = ''

WINDLINE_SQL_URL = ''

JDC_IMAP_SERVER = ''
JDC_IMAP_USERNAME = ''
JDC_IMAP_PASSWORD = ''
JDC_DELETE_EMAILS = False
JDC_PHP_PATH = 'php'

try:
    from local_settings import *  # noqa
except ImportError:
    pass
