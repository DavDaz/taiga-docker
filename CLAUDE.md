# CLAUDE.md

This file provides guidance to Claude Code instances working in this repository.

## Repository Overview

This repository provides Docker deployment configurations for **Taiga v6.9.0**, an open-source project management platform. It supports two distinct deployment modes:

- **Standard Docker Compose**: Full-featured deployment with 9 services
- **Railway Cloud**: Optimized deployment with 4 services for Railway platform

## Architecture

### Standard Docker Compose (9 services)

```
taiga-gateway (nginx:9000)
    ├─> taiga-front
    ├─> taiga-back
    ├─> taiga-events
    └─> taiga-protected

Supporting services:
    - taiga-db (PostgreSQL)
    - taiga-async-rabbitmq
    - taiga-events-rabbitmq
    - taiga-async (Celery worker)
```

**Key characteristics:**
- Routing via taiga-gateway (nginx on port 9000)
- Shared volumes for static/media files between services
- Full feature set including async tasks and real-time events

### Railway Deployment (4 services)

```
taiga-gateway
    ├─> taiga-front
    └─> taiga-back

    Managed Postgres (Railway service)
```

**Critical constraints:**
- **No shared volumes** between Railway services
- Services removed: taiga-events, taiga-protected, taiga-async, both RabbitMQ instances

**Solutions implemented:**
- **WhiteNoise middleware**: Serves static files directly from taiga-back
- **Django serve view**: Custom endpoint for media files
- **Custom config.py**: Overrides database connection, disables Celery, configures static/media serving
- **PostgreSQL events backend**: Replaces RabbitMQ for events

## Essential Commands

### Standard Docker Compose

```bash
./launch-taiga.sh                    # Start all services
./taiga-manage.sh createsuperuser    # Create admin user
./taiga-manage.sh [COMMAND]          # Run Django management commands
docker compose down                  # Stop services
```

### Railway Deployment

```bash
# Deploy services (CRITICAL: --path-as-root required)
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d

# Domain management
railway domain --service taiga-gateway

# Variable updates
railway variables --set "KEY=VALUE" --service SERVICE_NAME

# ALWAYS restart gateway after redeploying back/front
railway service restart --service taiga-gateway --yes

# Create superuser
railway ssh --service taiga-back -- python /taiga-back/manage.py createsuperuser
```

## Configuration Files

### Standard Deployment

- **`.env`**: Main configuration (database, URLs, email, RabbitMQ, security)
- **`docker-compose.yml`**: Full 9-service orchestration
- **`docker-compose-inits.yml`**: Management commands service
- Optional: Custom `config.py` and `conf.json` for advanced configuration

### Railway Deployment

**CRITICAL FILES:**

- **`railway/taiga-back/config.py`**:
  - Overrides database connection (uses Railway DATABASE_URL)
  - Disables Celery completely
  - Configures WhiteNoise for static files
  - Uses PostgreSQL for events backend
  - **This file is MANDATORY** - common.py hardcodes localhost database

- **`railway/taiga-back/urls_railway.py`**:
  - Adds media serving endpoint (`/media/<path>`)

- **`railway/taiga-front/99-disable-events.sh`**:
  - Disables WebSocket connections (no taiga-events service)

- **`railway/taiga-gateway/taiga.conf.template`**:
  - Uses Railway's `${PORT}` variable
  - Uses `.railway.internal` DNS for service discovery

## Critical Railway Patterns

### Database Configuration

**MUST use TCP proxy host**, NOT `.railway.internal`:
```python
# In Railway variables:
DATABASE_URL = "postgresql://user:pass@trolley.proxy.rlwy.net:53109/railway"
```

The `config.py` database override is **MANDATORY** because Taiga's `common.py` hardcodes `127.0.0.1`.

### Celery Disabled

```python
CELERY_ENABLED = False
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
```

Without this, requests timeout trying to connect to `localhost:5672` (non-existent RabbitMQ).

### Events via PostgreSQL

```python
EVENTS_PUSH_BACKEND = "taiga.events.backends.postgresql.EventsPushBackend"
```

Use full `"postgresql"` module name, NOT `"pg"`.

### Gateway Restart Rule

**After ANY redeploy of taiga-back or taiga-front:**
```bash
railway service restart --service taiga-gateway --yes
```

Nginx caches upstream IPs at startup. Without restart, it sends traffic to old IPs → **504 errors**.

### Variable Synchronization

`TAIGA_SITES_DOMAIN` (taiga-back) and `TAIGA_URL` (taiga-front) **MUST match** the actual domain, or Taiga shows generic error page.

Example:
```bash
railway variables --set "TAIGA_SITES_DOMAIN=taiga.example.com" --service taiga-back
railway variables --set "TAIGA_URL=https://taiga.example.com" --service taiga-front
```

## File Structure

### Critical Files

- **`launch-taiga.sh`**: Entry point for standard deployment
- **`taiga-manage.sh`**: Django management command wrapper
- **`railway/taiga-back/config.py`**: Most critical Railway file
- **`railway/taiga-back/urls_railway.py`**: Custom URL routing for media
- **`railway/taiga-gateway/taiga.conf.template`**: Nginx configuration with Railway variables
- **`README.md`**: Comprehensive standard deployment guide
- **`railway/DEPLOY_GUIDE.md`**: Complete Railway deployment walkthrough (Spanish)

### Documentation

- README covers all standard deployment scenarios
- Railway guide contains detailed troubleshooting
- No existing cursor rules, copilot instructions, or AI-specific files

## Development Notes

- This is an **infrastructure/configuration repository**, not application code
- No testing framework, linting, or CI/CD pipelines
- Uses pre-built `taigaio/*` Docker images from Docker Hub
- Follows conventional commits format
- Contributions managed via GitHub issues and PRs
- Taiga application code lives at https://github.com/taigaio/taiga
- Translations handled via Weblate (don't PR translation files except `-en.json`)

## Common Pitfalls

1. **Railway Database Connection**: Always use TCP proxy host, never `.railway.internal` DNS
2. **Gateway Not Restarting**: After back/front redeploy, gateway MUST be restarted manually
3. **Domain Mismatch**: TAIGA_SITES_DOMAIN and TAIGA_URL must match actual domain exactly
4. **Missing --path-as-root**: Railway deploys fail without this flag
5. **Celery Not Disabled**: Backend hangs on requests if Celery settings aren't overridden
6. **Events Backend Wrong**: Use `"postgresql"` not `"pg"` for events backend
7. **Django Admin CSS Missing**: `common.py` sets `STATIC_URL` to an absolute URL with hostname. WhiteNoise needs a relative path to intercept `/static/...` requests. Without `STATIC_URL = "/static/"` in `config.py`, the admin loads HTML but returns 404 for all CSS/JS. Fix: `config.py` must have `STATIC_URL = "/static/"` after `STATICFILES_STORAGE`.
