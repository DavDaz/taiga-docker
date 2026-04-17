# Repository Guidelines

> Guidance for AI coding agents operating in this repository.

## How to Use This Guide

- Start here for project context and cross-cutting norms.
- For detailed deployment/config workflows, load the `use-railway` skill on-demand.
- For deeper guides, see `railway/DEPLOY_GUIDE.md`, `railway/BACKUP_GUIDE.md`, and `railway/R2_STORAGE_GUIDE.md`.

## Prerequisites (New Machine Setup)

Before working with this repo on a new machine, register the Railway MCP server in Claude Code:

```bash
claude mcp add railway --transport http https://mcp.railway.com
```

This gives Claude Code direct access to Railway deployments, logs, variables, and services — required for all operations in this project.

---

## Critical Context

- **This project does NOT run locally.** There is no `docker-compose up`, no local dev server.
- **All changes are deployed to Railway.** Every code change requires a `railway up` deploy.
- **There is no test suite, no linter, and no CI/CD pipeline.** Validation is manual via logs and curl.
- **This is NOT application code** — it's Dockerfiles, nginx configs, and Django settings overrides.
- Taiga application source lives at https://github.com/taigaio/taiga.

---

## Available Skills

Use these skills for detailed patterns on-demand:

### Project-Specific Skills

| Skill | Description | Location |
|-------|-------------|----------|
| `use-railway` | Deploy, configure, troubleshoot Railway services | [SKILL.md](.agents/skills/use-railway/SKILL.md) |

### Generic Skills (Any Project)

| Skill | Description |
|-------|-------------|
| `django-drf` | Django REST Framework patterns |
| `pytest` | Python testing patterns |
| `typescript` | TypeScript strict patterns |

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Deploying any service to Railway | `use-railway` |
| Restarting gateway after deploy | `use-railway` |
| Setting/listing Railway variables | `use-railway` |
| Checking service logs or status | `use-railway` |
| Creating environments or domains | `use-railway` |
| Running Django management commands via SSH | `use-railway` |
| Troubleshooting 504s, build failures, or DNS issues | `use-railway` |
| Modifying `config.py` Django settings | `django-drf` |

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
```

---

## Deploy Workflow

> **This project does NOT run locally.** Use Railway CLI or the Railway MCP for all operations.

```bash
# Deploy services (--path-as-root is MANDATORY)
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d

# ALWAYS restart gateway after redeploying back or front
railway service restart --service taiga-gateway --yes
```

---

## Code Style

### Python — `config.py` / `urls_railway.py`

- `from .common import *  # noqa` — REQUIRED first line in config.py
- `os.getenv("VAR", "False") == "True"` for booleans (string comparison, never `bool()`)
- `int(os.getenv("VAR", "587"))` for integers with sensible defaults
- Double quotes for all strings
- Section headers with `# ---` dashed comment blocks

### Shell Scripts

- Shebang: `#!/bin/sh` for Railway entrypoints
- `set -e` (fail-fast) and `exec` for final command

### Nginx

- `set $upstream_xxx http://service.railway.internal:PORT` — never hardcode
- `${PORT}` (Railway-injected) and `${NGINX_RESOLVER}` (entrypoint-resolved)

### Dockerfiles

- Base: `taigaio/taiga-back:latest`, `taigaio/taiga-front:latest`, `nginx:1.19-alpine`
- COPY config first, then RUN build steps
- Pin pip packages: `"Django<4"`, `"django-grappelli>=3.0,<4.0"`

### Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat:`, `fix:`, `docs:`, `chore:`

---

## Critical Pitfalls

1. **Railway DB = TCP proxy host** — use `trolley.proxy.rlwy.net`, NEVER `.railway.internal`
2. **Gateway must restart** after any back/front redeploy — nginx caches IPs at boot → 504s
3. **`config.py` is MANDATORY** — `common.py` hardcodes `127.0.0.1` as DB host
4. **Celery disabled in taiga-back** — without it, requests hang on `localhost:5672`
5. **`STATIC_URL = "/static/"`** must stay in config.py — common.py sets an absolute URL that breaks WhiteNoise
6. **Events backend full path** — `"taiga.events.backends.postgresql.EventsPushBackend"`, NOT `"pg"`
7. **`--path-as-root`** is MANDATORY on all `railway up` commands
8. **`TAIGA_SITES_DOMAIN` (back) = `TAIGA_URL` domain (front)** — mismatch → blank error page

---

## Contributing

- GitHub issues and PRs
- License: MPL-2.0 — see [DCOLICENSE](DCOLICENSE)
- Do NOT PR translation files except `-en.json` — managed via [Weblate](https://hosted.weblate.org/projects/taiga/)
