FROM taigaio/taiga-front:latest

# Disable WebSocket events (taiga-events not deployed)
# This script runs after conf.json is generated from env vars
COPY 99-disable-events.sh /docker-entrypoint.d/99-disable-events.sh
RUN chmod +x /docker-entrypoint.d/99-disable-events.sh
