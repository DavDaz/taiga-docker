# Skill Registry — taiga-docker

Generated: 2026-04-14

## Compact Rules

### use-railway (project)
- Always run `railway status --json` to verify context before any mutation
- Use `--path-as-root` on every `railway up` command (mandatory, fails silently without it)
- Always restart gateway after deploying back or front: `railway service restart --service taiga-gateway --yes`
- Prefer `--service` and `--environment` flags explicitly over relying on linked context
- For destructive actions, confirm intent before executing

### django-expert (project)
- First line of config.py must be `from .common import *  # noqa`
- Booleans: `os.getenv("VAR", "False") == "True"` — never use `bool()`
- Integers: `int(os.getenv("VAR", "587"))`
- Double quotes, section headers with `# ---` dashed blocks
- STATIC_URL must stay `/static/` in config.py

### django-drf (user)
- Use ViewSets + Routers for CRUD resources
- Serializers own validation logic
- Use `permission_classes` and `authentication_classes` explicitly

### pytest (user)
- Use fixtures for setup, not setUp/tearDown
- Parametrize with `@pytest.mark.parametrize`
- Mock at boundary level, not implementation level

### playwright (user)
- Use Page Object Model pattern
- Prefer `getByRole` / `getByLabel` over CSS selectors
- Always wait for network idle after navigation

## User Skills

| Skill | Trigger Context |
|-------|----------------|
| `use-railway` | Railway deployments, services, variables, logs, infra |
| `django-expert` | config.py, urls_railway.py, Django middleware, admin |
| `django-drf` | Django REST Framework ViewSets, Serializers, Filters |
| `pytest` | Python tests, fixtures, mocking |
| `playwright` | E2E tests, browser automation |
| `react-19` | React components (no useMemo/useCallback needed) |
| `nextjs-15` | Next.js App Router, Server Actions |
| `typescript` | TypeScript strict patterns |
| `tailwind-4` | Tailwind CSS 4, cn(), theme variables |
| `zod-4` | Zod schema validation |
| `zustand-5` | React state management |
| `ai-sdk-5` | Vercel AI SDK 5 |
| `go-testing` | Go tests, Bubbletea TUI |
| `skill-creator` | Creating new agent skills |
| `branch-pr` | PR creation workflow |
| `issue-creation` | GitHub issue creation |
| `judgment-day` | Parallel adversarial review |

## Convention Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project-level agent instructions |
| `AGENTS.md` | Cross-cutting norms and deploy workflow |
