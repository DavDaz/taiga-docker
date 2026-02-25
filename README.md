# Taiga on Railway

Deployment configuration for **Taiga v6.9.0** on [Railway](https://railway.app).
This repo contains Docker configurations and Django overrides to run Taiga in a Railway cloud environment.

Taiga application source lives at https://github.com/taigaio/taiga.

![Taiga screenshot](imgs/taiga.jpg)

---

## Architecture

```
taiga-gateway (nginx)
    ├── taiga-front   (Angular SPA)
    └── taiga-back    (Django REST API)
         └── Managed PostgreSQL (Railway)
```

**Key design decisions vs. standard Docker Compose:**
- No shared volumes between services → WhiteNoise serves static files, Django serves media
- No RabbitMQ → PostgreSQL used as events backend
- No taiga-events service → WebSocket disabled in frontend
- Celery disabled in `taiga-back` (tasks run eagerly in-process)
- Optional Celery via `taiga-async` service if async task processing is needed

---

## Services

| Service | Image | Role |
|---|---|---|
| `taiga-gateway` | `nginx:1.19-alpine` (custom) | Reverse proxy, routes traffic |
| `taiga-back` | `taigaio/taiga-back:latest` (custom) | Django REST API + static/media serving |
| `taiga-front` | `taigaio/taiga-front:latest` (custom) | Angular SPA |
| `taiga-async` | `taigaio/taiga-back:latest` (custom) | Optional Celery worker |

---

## Deploy

> **CRITICAL**: `--path-as-root` is required on every `railway up` command.

```bash
# Deploy backend
railway up --service taiga-back --path-as-root railway/taiga-back -d

# Deploy frontend
railway up --service taiga-front --path-as-root railway/taiga-front -d

# Deploy gateway
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d

# ALWAYS restart gateway after redeploying back or front
# (nginx caches upstream IPs at startup → 504 errors without this)
railway service restart --service taiga-gateway --yes
```

---

## Required Variables

Set these via `railway variables --set "KEY=VALUE" --service SERVICE_NAME`.

### taiga-back

| Variable | Description | Example |
|---|---|---|
| `TAIGA_SECRET_KEY` | Django secret key (unpredictable) | `some-random-string` |
| `TAIGA_SITES_SCHEME` | Protocol | `https` |
| `TAIGA_SITES_DOMAIN` | Domain without protocol | `taiga.example.com` |
| `POSTGRES_DB` | Database name | `railway` |
| `POSTGRES_USER` | DB user | `postgres` |
| `POSTGRES_PASSWORD` | DB password | `...` |
| `POSTGRES_HOST` | **TCP proxy host** (NOT `.railway.internal`) | `trolley.proxy.rlwy.net` |
| `POSTGRES_PORT` | DB port | `53109` |
| `POSTGRES_SSLMODE` | SSL mode | `require` |
| `EMAIL_BACKEND` | Email backend | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | SMTP host | `smtp.sendgrid.net` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_HOST_USER` | SMTP user | `apikey` |
| `EMAIL_HOST_PASSWORD` | SMTP password | `...` |
| `DEFAULT_FROM_EMAIL` | Sender address | `noreply@example.com` |
| `PUBLIC_REGISTER_ENABLED` | Allow public signup | `True` |

### taiga-front

| Variable | Description | Example |
|---|---|---|
| `TAIGA_URL` | Full URL (must match back's domain) | `https://taiga.example.com` |

### taiga-gateway

No variables needed — `PORT` and `NGINX_RESOLVER` are resolved automatically by the entrypoint script.

---

## Optional: Cloudflare R2 Media Storage

To persist media files across deploys (attachments, avatars), configure R2:

```bash
railway variables --set "R2_ACCESS_KEY_ID=..." --service taiga-back
railway variables --set "R2_SECRET_ACCESS_KEY=..." --service taiga-back
railway variables --set "R2_BUCKET_NAME=taiga-media" --service taiga-back
railway variables --set "R2_ACCOUNT_ID=..." --service taiga-back
railway variables --set "R2_PUBLIC_URL=https://media.example.com" --service taiga-back
```

Without R2, media is stored on the container filesystem — **files are lost on every redeploy**.

---

## Admin User

```bash
railway ssh --service taiga-back -- python /taiga-back/manage.py createsuperuser
```

---

## Useful Commands

```bash
# Check service logs
railway logs --service taiga-back

# Run any Django management command
railway ssh --service taiga-back -- python /taiga-back/manage.py [COMMAND]

# Update a variable
railway variables --set "KEY=VALUE" --service SERVICE_NAME

# Get the public domain
railway domain --service taiga-gateway
```

---

## Critical Pitfalls

1. **DB must use TCP proxy host** — `trolley.proxy.rlwy.net`, never `.railway.internal`
2. **Gateway must restart** after any back/front redeploy — nginx caches IPs at boot
3. **`--path-as-root` is mandatory** — Railway deploys fail silently without it
4. **`TAIGA_SITES_DOMAIN` and `TAIGA_URL` must match** — domain mismatch shows a blank error page
5. **`STATIC_URL = "/static/"`** — if you touch `config.py`, keep this or Django Admin CSS breaks
6. **Events backend full path** — use `"taiga.events.backends.postgresql.EventsPushBackend"`, not `"pg"`

---

## File Structure

```
railway/
  taiga-back/
    config.py              # ⚠ MOST CRITICAL — Django settings overrides
    urls_railway.py        # Custom URLs (grappelli + media serving)
    Dockerfile             # Installs whitenoise, grappelli, django-storages
    base_site.html         # Custom Django admin branding
  taiga-front/
    Dockerfile             # Copies disable-events script
    99-disable-events.sh   # Sets eventsUrl=null in conf.json
  taiga-gateway/
    taiga.conf.template    # Nginx config with Railway ${PORT} and .railway.internal
    docker-entrypoint-railway.sh  # Resolves DNS nameserver for nginx resolver
    Dockerfile
  taiga-async/
    config.py              # Celery config (uses RabbitMQ, not memory://)
    urls_railway.py
    Dockerfile
  DEPLOY_GUIDE.md          # Full deployment walkthrough
  BACKUP_GUIDE.md          # Database backup procedures
  R2_STORAGE_GUIDE.md      # Cloudflare R2 setup guide
```

---

## Contributing

- Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for commit messages
- Do not PR translation files (except `-en.json`) — managed via [Weblate](https://hosted.weblate.org/projects/taiga/)
- License: MPL-2.0 — see [DCOLICENSE](DCOLICENSE) for contributor terms
