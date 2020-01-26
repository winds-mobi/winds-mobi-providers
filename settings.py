import os

# COMMONS
MONGODB_URL = os.environ.get('MONGODB_URL') or 'mongodb://localhost:27017/winds_mobi'
REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY') or ''  # Mandatory to run any provider

# Logging and monitoring
LOG_DIR = os.environ.get('LOG_DIR')
SENTRY_URL = os.environ.get('SENTRY_URL')
ENVIRONMENT = os.environ.get('ENVIRONMENT') or 'development'

# PROVIDERS
# JDC
JDC_IMAP_SERVER = os.environ.get('JDC_IMAP_SERVER') or ''
JDC_IMAP_USERNAME = os.environ.get('JDC_IMAP_USERNAME') or ''
JDC_IMAP_PASSWORD = os.environ.get('JDC_IMAP_PASSWORD') or ''
JDC_DELETE_EMAILS = os.environ.get('JDC_DELETE_EMAILS', 'false').lower() in ['true', '1']
JDC_PHP_PATH = os.environ.get('JDC_PHP_PATH') or 'php'
JDC_ADMIN_DB_URL = os.environ.get('JDC_ADMIN_DB_URL') or 'postgres://postgres:postgres@localhost:5432/winds_mobi'

# Windline
WINDLINE_SQL_URL = os.environ.get('WINDLINE_SQL_URL') or ''

# METAR
CHECKWX_API_KEY = os.environ.get('CHECKWX_API_KEY') or ''

# Romma
ROMMA_KEY = os.environ.get('ROMMA_KEY') or ''

# iWeathar
IWEATHAR_KEY = os.environ.get('IWEATHAR_KEY') or ''

try:
    from local_settings import *  # noqa
except ImportError:
    pass
