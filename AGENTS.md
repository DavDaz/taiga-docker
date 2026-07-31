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
    taiga_railway/         # Railway-specific Django app (R2 thumbnail signals)
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
skills/
  django-drf/SKILL.md      # Django REST Framework patterns
  pytest/SKILL.md          # Python testing patterns
  railway-mcp/SKILL.md     # Railway MCP operations
.agents/skills/
  use-railway/SKILL.md     # Detailed Railway CLI workflows
```

---

## Skills

Local skills live in `skills/`. Load them BEFORE writing any Python or making config changes.

| Context | Load this skill |
|---|---|
| Editing `config.py`, `urls_railway.py`, Django settings | `skills/django-drf/SKILL.md` |
| Writing Python scripts or test utilities | `skills/pytest/SKILL.md` |
| Railway CLI operations and troubleshooting | `.agents/skills/use-railway/SKILL.md` |

**How to load**: Read the SKILL.md file completely before writing code. Apply ALL patterns in it.

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Adding or modifying Django settings overrides | `django-drf` |
| After creating/modifying a skill | `skill-sync` |
| Checking Railway build/deploy logs | `railway-mcp` |
| Creating test fixtures or mocks for Django code | `pytest` |
| Deploying or redeploying Railway services | `railway-mcp` |
| Editing config.py or urls_railway.py | `django-drf` |
| Regenerate AGENTS.md Auto-invoke tables (sync.sh) | `skill-sync` |
| Troubleshoot why a skill is missing from AGENTS.md auto-invoke | `skill-sync` |
| Troubleshooting 502/504 or runtime errors on Railway | `railway-mcp` |
| Writing Python code for taiga-back or taiga-async | `django-drf` |
| Writing Python test scripts or utilities | `pytest` |

---

## Railway Prerequisites

Install the Railway CLI, authenticate, and verify that this repository is linked to the intended project and environment before running Railway commands:

```bash
brew install railway
railway login
railway link
railway status --json
```

Claude Code users can also register Railway's hosted MCP server:

```bash
claude mcp add railway --transport http https://mcp.railway.com
```

Use `.agents/skills/use-railway/SKILL.md` for detailed Railway workflows. Do not deploy or mutate Railway merely to validate repository changes.

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

> **There is no CI. Every change must be manually verified before considering it done.**

### After deploying taiga-back

```bash
# 1. Check build logs — look for import errors or missing env vars
railway logs --service taiga-back

# 2. Verify the API responds
curl -s https://your-domain.railway.app/api/v1/ | head -20

# 3. Verify Django admin loads (CSS must render — not just HTML)
curl -s https://your-domain.railway.app/admin/ | grep -i "django"

# 4. Check static files are served by WhiteNoise (not 404)
curl -I https://your-domain.railway.app/static/admin/css/base.css
```

### After deploying taiga-front

```bash
# Restart gateway first — nginx caches IPs at boot
railway service restart --service taiga-gateway --yes

# Then verify the SPA loads
curl -s https://your-domain.railway.app/ | grep -i "taiga"
```

### After deploying taiga-gateway

```bash
railway logs --service taiga-gateway

# Verify upstream routing works end-to-end
curl -s https://your-domain.railway.app/api/v1/
curl -s https://your-domain.railway.app/
```

### Smoke test checklist

- [ ] API responds at `/api/v1/`
- [ ] Django admin loads with CSS at `/admin/`
- [ ] Frontend SPA loads at `/`
- [ ] Login works (verifies DB connection + CORS + TAIGA_SITES_DOMAIN)
- [ ] No 504 errors (gateway upstream resolution)

---

## Debugging Guide

> No CI, no tests — when something breaks, work systematically. Never guess.

### Step 1 — Read logs before touching anything

```bash
railway logs --service taiga-back    # Django startup errors, import failures
railway logs --service taiga-gateway # Nginx upstream errors, 502/504
railway logs --service taiga-front   # Script errors in disable-events
```

### Step 2 — Identify which layer broke

```
Request → taiga-gateway (nginx) → taiga-back (Django) → PostgreSQL
```

| Symptom | Likely layer |
|---|---|
| 502 Bad Gateway | nginx can't reach taiga-back |
| 504 Gateway Timeout | nginx IP cache stale — restart gateway |
| 500 Internal Server Error | Django / config.py error |
| Blank page, no errors | `TAIGA_SITES_DOMAIN` mismatch with `TAIGA_URL` |
| Admin CSS missing | `STATIC_URL` wrong or WhiteNoise not intercepting |
| Login fails silently | CORS, `TAIGA_SITES_DOMAIN`, or DB connection |

### Step 3 — Check recent changes first

```bash
git diff HEAD~1
```

Most breakages come from a single wrong env var or a missing setting override in `config.py`.

### Step 4 — Verify environment variables

```bash
railway variables --service taiga-back
railway variables --service taiga-gateway
```

Cross-check against Critical Pitfalls below — especially `TAIGA_SITES_DOMAIN` vs `TAIGA_URL`.

### Step 5 — Fix ONE thing at a time

Do not stack multiple changes. Deploy, verify, then proceed. If 3+ fixes haven't worked,
the problem is likely architectural — re-read the Critical Pitfalls section completely.

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

## MCP Integration

AI agents can interact with Taiga through the local stdio MCP server in `mcp/`. See [`mcp/README.md`](mcp/README.md) for secure setup, client registration, verification, and credential rotation.

### Setup

```bash
python3 -m venv mcp/.venv
mcp/.venv/bin/python -m pip install -r mcp/requirements.txt
umask 077 && touch mcp/.env && chmod 600 mcp/.env
```

Store only the allowlisted Taiga variables in `mcp/.env`; never commit or share that file. `opencode.json` registers the server for this workspace. Other AI clients require independent registration as documented in the guide. No Railway changes are required.

### Available Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List all accessible Taiga projects (returns id, name, slug) |
| `create_issue` | Create a new issue in a project |
| `move_status` | Update an issue's status by name (e.g. "In progress", "Done") |
| `add_comment` | Add a comment to an issue |
| `assign_user` | Assign a team member to an issue by username |

### Known Limitations

- Comments use PATCH on the issue resource — Taiga requires the current `version` field to prevent conflicts
- `move_status` resolves status names case-insensitively; use the exact name from your project's board
- `assign_user` requires the Taiga username (not display name) of the team member
- No WebSocket/events support — this MCP operates on REST API only

### File Structure

```
mcp/
  taiga_mcp/
    __init__.py     # package marker
    client.py       # HTTP client with lazy auth
    launcher.py     # secure credential loader and process entry point
    server.py       # FastMCP server with 5 tools
  tests/            # credential-loader tests using temporary files
  README.md         # setup and client registration guide
  requirements.txt  # mcp>=1.0, httpx>=0.27
  run.sh            # POSIX wrapper for the Python launcher
opencode.json       # MCP server registration (project-level)
```

---

## Contributing

- GitHub issues and PRs
- License: MPL-2.0 — see [DCOLICENSE](DCOLICENSE)
- Translations: [Weblate](https://hosted.weblate.org/projects/taiga/)
