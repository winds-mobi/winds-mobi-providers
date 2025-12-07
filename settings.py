import os

# Logging and monitoring
SENTRY_URL = os.environ.get("SENTRY_URL")
ENVIRONMENT = os.environ.get("ENVIRONMENT") or "local"

# Commons
MONGODB_URL = os.environ.get("MONGODB_URL") or "mongodb://localhost:27017/winds_mobi"
REDIS_URL = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
OPEN_ELEVATION_API_URL = os.environ.get("OPEN_ELEVATION_API_URL")

# Providers
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or "postgres://postgres:postgres@localhost:5432/winds_mobi"
BORN_TO_FLY_VENDOR_ID = os.environ.get("BORN_TO_FLY_VENDOR_ID")
BORN_TO_FLY_DEVICE_ID = os.environ.get("BORN_TO_FLY_DEVICE_ID")
FFVL_API_KEY = os.environ.get("FFVL_API_KEY")
IWEATHAR_KEY = os.environ.get("IWEATHAR_KEY")
KACHELMANN_API_KEY = os.environ.get("KACHELMANN_API_KEY")
ROMMA_KEY = os.environ.get("ROMMA_KEY")
WINDLINE_SQL_URL = os.environ.get("WINDLINE_SQL_URL")
WINDY_API_KEY = os.environ.get("WINDY_API_KEY")
