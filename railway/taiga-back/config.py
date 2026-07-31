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

from whitenoise.storage import CompressedManifestStaticFilesStorage as _WhiteNoiseManifestStorage

class _LaxManifestStorage(_WhiteNoiseManifestStorage):
    """manifest_strict=False: archivos ausentes del manifest devuelven URL cruda en vez de ValueError."""
    manifest_strict = False

STATICFILES_STORAGE = "settings.config._LaxManifestStorage"
STATIC_URL = "/static/"

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
# Media files - Cloudflare R2 (if R2_ACCESS_KEY_ID defined) or filesystem
# --------------------------------------------------------------------------
if os.getenv("R2_ACCESS_KEY_ID"):
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

    AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
    AWS_S3_REGION_NAME = "auto"
    AWS_DEFAULT_ACL = None          # R2 uses bucket-level public access
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_QUERYSTRING_AUTH = False    # Public URLs without signing
    AWS_S3_FILE_OVERWRITE = True    # Overwrite thumbnails on re-upload

    _r2_public_url = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
    AWS_S3_CUSTOM_DOMAIN = _r2_public_url.replace("https://", "").replace("http://", "")
    MEDIA_URL = f"{_r2_public_url}/"
    MEDIA_ROOT = ""
else:
    # Fallback: local filesystem (ephemeral, files lost on redeploy)
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    MEDIA_URL = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")

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
EMAIL_TIMEOUT = 15  # seconds — prevents worker from hanging on SMTP connect

# --------------------------------------------------------------------------
# Telemetry
# --------------------------------------------------------------------------
ENABLE_TELEMETRY = os.getenv("ENABLE_TELEMETRY", "True") == "True"

# --------------------------------------------------------------------------
# Public registration
# --------------------------------------------------------------------------
PUBLIC_REGISTER_ENABLED = os.getenv("PUBLIC_REGISTER_ENABLED", "True") == "True"

# --------------------------------------------------------------------------
# Django Grappelli - modern admin skin (replaces templates, no permission hooks)
# --------------------------------------------------------------------------
INSTALLED_APPS = ["grappelli", "taiga_railway"] + list(INSTALLED_APPS)
GRAPPELLI_ADMIN_TITLE = "Taiga Admin"
