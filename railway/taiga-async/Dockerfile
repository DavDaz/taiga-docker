FROM taigaio/taiga-back:latest

# Install whitenoise (same config as taiga-back)
RUN pip install whitenoise

# Custom config for Railway deployment (shared with taiga-back)
COPY config.py /taiga-back/settings/config.py
COPY urls_railway.py /taiga-back/settings/urls_railway.py

# Celery async worker entrypoint
ENTRYPOINT ["/taiga-back/docker/async_entrypoint.sh"]
