"""
Taiga MCP Server — exposes 5 Taiga project management tools to AI agents.

Tools:
  - list_projects: list all accessible projects
  - create_issue: create a new issue in a project
  - move_status: update an issue's status
  - add_comment: add a comment to an issue
  - assign_user: assign a user to an issue

Run via: python -m taiga_mcp.server  (or mcp/run.sh)
Transport: stdio (spawned by OpenCode)
"""
from mcp.server.fastmcp import FastMCP
from .client import TaigaClient

mcp = FastMCP("taiga")
_client: TaigaClient | None = None


def get_client() -> TaigaClient:
    global _client
    if _client is None:
        _client = TaigaClient()
    return _client


@mcp.tool()
def list_projects() -> list[dict]:
    """List all Taiga projects accessible to the authenticated user.

    Returns a list of projects with id, name, and slug.
    """
    client = get_client()
    user = client.get("/api/v1/users/me")
    projects = client.get(f"/api/v1/projects?member={user['id']}")
    return [{"id": p["id"], "name": p["name"], "slug": p["slug"]} for p in projects]


@mcp.tool()
def create_issue(project_id: int, subject: str, description: str = "") -> dict:
    """Create a new issue in a Taiga project.

    Args:
        project_id: The numeric ID of the project (from list_projects)
        subject: The title/subject of the issue
        description: Optional description text

    Returns the created issue's id and a reference URL.
    """
    client = get_client()
    data = {"project": project_id, "subject": subject}
    if description:
        data["description"] = description
    issue = client.post("/api/v1/issues", data)
    base_url = client.base_url
    return {
        "id": issue["id"],
        "ref": issue.get("ref"),
        "subject": issue["subject"],
        "url": f"{base_url}/project/{issue['project_extra_info']['slug']}/issue/{issue.get('ref')}",
    }


@mcp.tool()
def move_status(issue_id: int, status_name: str) -> dict:
    """Move an issue to a new status by name.

    Args:
        issue_id: The numeric ID of the issue
        status_name: The target status name (e.g. "In progress", "Done")

    Returns confirmation with the new status.
    """
    client = get_client()
    issue = client.get_entity_with_version("issues", issue_id)
    project_id = issue["project"]
    version = issue["version"]

    # Resolve status name -> id
    statuses = client.get(f"/api/v1/issue-statuses?project={project_id}")
    status_map = {s["name"].lower(): s["id"] for s in statuses}
    target_id = status_map.get(status_name.lower())
    if target_id is None:
        available = ", ".join(s["name"] for s in statuses)
        raise ValueError(f"Status '{status_name}' not found. Available: {available}")

    updated = client.patch(f"/api/v1/issues/{issue_id}", {"status": target_id, "version": version})
    return {"id": issue_id, "new_status": updated["status_extra_info"]["name"]}


@mcp.tool()
def add_comment(issue_id: int, comment: str) -> dict:
    """Add a comment to an existing Taiga issue.

    Args:
        issue_id: The numeric ID of the issue
        comment: The comment text to add

    Returns confirmation with the updated issue version.
    """
    client = get_client()
    issue = client.get_entity_with_version("issues", issue_id)
    version = issue["version"]

    # Comments are added via PATCH on the issue resource with a 'comment' field
    updated = client.patch(f"/api/v1/issues/{issue_id}", {"comment": comment, "version": version})
    return {"issue_id": issue_id, "comment_added": True, "new_version": updated["version"]}


@mcp.tool()
def assign_user(issue_id: int, username: str) -> dict:
    """Assign a team member to an existing Taiga issue.

    Args:
        issue_id: The numeric ID of the issue
        username: The Taiga username of the person to assign

    Returns confirmation with assigned user details.
    """
    client = get_client()
    issue = client.get_entity_with_version("issues", issue_id)
    project_id = issue["project"]
    version = issue["version"]

    # Resolve username -> user id via project members
    members = client.get(f"/api/v1/projects/{project_id}/members")
    user_map = {m["username"]: m["id"] for m in members}
    user_id = user_map.get(username)
    if user_id is None:
        available = ", ".join(m["username"] for m in members)
        raise ValueError(f"User '{username}' not found in project. Members: {available}")

    updated = client.patch(f"/api/v1/issues/{issue_id}", {"assigned_to": user_id, "version": version})
    assigned = updated.get("assigned_to_extra_info") or {}
    return {
        "issue_id": issue_id,
        "assigned_to": assigned.get("username", username),
        "full_name": assigned.get("full_name_display", ""),
    }


if __name__ == "__main__":
    mcp.run()
