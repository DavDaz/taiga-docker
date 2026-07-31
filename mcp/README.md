# Use Taiga from local AI clients

This directory provides a local stdio MCP server for Taiga. It gives an AI client five project-management tools while keeping Taiga credentials in a local, Git-ignored file.

## Tools

| Tool | Effect |
|------|--------|
| `list_projects` | Read accessible projects and return `id`, `name`, and `slug` |
| `create_issue` | Create an issue in a project |
| `move_status` | Move an issue to a named status |
| `add_comment` | Add a comment to an issue |
| `assign_user` | Assign an issue to a project member by username |

Only `list_projects` is read-only. Review the requested action before allowing an AI to call any other tool.

## Fresh-machine setup

Run these commands from the repository root:

```sh
git clone <repository-url> taiga-docker
cd taiga-docker
python3 -m venv mcp/.venv
mcp/.venv/bin/python -m pip install -r mcp/requirements.txt
umask 077
touch mcp/.env
chmod 600 mcp/.env
```

Edit `mcp/.env` as plain data. Use either an existing bearer token:

```dotenv
TAIGA_URL=https://taiga.example.com
TAIGA_TOKEN=replace-with-your-token
```

Or let the server request a short-lived token when it starts:

```dotenv
TAIGA_URL=https://taiga.example.com
TAIGA_USERNAME=replace-with-your-username
TAIGA_PASSWORD=replace-with-your-password
```

The parser accepts only `TAIGA_URL`, `TAIGA_USERNAME`, `TAIGA_PASSWORD`, and `TAIGA_TOKEN`. It does not execute shell syntax, strip quotes, expand variables, or trim values. Keep each value on one line and do not add spaces around the key or `=` unless they are intentionally part of the value.

The launcher rejects symlinks, non-regular files, duplicate or unknown keys, malformed records, and modes other than `0400` or `0600`. A missing `.env` is allowed so credentials can instead come from an already controlled process environment.

## Token guidance

Prefer a revocable token from a trusted secret-management or Taiga administration workflow. Taiga's official REST API also returns a standard bearer token from `POST /api/v1/auth`; avoid putting a password in shell history, command arguments, scripts, or copied chat messages when using that API. The username/password configuration above performs that login in memory and does not write the returned token.

Never commit `.env`, paste credentials into an AI prompt, place them directly in an MCP client configuration, or enable shell tracing while launching the server. This integration currently uses standard `Bearer` tokens, not Taiga application tokens, whose authorization header format differs.

## Register each AI client

Each AI client has its own MCP registry. Register this same local server independently in every client you use. Replace `/absolute/path/to/taiga-docker` with the clone's absolute path; do not copy that placeholder literally.

### OpenCode

This repository already contains `opencode.json`:

```json
{
  "mcp": {
    "taiga": {
      "type": "local",
      "command": ["sh", "mcp/run.sh"],
      "enabled": true
    }
  }
}
```

That command is repository-relative and works when OpenCode loads this workspace. For a global OpenCode configuration, use an absolute script path instead. Verify with:

```sh
opencode mcp list
```

### Claude Code

Register a local stdio server using an absolute path. The default `local` scope applies only to this project:

```sh
claude mcp add --transport stdio --scope local taiga -- \
  sh /absolute/path/to/taiga-docker/mcp/run.sh
claude mcp list
```

Use `--scope user` only if you intentionally want this server available in every Claude Code project. A shared project registration would use `.mcp.json`, but an absolute path is machine-specific and should not be committed as a portable team default.

### OpenAI Codex

Register the stdio server with an absolute path:

```sh
codex mcp add taiga -- sh /absolute/path/to/taiga-docker/mcp/run.sh
codex mcp list
```

Codex CLI, the Codex IDE extension, and the ChatGPT desktop app share the local Codex `config.toml` for the same host. ChatGPT web does not run local stdio servers.

## Verify

Restart the AI client after registration, then inspect its MCP server list. Ask only for a read operation first:

```text
Use Taiga list_projects and show only each project's ID, name, and slug.
```

Expected tools are `list_projects`, `create_issue`, `move_status`, `add_comment`, and `assign_user`.

Example write prompts, which require careful review:

```text
Create an issue in Taiga project 12 with subject "Document backup restore" and no description.
Move Taiga issue 34 to "In progress".
Assign Taiga issue 34 to username alex.
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Virtual environment is missing | Run the venv creation and dependency installation commands above |
| Credentials file cannot be opened safely | Confirm `mcp/.env` is a regular file, not a symlink |
| Unsafe permissions | Run `chmod 600 mcp/.env` |
| Invalid, unknown, or duplicate entry | Use one exact allowlisted `KEY=value` record per line |
| `TAIGA_URL` is required | Add it to `.env` or the controlled parent environment |
| Authentication fails | Confirm the URL and credentials, or replace an expired token |
| Client shows no tools | Confirm the absolute path, restart the client, and inspect its MCP status command |

The server communicates over stdout using MCP. Do not add debug prints to stdout; use secret-free stderr diagnostics only.

## Rotate or revoke access

1. Revoke or expire the old credential through the Taiga administration or identity workflow available for your deployment. Standard login tokens expire; password changes and server-side session policies depend on the deployment.
2. Replace the local value in `mcp/.env` without changing its mode.
3. Restart every registered AI client so it starts a new server process.
4. Run the read-only `list_projects` verification.
5. Remove obsolete local copies and clear any terminal output that exposed a token during an external acquisition workflow.

If a credential may have entered Git history, logs, screenshots, or chat, treat it as compromised and revoke it immediately. Deleting the visible text is not sufficient.

## Official references

- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)
- [Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp)
- [OpenAI Codex MCP](https://developers.openai.com/codex/extend/mcp/)
- [Taiga REST API authentication](https://docs.taiga.io/api.html#_authentication)
