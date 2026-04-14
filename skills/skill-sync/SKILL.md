---
name: skill-sync
description: >
  Syncs skill metadata to CLAUDE.md Auto-invoke sections.
  Trigger: When updating skill metadata (metadata.scope/metadata.auto_invoke), registering a newly downloaded skill, regenerating Auto-invoke tables, or running ./skills/skill-sync/assets/sync.sh (including --dry-run/--scope).
license: Apache-2.0
metadata:
  author: prowler-cloud
  version: "1.0"
  scope: [root]
  auto_invoke:
    - "After creating/modifying a skill"
    - "Regenerate CLAUDE.md Auto-invoke tables (sync.sh)"
    - "Troubleshoot why a skill is missing from CLAUDE.md auto-invoke"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Purpose

Keeps CLAUDE.md Auto-invoke sections in sync with skill metadata. When you create or modify a skill, run the sync script to automatically update all affected CLAUDE.md files.

## Required Skill Metadata

Each skill that should appear in Auto-invoke sections needs these fields in `metadata`.

`auto_invoke` can be either a single string **or** a list of actions:

```yaml
metadata:
  author: prowler-cloud
  version: "1.0"
  scope: [ui]                                    # Which AGENTS.md: ui, api, sdk, root

  # Option A: single action
  auto_invoke: "Creating/modifying components"

  # Option B: multiple actions
  # auto_invoke:
  #   - "Creating/modifying components"
  #   - "Refactoring component folder placement"
```

### Scope Values

| Scope | Updates |
|-------|---------|
| `root` | `CLAUDE.md` (repo root) |
| `ui` | `ui/CLAUDE.md` |
| `api` | `api/CLAUDE.md` |
| `sdk` | `prowler/CLAUDE.md` |
| `mcp_server` | `mcp_server/CLAUDE.md` |

Skills can have multiple scopes: `scope: [ui, api]`

---

## Usage

### After Creating/Modifying a Skill

```bash
./skills/skill-sync/assets/sync.sh
```

### What It Does

1. Reads all `skills/*/SKILL.md` files
2. Extracts `metadata.scope` and `metadata.auto_invoke`
3. Generates Auto-invoke tables for each AGENTS.md
4. Updates the `### Auto-invoke Skills` section in each file

---

## Example

Given this skill metadata:

```yaml
# skills/prowler-ui/SKILL.md
metadata:
  author: prowler-cloud
  version: "1.0"
  scope: [ui]
  auto_invoke: "Creating/modifying React components"
```

The sync script generates in `ui/CLAUDE.md`:

```markdown
### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying React components | `prowler-ui` |
```

---

## Commands

```bash
# Sync all CLAUDE.md files
./skills/skill-sync/assets/sync.sh

# Dry run (show what would change)
./skills/skill-sync/assets/sync.sh --dry-run

# Sync specific scope only
./skills/skill-sync/assets/sync.sh --scope root
```

---

## Registering a Downloaded Skill

Skills downloaded via `npx` don't include `metadata.scope` or `metadata.auto_invoke` — those are project-specific. When `sync.sh` reports a skill as missing metadata, follow this flow:

### Step 1 — Read the skill
```bash
cat .claude/skills/{skill-name}/SKILL.md
```
Understand what the skill does and when it should be used.

### Step 2 — Determine scope
For this project, always `root` (single CLAUDE.md at repo root).

### Step 3 — Ask the user
Show the skill's description and ask:
> "¿Cuándo querés que se invoque esta skill automáticamente? Describí las acciones que la deben disparar."

### Step 4 — Add metadata block
Add to the skill's frontmatter (after `allowed-tools` if present, otherwise after `license`):

```yaml
metadata:
  author: {keep existing or use your name}
  version: "1.0"
  scope: [root]
  auto_invoke:
    - "Action that triggers this skill"
    - "Another triggering action"
```

### Step 5 — Run sync
```bash
bash skills/skill-sync/assets/sync.sh
```

---

## Checklist After Modifying Skills

- [ ] Added `metadata.scope` to new/modified skill
- [ ] Added `metadata.auto_invoke` with action description
- [ ] Ran `./skills/skill-sync/assets/sync.sh`
- [ ] Verified CLAUDE.md files updated correctly
