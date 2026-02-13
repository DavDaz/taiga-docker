FROM taigaio/taiga-back:latest

# Install whitenoise for serving static files without shared volumes
RUN pip install "Django<4" whitenoise django-storages[s3] boto3 "django-grappelli>=3.0,<4.0"

# Custom config for Railway deployment
COPY config.py /taiga-back/settings/config.py
COPY urls_railway.py /taiga-back/settings/urls_railway.py

# Generate staticfiles manifest required by CompressedManifestStaticFilesStorage.
# Dummy env vars: collectstatic is a filesystem op, does not connect to the DB.
RUN cd /taiga-back && \
    DJANGO_SETTINGS_MODULE=settings.config \
    POSTGRES_HOST=localhost \
    POSTGRES_DB=taiga \
    POSTGRES_USER=taiga \
    POSTGRES_PASSWORD=taiga \
    POSTGRES_PORT=5432 \
    TAIGA_SECRET_KEY=dummy-collectstatic-build \
    python manage.py collectstatic --noinput
