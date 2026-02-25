# AGENTS.md

> Guidance for AI coding agents operating in this repository.

## What This Repo Is

Infrastructure/configuration repo for **Taiga v6.9.0** on [Railway](https://railway.app).
**This is NOT application code** — it's Dockerfiles, nginx configs, and Django settings overrides.
Taiga application source lives at https://github.com/taigaio/taiga.

There is **no test suite, no linter, and no CI/CD pipeline**. Validation is manual.

---

## Architecture

```
taiga-gateway (nginx)
    ├── taiga-front   (Angular SPA — taigaio/taiga-front:latest)
    └── taiga-back    (Django API  — taigaio/taiga-back:latest)
         └── Managed PostgreSQL (Railway)
```

Services removed vs. standard Taiga: taiga-events, taiga-protected, both RabbitMQ instances.
Solutions: WhiteNoise (static), Django serve view (media), PostgreSQL events backend.

---

## File Structure

```
railway/
  taiga-back/
    config.py              # ⚠ MOST CRITICAL — Django settings overrides for Railway
    urls_railway.py        # Custom URLs (grappelli admin + media serving endpoint)
    Dockerfile             # Installs whitenoise, grappelli, django-storages[s3]
    base_site.html         # Custom Django admin branding template
  taiga-front/
    Dockerfile             # Copies disable-events script
    99-disable-events.sh   # Sets eventsUrl=null in conf.json (no taiga-events)
  taiga-gateway/
    taiga.conf.template    # Nginx with Railway ${PORT} and .railway.internal DNS
    docker-entrypoint-railway.sh  # Reads /etc/resolv.conf to set NGINX_RESOLVER
    Dockerfile             # nginx:1.19-alpine + template + entrypoint
  taiga-async/
    config.py              # Celery worker config (uses actual RabbitMQ, not memory://)
    urls_railway.py        # Shared URL config
    Dockerfile             # Celery async worker entrypoint
  DEPLOY_GUIDE.md          # Full deployment walkthrough
  BACKUP_GUIDE.md          # Database backup procedures
  R2_STORAGE_GUIDE.md      # Cloudflare R2 setup guide
```

---

## Deploy Commands

> **CRITICAL**: `--path-as-root` is required on every `railway up` command.

```bash
# Deploy services
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d

# ALWAYS restart gateway after redeploying back or front
railway service restart --service taiga-gateway --yes

# Variables
railway variables --set "KEY=VALUE" --service SERVICE_NAME

# Create superuser
railway ssh --service taiga-back -- python /taiga-back/manage.py createsuperuser

# Run any Django management command
railway ssh --service taiga-back -- python /taiga-back/manage.py [COMMAND]

# Domain
railway domain --service taiga-gateway
```

---

## Validation (no automated tests)

```bash
railway logs --service taiga-back
railway logs --service taiga-gateway
# Then verify manually:
curl -s https://your-domain.railway.app/api/v1/ | head -20
```

---

## Code Style Guidelines

### Python — `config.py` and `urls_railway.py`

```python
from .common import *  # noqa   ← REQUIRED first line in config.py
import os

# --------------------------------------------------------------------------
# Section Name - brief description
# --------------------------------------------------------------------------
SETTING = os.getenv("VAR_NAME", "default")
```

- `os.getenv("VAR", "False") == "True"` for booleans — string comparison, never `bool()`
- `int(os.getenv("VAR", "587"))` for integers with sensible defaults
- Double quotes for all strings (Django convention in this project)
- `stdlib` imports (`os`) go **after** the wildcard common import
- Section headers with `# ---` dashed comment blocks (see existing files)

### Shell Scripts

- Shebang: `#!/usr/bin/env sh` (standard) or `#!/bin/sh` (Railway entrypoints)
- `set -e` in Railway entrypoints (fail-fast)
- `exec` to replace shell process when launching final command

### Nginx Configuration (Railway)

- Use `set $upstream_xxx http://service.railway.internal:PORT` variables — never hardcode
- Always include: `proxy_pass_header Server`, `proxy_set_header Host $http_host`, `proxy_redirect off`
- `client_max_body_size 100M` and `charset utf-8` in server block
- Use `${PORT}` (Railway injects this) and `${NGINX_RESOLVER}` (set by entrypoint script)

### Dockerfiles

- Base: `taigaio/taiga-back:latest`, `taigaio/taiga-front:latest`, `nginx:1.19-alpine`
- COPY config files first, then RUN build steps
- Pin pip packages: `"Django<4"`, `"django-grappelli>=3.0,<4.0"`
- `collectstatic` needs dummy env vars (filesystem op, no DB connection required)

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
```
feat: add R2 storage support for media files
fix: set explicit STATIC_URL for WhiteNoise interception
docs: document Django admin CSS fix
chore: bump to 6.9.0 version
```

---

## Critical Pitfalls — Read Before Changing Anything

1. **Railway DB = TCP proxy host** — use `trolley.proxy.rlwy.net`, NEVER `.railway.internal`
2. **Gateway must restart** after any back/front redeploy — nginx caches IPs at boot → 504s
3. **`config.py` is MANDATORY** — `common.py` hardcodes `127.0.0.1` as DB host
4. **Celery disabled in taiga-back** — without it, requests hang on `localhost:5672`
5. **`STATIC_URL = "/static/"`** in config.py — common.py sets an absolute URL that breaks WhiteNoise
6. **Events backend full path** — `"taiga.events.backends.postgresql.EventsPushBackend"`, NOT `"pg"`
7. **`--path-as-root`** is required on all `railway up` commands
8. **`TAIGA_SITES_DOMAIN` (back) = `TAIGA_URL` domain (front)** — mismatch → blank error page
9. **Do NOT PR translation files** except `-en.json` — translations managed via Weblate

---

## Contributing

- GitHub issues and PRs
- License: MPL-2.0 — see [DCOLICENSE](DCOLICENSE)
- Translations: [Weblate](https://hosted.weblate.org/projects/taiga/)
