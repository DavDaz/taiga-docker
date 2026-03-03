---
name: railway-mcp
description: >
  Railway MCP operational workflow for Taiga infrastructure.
  Trigger: When deploying services, checking Railway logs/deployments, or troubleshooting Railway runtime issues.
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
  scope: [root]
  auto_invoke:
    - "Deploying or redeploying Railway services"
    - "Checking Railway build/deploy logs"
    - "Troubleshooting 502/504 or runtime errors on Railway"
---

## Purpose

Standardize how agents use Railway MCP and Railway CLI in this repo to avoid broken deploys and stale gateway routing.

## Critical Rules

- Always deploy with `--path-as-root` for each service.
- After back/front deploys, redeploy gateway when restart is not available.
- Validate with live endpoints after every deploy.
- Never batch unrelated fixes; deploy one logical change at a time.

## Canonical Deploy Sequence

```bash
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d
railway service redeploy --service taiga-gateway --yes
```

## Verification Checklist

```bash
curl -sS https://taiga.xsidian.dev/api/v1/
curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://taiga.xsidian.dev/
curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://taiga.xsidian.dev/admin/
curl -I https://taiga.xsidian.dev/static/admin/css/base.css
```

Expected:
- API endpoint returns JSON index
- Front page returns HTTP 200
- Admin returns HTTP 302 (redirect to login) or 200 when authenticated
- Admin CSS returns HTTP 200

## Fast Debug Flow

1. Check latest deployment status for `taiga-back`, `taiga-front`, `taiga-gateway`.
2. Pull build logs for the failing service.
3. If 504/upstream issues persist, redeploy gateway.
4. Re-run endpoint checks.

## Keywords

railway, mcp, deploy, logs, gateway, taiga, troubleshooting
