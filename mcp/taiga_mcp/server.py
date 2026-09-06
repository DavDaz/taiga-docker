"""Narrow Taiga MCP tools for issues, planning, and repeatable course plans."""

from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .client import TaigaClient


mcp = FastMCP("taiga")
_client: TaigaClient | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PointEstimate(StrictModel):
    role: str = Field(min_length=1)
    value: float = Field(ge=0)


class CourseTask(StrictModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    subject: str = Field(min_length=1)
    description: str = ""
    status: str = ""
    assignee: str = ""
    tags: list[str] = Field(default_factory=list)


class CourseStory(StrictModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    subject: str = Field(min_length=1)
    kind: Literal["lesson", "challenge", "lab", "quiz"]
    description: str = ""
    status: str = ""
    assignee: str = ""
    tags: list[str] = Field(default_factory=list)
    points: list[PointEstimate] = Field(default_factory=list)
    tasks: list[CourseTask] = Field(default_factory=list)


class CourseWeek(StrictModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    start_date: date
    end_date: date
    stories: list[CourseStory] = Field(min_length=1)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "CourseWeek":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class CoursePlan(StrictModel):
    project_id: int = Field(gt=0)
    plan_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    epic_subject: str = Field(min_length=1)
    epic_description: str = ""
    weeks: list[CourseWeek] = Field(min_length=1)

    @model_validator(mode="after")
    def references_are_unique_and_ordered(self) -> "CoursePlan":
        week_keys = [week.key for week in self.weeks]
        if len(week_keys) != len(set(week_keys)):
            raise ValueError("week keys must be unique")
        story_keys = [story.key for week in self.weeks for story in week.stories]
        if len(story_keys) != len(set(story_keys)):
            raise ValueError("story keys must be unique across the plan")
        task_markers = [
            f"{story.key}:{task.key}"
            for week in self.weeks
            for story in week.stories
            for task in story.tasks
        ]
        if len(task_markers) != len(set(task_markers)):
            raise ValueError("task stable markers must be unique across the plan")
        for previous, current in zip(self.weeks, self.weeks[1:]):
            if current.start_date <= previous.end_date:
                raise ValueError("weeks must be chronological and non-overlapping")
        return self


def get_client() -> TaigaClient:
    global _client
    if _client is None:
        _client = TaigaClient()
    return _client


def _choice_id(items: list[dict], value: str, label: str, id_field: str = "id") -> int:
    matches = [item for item in items if item[label].casefold() == value.casefold()]
    if len(matches) == 1:
        return matches[0][id_field]
    available = ", ".join(sorted(item[label] for item in items)) or "none"
    if not matches:
        raise ValueError(f"{label.replace('_', ' ').title()} '{value}' not found. Available: {available}")
    raise ValueError(f"{label.replace('_', ' ').title()} '{value}' is ambiguous. Available: {available}")


def _members(client: TaigaClient, project_id: int) -> list[dict]:
    return client.get(f"/api/v1/projects/{project_id}/members")


def _resolve_assignee(members: list[dict], username: str) -> int:
    return _choice_id(members, username, "username")


def _resolve_status(statuses: list[dict], name: str) -> int:
    return _choice_id(statuses, name, "name")


def _resolve_points(
    estimates: list[PointEstimate], roles: list[dict], points: list[dict]
) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for estimate in estimates:
        role_id = _choice_id(roles, estimate.role, "name")
        matches = [point for point in points if float(point["value"]) == estimate.value]
        if len(matches) != 1:
            available = ", ".join(str(point["value"]) for point in points) or "none"
            raise ValueError(
                f"Point value '{estimate.value}' not found uniquely. Available: {available}"
            )
        resolved[str(role_id)] = matches[0]["id"]
    return resolved


def _patch_current(client: TaigaClient, entity_type: str, entity_id: int, changes: dict) -> dict:
    current = client.get_entity_with_version(entity_type, entity_id)
    return client.patch(
        f"/api/v1/{entity_type}/{entity_id}",
        {**changes, "version": current["version"]},
    )


def _marker(kind: str, plan_key: str, key: str = "") -> str:
    suffix = f":{key}" if key else ""
    return f"[course:{plan_key}:{kind}{suffix}]"


def _marked_subject(marker: str, subject: str) -> str:
    return f"{marker} {subject}"


def _summary_item(item: dict) -> dict:
    return {"id": item["id"], "subject": item.get("subject", item.get("name", ""))}


@mcp.tool()
def list_projects() -> list[dict]:
    """List all Taiga projects accessible to the authenticated user."""
    client = get_client()
    user = client.get("/api/v1/users/me")
    projects = client.get(f"/api/v1/projects?member={user['id']}")
    return [{"id": p["id"], "name": p["name"], "slug": p["slug"]} for p in projects]


@mcp.tool()
def list_epics(project_id: int) -> list[dict]:
    """List epics in a Taiga project with concise planning details."""
    client = get_client()
    epics = client.get(f"/api/v1/epics?project={project_id}")
    return [
        {
            "id": epic["id"],
            "ref": epic.get("ref"),
            "subject": epic["subject"],
            "status": (epic.get("status_extra_info") or {}).get("name", ""),
            "user_story_count": epic.get("user_stories_counts", 0),
            "url": f"{client.base_url}/project/{epic['project_extra_info']['slug']}/epic/{epic.get('ref')}",
        }
        for epic in epics
    ]


@mcp.tool()
def create_epic(project_id: int, subject: str, description: str = "") -> dict:
    """Create an epic in a Taiga project."""
    client = get_client()
    data = {"project": project_id, "subject": subject}
    if description:
        data["description"] = description
    epic = client.post("/api/v1/epics", data)
    return {
        "id": epic["id"],
        "ref": epic.get("ref"),
        "subject": epic["subject"],
        "url": f"{client.base_url}/project/{epic['project_extra_info']['slug']}/epic/{epic.get('ref')}",
    }


@mcp.tool()
def create_user_story(project_id: int, subject: str, description: str = "") -> dict:
    """Create a user story in a Taiga project."""
    client = get_client()
    data = {"project": project_id, "subject": subject}
    if description:
        data["description"] = description
    story = client.post("/api/v1/userstories", data)
    return {
        "id": story["id"],
        "ref": story.get("ref"),
        "subject": story["subject"],
        "url": f"{client.base_url}/project/{story['project_extra_info']['slug']}/us/{story.get('ref')}",
    }


@mcp.tool()
def link_story_to_epic(epic_id: int, user_story_id: int) -> dict:
    """Link an existing user story to an epic."""
    client = get_client()
    relation = client.post(
        f"/api/v1/epics/{epic_id}/related_userstories",
        {"epic": epic_id, "user_story": user_story_id},
    )
    return {
        "epic_id": relation["epic"],
        "user_story_id": relation["user_story"],
        "order": relation.get("order"),
        "linked": True,
    }


@mcp.tool()
def list_milestones(project_id: int) -> list[dict]:
    """List milestones (sprints) in a project."""
    milestones = get_client().get(f"/api/v1/milestones?project={project_id}")
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "start_date": item["estimated_start"],
            "end_date": item["estimated_finish"],
            "closed": item.get("closed", False),
            "order": item.get("order"),
        }
        for item in milestones
    ]


@mcp.tool()
def create_milestone(project_id: int, name: str, start_date: date, end_date: date) -> dict:
    """Create a milestone (sprint) with inclusive start and end dates."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    milestone = get_client().post(
        "/api/v1/milestones",
        {
            "project": project_id,
            "name": name,
            "estimated_start": start_date.isoformat(),
            "estimated_finish": end_date.isoformat(),
        },
    )
    return {"id": milestone["id"], "name": milestone["name"]}


@mcp.tool()
def update_milestone(
    milestone_id: int,
    name: str = "",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Update selected milestone fields using Taiga optimistic concurrency."""
    changes: dict = {}
    if name:
        changes["name"] = name
    if start_date:
        changes["estimated_start"] = start_date.isoformat()
    if end_date:
        changes["estimated_finish"] = end_date.isoformat()
    if not changes:
        raise ValueError("At least one milestone field must be supplied")
    client = get_client()
    current = client.get_entity_with_version("milestones", milestone_id)
    effective_start = start_date or date.fromisoformat(current["estimated_start"])
    effective_end = end_date or date.fromisoformat(current["estimated_finish"])
    if effective_end < effective_start:
        raise ValueError("end_date must be on or after start_date")
    updated = client.patch(
        f"/api/v1/milestones/{milestone_id}",
        {**changes, "version": current["version"]},
    )
    return {"id": updated["id"], "name": updated["name"], "updated": sorted(changes)}


@mcp.tool()
def list_user_stories(project_id: int, milestone_id: int | None = None) -> list[dict]:
    """List project user stories, optionally restricted to a milestone."""
    path = f"/api/v1/userstories?project={project_id}"
    if milestone_id is not None:
        path += f"&milestone={milestone_id}"
    stories = get_client().get(path)
    return [
        {
            "id": story["id"],
            "ref": story.get("ref"),
            "subject": story["subject"],
            "status": (story.get("status_extra_info") or {}).get("name", ""),
            "milestone": (story.get("milestone_extra_info") or {}).get("name"),
            "assigned_to": (story.get("assigned_to_extra_info") or {}).get("username"),
            "tags": story.get("tags", []),
            "points": story.get("points", {}),
            "sprint_order": story.get("sprint_order"),
        }
        for story in stories
    ]


@mcp.tool()
def update_user_story(
    user_story_id: int,
    subject: str = "",
    status_name: str = "",
    milestone_id: int | None = None,
    assignee_username: str = "",
    tags: list[str] | None = None,
    points: list[PointEstimate] | None = None,
    sprint_order: int | None = None,
) -> dict:
    """Update selected user-story planning fields using names where useful."""
    client = get_client()
    current = client.get_entity_with_version("userstories", user_story_id)
    project_id = current["project"]
    changes: dict = {}
    if subject:
        changes["subject"] = subject
    if status_name:
        changes["status"] = _resolve_status(
            client.get(f"/api/v1/userstory-statuses?project={project_id}"), status_name
        )
    if milestone_id is not None:
        changes["milestone"] = milestone_id or None
    if assignee_username:
        changes["assigned_to"] = _resolve_assignee(_members(client, project_id), assignee_username)
    if tags is not None:
        changes["tags"] = tags
    if points is not None:
        changes["points"] = _resolve_points(
            points,
            client.get(f"/api/v1/roles?project={project_id}"),
            client.get(f"/api/v1/points?project={project_id}"),
        )
    if sprint_order is not None:
        changes["sprint_order"] = sprint_order
    if not changes:
        raise ValueError("At least one user-story field must be supplied")
    updated = _patch_current(client, "userstories", user_story_id, changes)
    return {"id": updated["id"], "subject": updated["subject"], "updated": sorted(changes)}


@mcp.tool()
def create_task(
    project_id: int,
    user_story_id: int,
    subject: str,
    description: str = "",
    status_name: str = "",
    assignee_username: str = "",
    tags: list[str] | None = None,
    order: int | None = None,
) -> dict:
    """Create a task under a user story with optional planning metadata."""
    client = get_client()
    data: dict = {"project": project_id, "user_story": user_story_id, "subject": subject}
    if description:
        data["description"] = description
    if status_name:
        data["status"] = _resolve_status(
            client.get(f"/api/v1/task-statuses?project={project_id}"), status_name
        )
    if assignee_username:
        data["assigned_to"] = _resolve_assignee(_members(client, project_id), assignee_username)
    if tags is not None:
        data["tags"] = tags
    if order is not None:
        data["us_order"] = order
    task = client.post("/api/v1/tasks", data)
    return _summary_item(task)


@mcp.tool()
def list_tasks(project_id: int, user_story_id: int | None = None) -> list[dict]:
    """List project tasks, optionally restricted to a user story."""
    path = f"/api/v1/tasks?project={project_id}"
    if user_story_id is not None:
        path += f"&user_story={user_story_id}"
    tasks = get_client().get(path)
    return [
        {
            "id": task["id"],
            "ref": task.get("ref"),
            "subject": task["subject"],
            "user_story": task.get("user_story"),
            "status": (task.get("status_extra_info") or {}).get("name", ""),
            "assigned_to": (task.get("assigned_to_extra_info") or {}).get("username"),
            "tags": task.get("tags", []),
            "order": task.get("us_order"),
        }
        for task in tasks
    ]


@mcp.tool()
def update_task(
    task_id: int,
    subject: str = "",
    status_name: str = "",
    assignee_username: str = "",
    tags: list[str] | None = None,
    order: int | None = None,
) -> dict:
    """Update selected task planning fields using Taiga optimistic concurrency."""
    client = get_client()
    current = client.get_entity_with_version("tasks", task_id)
    project_id = current["project"]
    changes: dict = {}
    if subject:
        changes["subject"] = subject
    if status_name:
        changes["status"] = _resolve_status(
            client.get(f"/api/v1/task-statuses?project={project_id}"), status_name
        )
    if assignee_username:
        changes["assigned_to"] = _resolve_assignee(_members(client, project_id), assignee_username)
    if tags is not None:
        changes["tags"] = tags
    if order is not None:
        changes["us_order"] = order
    if not changes:
        raise ValueError("At least one task field must be supplied")
    updated = _patch_current(client, "tasks", task_id, changes)
    return {"id": updated["id"], "subject": updated["subject"], "updated": sorted(changes)}


def _course_operations(plan: CoursePlan) -> list[dict]:
    operations = [
        {
            "action": "reconcile",
            "type": "epic",
            "key": plan.plan_key,
            "subject": _marked_subject(_marker("epic", plan.plan_key), plan.epic_subject),
        }
    ]
    for week_index, week in enumerate(plan.weeks, 1):
        operations.append(
            {
                "action": "reconcile",
                "type": "milestone",
                "key": week.key,
                "name": _marked_subject(_marker("week", plan.plan_key, week.key), week.name),
                "start_date": week.start_date.isoformat(),
                "end_date": week.end_date.isoformat(),
                "order": week_index,
            }
        )
        for story_index, story in enumerate(week.stories, 1):
            marker = _marker("story", plan.plan_key, story.key)
            operations.append(
                {
                    "action": "reconcile",
                    "type": "user_story",
                    "key": story.key,
                    "week": week.key,
                    "subject": _marked_subject(marker, story.subject),
                    "kind": story.kind,
                    "order": story_index,
                    "task_count": len(story.tasks),
                }
            )
            for task_index, task in enumerate(story.tasks, 1):
                operations.append(
                    {
                        "action": "reconcile",
                        "type": "task",
                        "key": task.key,
                        "story": story.key,
                        "subject": _marked_subject(
                            _marker("task", plan.plan_key, f"{story.key}:{task.key}"), task.subject
                        ),
                        "order": task_index,
                    }
                )
    return operations


@mcp.tool()
def preview_course_plan(plan: CoursePlan) -> dict:
    """Validate and deterministically preview a course plan without any Taiga calls."""
    operations = _course_operations(plan)
    return {
        "valid": True,
        "project_id": plan.project_id,
        "plan_key": plan.plan_key,
        "counts": {
            "milestones": len(plan.weeks),
            "stories": sum(len(week.stories) for week in plan.weeks),
            "tasks": sum(len(story.tasks) for week in plan.weeks for story in week.stories),
        },
        "operations": operations,
        "mutations": 0,
    }


def _course_preflight(client: TaigaClient, plan: CoursePlan) -> dict:
    members = _members(client, plan.project_id)
    story_statuses = client.get(f"/api/v1/userstory-statuses?project={plan.project_id}")
    task_statuses = client.get(f"/api/v1/task-statuses?project={plan.project_id}")
    roles = client.get(f"/api/v1/roles?project={plan.project_id}")
    points = client.get(f"/api/v1/points?project={plan.project_id}")
    resolved: dict = {"stories": {}, "tasks": {}}
    for week in plan.weeks:
        for story in week.stories:
            story_values: dict = {}
            if story.status:
                story_values["status"] = _resolve_status(story_statuses, story.status)
            if story.assignee:
                story_values["assigned_to"] = _resolve_assignee(members, story.assignee)
            if story.points:
                story_values["points"] = _resolve_points(story.points, roles, points)
            resolved["stories"][story.key] = story_values
            for task in story.tasks:
                task_values: dict = {}
                if task.status:
                    task_values["status"] = _resolve_status(task_statuses, task.status)
                if task.assignee:
                    task_values["assigned_to"] = _resolve_assignee(members, task.assignee)
                resolved["tasks"][(story.key, task.key)] = task_values
    return resolved


def _find_marked(items: list[dict], field: str, marker: str) -> dict | None:
    matches = [item for item in items if item.get(field, "").startswith(marker + " ")]
    if len(matches) > 1:
        raise ValueError(f"Multiple Taiga objects use stable marker {marker}")
    return matches[0] if matches else None


def _record(summary: dict, action: str, kind: str, item: dict) -> None:
    summary[action].append({"type": kind, **_summary_item(item)})


@mcp.tool()
def apply_course_plan(plan: CoursePlan) -> dict:
    """Idempotently reconcile a validated course plan, stopping on the first remote failure."""
    _course_operations(plan)
    client = get_client()
    resolved = _course_preflight(client, plan)
    existing_epics = client.get(f"/api/v1/epics?project={plan.project_id}")
    existing_milestones = client.get(f"/api/v1/milestones?project={plan.project_id}")
    existing_stories = client.get(f"/api/v1/userstories?project={plan.project_id}")

    # Reject ambiguous reconciliation state before the first mutation.
    _find_marked(existing_epics, "subject", _marker("epic", plan.plan_key))
    existing_tasks_by_story: dict[str, list[dict]] = {}
    existing_tasks: list[dict] = []
    for week in plan.weeks:
        _find_marked(existing_milestones, "name", _marker("week", plan.plan_key, week.key))
        for story in week.stories:
            existing_story = _find_marked(
                existing_stories, "subject", _marker("story", plan.plan_key, story.key)
            )
            story_tasks = (
                client.get(
                    f"/api/v1/tasks?project={plan.project_id}&user_story={existing_story['id']}"
                )
                if existing_story
                else []
            )
            existing_tasks_by_story[story.key] = story_tasks
            existing_tasks.extend(story_tasks)
    for week in plan.weeks:
        for story in week.stories:
            for task in story.tasks:
                _find_marked(
                    existing_tasks,
                    "subject",
                    _marker("task", plan.plan_key, f"{story.key}:{task.key}"),
                )
    summary: dict = {"created": [], "updated": [], "skipped": [], "failed": []}
    operation = {"type": "epic", "key": plan.plan_key}

    try:
        epic_marker = _marker("epic", plan.plan_key)
        epic_subject = _marked_subject(epic_marker, plan.epic_subject)
        epic = _find_marked(existing_epics, "subject", epic_marker)
        if epic is None:
            epic = client.post(
                "/api/v1/epics",
                {"project": plan.project_id, "subject": epic_subject, "description": plan.epic_description},
            )
            _record(summary, "created", "epic", epic)
        elif epic.get("subject") != epic_subject or epic.get("description", "") != plan.epic_description:
            epic = _patch_current(
                client,
                "epics",
                epic["id"],
                {"subject": epic_subject, "description": plan.epic_description},
            )
            _record(summary, "updated", "epic", epic)
        else:
            _record(summary, "skipped", "epic", epic)

        milestone_by_key: dict[str, dict] = {}
        for week_index, week in enumerate(plan.weeks, 1):
            operation = {"type": "milestone", "key": week.key}
            marker = _marker("week", plan.plan_key, week.key)
            name = _marked_subject(marker, week.name)
            desired = {
                "name": name,
                "estimated_start": week.start_date.isoformat(),
                "estimated_finish": week.end_date.isoformat(),
                "order": week_index,
            }
            milestone = _find_marked(existing_milestones, "name", marker)
            if milestone is None:
                milestone = client.post("/api/v1/milestones", {"project": plan.project_id, **desired})
                _record(summary, "created", "milestone", milestone)
            elif any(milestone.get(key) != value for key, value in desired.items()):
                milestone = _patch_current(client, "milestones", milestone["id"], desired)
                _record(summary, "updated", "milestone", milestone)
            else:
                _record(summary, "skipped", "milestone", milestone)
            milestone_by_key[week.key] = milestone

        for week in plan.weeks:
            milestone = milestone_by_key[week.key]
            for story_index, story_spec in enumerate(week.stories, 1):
                operation = {"type": "user_story", "key": story_spec.key}
                marker = _marker("story", plan.plan_key, story_spec.key)
                subject = _marked_subject(marker, story_spec.subject)
                desired = {
                    "subject": subject,
                    "description": story_spec.description,
                    "milestone": milestone["id"],
                    "tags": list(dict.fromkeys([story_spec.kind, *story_spec.tags])),
                    "sprint_order": story_index,
                    **resolved["stories"][story_spec.key],
                }
                story = _find_marked(existing_stories, "subject", marker)
                if story is None:
                    story = client.post("/api/v1/userstories", {"project": plan.project_id, **desired})
                    existing_stories.append(story)
                    _record(summary, "created", "user_story", story)
                elif any(story.get(key) != value for key, value in desired.items()):
                    story = _patch_current(client, "userstories", story["id"], desired)
                    _record(summary, "updated", "user_story", story)
                else:
                    _record(summary, "skipped", "user_story", story)

                relations = client.get(f"/api/v1/epics/{epic['id']}/related_userstories")
                if not any(relation.get("user_story") == story["id"] for relation in relations):
                    client.post(
                        f"/api/v1/epics/{epic['id']}/related_userstories",
                        {"epic": epic["id"], "user_story": story["id"]},
                    )
                    summary["created"].append(
                        {"type": "epic_link", "epic_id": epic["id"], "user_story_id": story["id"]}
                    )
                else:
                    summary["skipped"].append(
                        {"type": "epic_link", "epic_id": epic["id"], "user_story_id": story["id"]}
                    )

                story_tasks = existing_tasks_by_story[story_spec.key]
                for task_index, task_spec in enumerate(story_spec.tasks, 1):
                    operation = {
                        "type": "task",
                        "key": task_spec.key,
                        "user_story_key": story_spec.key,
                    }
                    task_marker = _marker("task", plan.plan_key, f"{story_spec.key}:{task_spec.key}")
                    task_subject = _marked_subject(task_marker, task_spec.subject)
                    task_desired = {
                        "subject": task_subject,
                        "description": task_spec.description,
                        "milestone": milestone["id"],
                        "tags": task_spec.tags,
                        "us_order": task_index,
                        **resolved["tasks"][(story_spec.key, task_spec.key)],
                    }
                    task = _find_marked(story_tasks, "subject", task_marker)
                    if task is None:
                        task = client.post(
                            "/api/v1/tasks",
                            {
                                "project": plan.project_id,
                                "user_story": story["id"],
                                **task_desired,
                            },
                        )
                        _record(summary, "created", "task", task)
                    elif any(task.get(key) != value for key, value in task_desired.items()):
                        task = _patch_current(client, "tasks", task["id"], task_desired)
                        _record(summary, "updated", "task", task)
                    else:
                        _record(summary, "skipped", "task", task)
    except Exception as exc:
        summary["failed"].append({**operation, "error": type(exc).__name__})

    summary["ok"] = not summary["failed"]
    summary["retry_safe"] = True
    summary["counts"] = {key: len(value) for key, value in summary.items() if isinstance(value, list)}
    return summary


@mcp.tool()
def create_issue(project_id: int, subject: str, description: str = "") -> dict:
    """Create a new issue in a Taiga project."""
    client = get_client()
    data = {"project": project_id, "subject": subject}
    if description:
        data["description"] = description
    issue = client.post("/api/v1/issues", data)
    return {
        "id": issue["id"],
        "ref": issue.get("ref"),
        "subject": issue["subject"],
        "url": f"{client.base_url}/project/{issue['project_extra_info']['slug']}/issue/{issue.get('ref')}",
    }


@mcp.tool()
def move_status(issue_id: int, status_name: str) -> dict:
    """Move an issue to a new status by name."""
    client = get_client()
    issue = client.get_entity_with_version("issues", issue_id)
    statuses = client.get(f"/api/v1/issue-statuses?project={issue['project']}")
    target_id = _resolve_status(statuses, status_name)
    updated = _patch_current(client, "issues", issue_id, {"status": target_id})
    return {"id": issue_id, "new_status": updated["status_extra_info"]["name"]}


@mcp.tool()
def add_comment(issue_id: int, comment: str) -> dict:
    """Add a comment to an existing Taiga issue."""
    updated = _patch_current(get_client(), "issues", issue_id, {"comment": comment})
    return {"issue_id": issue_id, "comment_added": True, "new_version": updated["version"]}


@mcp.tool()
def assign_user(issue_id: int, username: str) -> dict:
    """Assign a team member to an existing Taiga issue."""
    client = get_client()
    issue = client.get_entity_with_version("issues", issue_id)
    user_id = _resolve_assignee(_members(client, issue["project"]), username)
    updated = _patch_current(client, "issues", issue_id, {"assigned_to": user_id})
    assigned = updated.get("assigned_to_extra_info") or {}
    return {
        "issue_id": issue_id,
        "assigned_to": assigned.get("username", username),
        "full_name": assigned.get("full_name_display", ""),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
