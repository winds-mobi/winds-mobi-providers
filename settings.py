# COMMONS
MONGODB_URL = 'mongodb://localhost:27017/winds_mobi'
REDIS_URL = 'redis://localhost:6379/0'
GOOGLE_API_KEY = ''  # Mandatory to run any provider

# Logging and monitoring
LOG_DIR = None
SENTRY_URL = ''
ENVIRONMENT = 'development'

# PROVIDERS
# JDC
JDC_IMAP_SERVER = ''
JDC_IMAP_USERNAME = ''
JDC_IMAP_PASSWORD = ''
JDC_DELETE_EMAILS = False
JDC_PHP_PATH = 'php'
JDC_ADMIN_DB_URL = 'postgres://postgres:postgres@localhost:5432/winds_mobi'

# Windline
WINDLINE_SQL_URL = ''

# METAR
CHECKWX_API_KEY = ''

# Romma
ROMMA_KEY = ''

# iWeathar
IWEATHAR_KEY = ''

try:
    from local_settings import *  # noqa
except ImportError:
    pass
