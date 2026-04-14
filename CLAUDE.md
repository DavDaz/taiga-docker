# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical Context

- **This project does NOT run locally.** No `docker-compose up`, no local dev server, no test suite, no linter.
- **All validation is manual** — deploy to Railway, then check logs or curl the endpoint.
- **This is NOT application code** — it's Dockerfiles, nginx configs, and Django settings overrides on top of upstream Taiga images.
- Full agent guidance lives in [AGENTS.md](AGENTS.md). Read it before making changes.

## Architecture

```
taiga-gateway (nginx)
    ├── taiga-front   (Angular SPA — taigaio/taiga-front:latest)
    └── taiga-back    (Django API  — taigaio/taiga-back:latest)
         └── Managed PostgreSQL (Railway)
```

Key deviations from standard Taiga Docker Compose:
- No RabbitMQ / taiga-events → PostgreSQL events backend, Celery disabled
- No shared volumes → WhiteNoise serves static files, Django view serves media
- Optional `taiga-async` service if Celery workers are needed

## Deploy

> `--path-as-root` is **mandatory** on every `railway up`.

```bash
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d

# ALWAYS restart gateway after deploying back or front
railway service restart --service taiga-gateway --yes
```

Other useful commands:
```bash
railway logs --service taiga-back
railway variables --set "KEY=VALUE" --service SERVICE_NAME
railway ssh --service taiga-back -- python /taiga-back/manage.py createsuperuser
```

## File Structure

```
railway/
  taiga-back/
    config.py              # ⚠ MOST CRITICAL — Django settings overrides for Railway
    urls_railway.py        # Custom URLs (grappelli admin + media serving)
    Dockerfile             # Installs whitenoise, grappelli, django-storages[s3]
    base_site.html         # Custom Django admin branding
  taiga-front/
    Dockerfile
    99-disable-events.sh   # Sets eventsUrl=null in conf.json (disables WebSocket)
  taiga-gateway/
    taiga.conf.template    # Nginx config using Railway ${PORT} + .railway.internal DNS
    docker-entrypoint-railway.sh  # Reads /etc/resolv.conf → sets NGINX_RESOLVER
    Dockerfile
  taiga-async/
    config.py              # Celery worker config (requires real RabbitMQ)
    Dockerfile
```

## Code Conventions

**Python (`config.py` / `urls_railway.py`)**
- First line must be `from .common import *  # noqa`
- Booleans: `os.getenv("VAR", "False") == "True"` (never `bool()`)
- Integers: `int(os.getenv("VAR", "587"))`
- Double quotes, section headers with `# ---` dashed blocks

**Shell scripts**
- Shebang: `#!/bin/sh`; always `set -e`; end with `exec`

**Nginx**
- Upstreams: `set $upstream_xxx http://service.railway.internal:PORT`
- Never hardcode ports or IPs

**Dockerfiles**
- Bases: `taigaio/taiga-back:latest`, `taigaio/taiga-front:latest`, `nginx:1.19-alpine`
- Pin pip packages: `"Django<4"`, `"django-grappelli>=3.0,<4.0"`

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Adding Django management commands via SSH | `django-expert` |
| Adding or changing Django middleware | `django-expert` |
| After creating/modifying a skill | `skill-sync` |
| Checking service logs or status | `use-railway` |
| Configuring Django settings (email, static, media, database) | `django-expert` |
| Configuring WhiteNoise or static file serving | `django-expert` |
| Creating environments or domains | `use-railway` |
| Customizing Django admin (grappelli, base_site.html) | `django-expert` |
| Debugging Django errors or 500s in taiga-back | `django-expert` |
| Deploying any service to Railway | `use-railway` |
| Modifying config.py or urls_railway.py | `django-expert` |
| Regenerate CLAUDE.md Auto-invoke tables (sync.sh) | `skill-sync` |
| Restarting gateway after deploy | `use-railway` |
| Running Django management commands via SSH | `use-railway` |
| Setting or listing Railway variables | `use-railway` |
| Troubleshoot why a skill is missing from CLAUDE.md auto-invoke | `skill-sync` |
| Troubleshooting 504s, build failures, or DNS issues | `use-railway` |

## Critical Pitfalls

1. **DB must use TCP proxy host** — `trolley.proxy.rlwy.net`, never `.railway.internal`
2. **Gateway must restart** after back/front redeploy — nginx caches upstream IPs at boot → 504s
3. **`STATIC_URL = "/static/"`** must stay in `config.py` — `common.py` sets an absolute URL that breaks WhiteNoise and Django Admin CSS
4. **Events backend full path** — `"taiga.events.backends.postgresql.EventsPushBackend"`, not `"pg"`
5. **`TAIGA_SITES_DOMAIN` (back) must equal `TAIGA_URL` domain (front)** — mismatch renders a blank error page
6. **Celery disabled in taiga-back** — `CELERY_BROKER_URL = "memory://"` must stay or requests hang on `localhost:5672`
