# Railway-specific configuration for taiga-back
# This file overrides default settings for Railway deployment

from .common import *  # noqa

import os

# --------------------------------------------------------------------------
# Database - override common.py hardcoded 127.0.0.1 with env vars
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "OPTIONS": {"sslmode": os.getenv("POSTGRES_SSLMODE", "disable")},
        "DISABLE_SERVER_SIDE_CURSORS": os.getenv("POSTGRES_DISABLE_SERVER_SIDE_CURSORS", "False") == "True",
    }
}

# --------------------------------------------------------------------------
# WhiteNoise - serve static files directly from Django
# --------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
] + [m for m in MIDDLEWARE if m not in (
    "django.middleware.security.SecurityMiddleware",
)]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --------------------------------------------------------------------------
# URL configuration - use custom urls that include media serving
# --------------------------------------------------------------------------
ROOT_URLCONF = "settings.urls_railway"

# --------------------------------------------------------------------------
# Events & Celery - DISABLED (no RabbitMQ/taiga-events in minimal deploy)
# --------------------------------------------------------------------------
EVENTS_PUSH_BACKEND = "taiga.events.backends.postgresql.EventsPushBackend"
CELERY_ENABLED = False

# Override Celery broker from common.py (default points to localhost:5672)
CELERY_BROKER_URL = "memory://"
BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# --------------------------------------------------------------------------
# Media files - served by Django in Railway (no shared volumes)
# --------------------------------------------------------------------------
MEDIA_URL = "/media/"

# --------------------------------------------------------------------------
# Disable protected media (no taiga-protected service)
# --------------------------------------------------------------------------
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# --------------------------------------------------------------------------
# Taiga settings from env vars (same as official docker/config.py)
# --------------------------------------------------------------------------
SECRET_KEY = os.getenv("TAIGA_SECRET_KEY")

TAIGA_SITES_SCHEME = os.getenv("TAIGA_SITES_SCHEME", "https")
TAIGA_SITES_DOMAIN = os.getenv("TAIGA_SITES_DOMAIN", "localhost")
FORCE_SCRIPT_NAME = os.getenv("TAIGA_SUBPATH", "")

SITES = {
    "api": {"scheme": TAIGA_SITES_SCHEME, "domain": TAIGA_SITES_DOMAIN, "name": "api"},
    "front": {"scheme": TAIGA_SITES_SCHEME, "domain": f"{TAIGA_SITES_DOMAIN}{FORCE_SCRIPT_NAME}"},
}

# Allow Railway domain
ALLOWED_HOSTS = ["*"]

# --------------------------------------------------------------------------
# Email settings from env vars
# --------------------------------------------------------------------------
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "system@taiga.io")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False") == "True"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

# --------------------------------------------------------------------------
# Telemetry
# --------------------------------------------------------------------------
ENABLE_TELEMETRY = os.getenv("ENABLE_TELEMETRY", "True") == "True"
