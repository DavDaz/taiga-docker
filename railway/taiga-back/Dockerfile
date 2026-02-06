FROM taigaio/taiga-back:latest

# Install whitenoise for serving static files without shared volumes
RUN pip install whitenoise

# Custom config for Railway deployment
COPY config.py /taiga-back/settings/config.py
COPY urls_railway.py /taiga-back/settings/urls_railway.py
