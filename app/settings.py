from datetime import datetime, timedelta

from environs import Env

env = Env()
env.read_env()

# --- Flask configurations ---
# Flask environment.
ENV = env("FLASK_ENV")

# Enable/disable Flask debug mode.
DEBUG = env.bool("DEBUG", ENV == "development")

# (REQUIRED) The server name, e.g. my-app.isotammi.fi
SERVER_NAME = env("SERVER_NAME")

# (REQUIRED) Flask's secret key.
# NOTE: NEVER, EVER ADD THIS KEY IN THIS FILE OR COMMIT IT IN TO THE REPOSITORY.
SECRET_KEY = env.str("SECRET_KEY")
# ----------------------------

# --- Eloqua configurations ---
# Eloqua OAuth 2.0 authorization endpoint.
ELOQUA_ENDPOINT_AUTH = "https://login.eloqua.com/auth/oauth2/authorize"

# Eloqua OAuth 2.0 token endpoint.
ELOQUA_ENDPOINT_TOKEN = "https://login.eloqua.com/auth/oauth2/token"

# Eloqua ID endpoint.
ELOQUA_ENDPOINT_ID = "https://login.eloqua.com/id"
# -----------------------------

# --- Cloud app configurations ---
with env.prefixed("CLOUD_APP_"):
    # (REQUIRED) The cloud app's client ID. Found in Eloqua AppCloud Developer tool.
    CLOUD_APP_CLIENT_ID = env("CLIENT_ID")

    # (REQUIRED) The cloud app's client secret. Found in Eloqua AppCloud Developer tool.
    # NOTE: NEVER, EVER ADD THIS KEY IN THIS FILE OR COMMIT IT IN TO THE REPOSITORY.
    CLOUD_APP_CLIENT_SECRET = env("CLIENT_SECRET")

    # The "friendly" name for the cloud app. Mostly for the viewers' pleasure.
    CLOUD_APP_FRIENDLY_NAME = env("FRIENDLY_NAME")


# The MongoDB database name.
CLOUD_APP_DB_NAME = "visma-qondor-integration"

# Debug data dump TTL.
CLOUD_APP_DB_DATA_DUMP_TTL = timedelta(weeks=1).total_seconds()
CLOUD_APP_DB_SERVICE_LOG_TTL = timedelta(days=30).total_seconds()
# --------------------------------

# --- Other configurations ---

# The logging configuration file to use. The file needs to be a YAML file.
LOGGING_CONFIG = "logging.yaml"
# ----------------------------

# Add your configurations under here
QONDOR_PRIMARY_KEY = env("QONDOR_PRIMARY_KEY")

DB_CONNECTION_STRING = env("DB_CONNECTION_STRING")