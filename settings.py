import os

# COMMONS
MONGODB_URL = os.environ.get("MONGODB_URL") or "mongodb://localhost:27017/winds_mobi"
REDIS_URL = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Logging and monitoring
SENTRY_URL = os.environ.get("SENTRY_URL")
ENVIRONMENT = os.environ.get("ENVIRONMENT") or "development"

# PROVIDERS
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or "postgres://postgres:postgres@localhost:5432/winds_mobi"

# Windline
WINDLINE_SQL_URL = os.environ.get("WINDLINE_SQL_URL")

# METAR
CHECKWX_API_KEY = os.environ.get("CHECKWX_API_KEY")

# Romma
ROMMA_KEY = os.environ.get("ROMMA_KEY")

# iWeathar
IWEATHAR_KEY = os.environ.get("IWEATHAR_KEY")

# BornToFly
BORN_TO_FLY_VENDOR_ID = os.environ.get("BORN_TO_FLY_VENDOR_ID")
BORN_TO_FLY_DEVICE_ID = os.environ.get("BORN_TO_FLY_DEVICE_ID")
