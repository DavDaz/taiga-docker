from unittest.mock import MagicMock
from datetime import date

import httpx
import pytest

from taiga_mcp import server


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    client.base_url = "https://taiga.example"
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client


def test_members_uses_legacy_project_member_shape(client: MagicMock) -> None:
    members = [{"id": 9, "username": "alex"}]
    client.get.return_value = members

    assert server._members(client, 12) == members
    client.get.assert_called_once_with("/api/v1/projects/12/members")


@pytest.mark.parametrize(
    ("membership", "user_response", "expected"),
    [
        (
            {"id": 41, "user": 9, "user_extra_info": {"username": "alex"}},
            None,
            {"id": 9, "username": "alex"},
        ),
        (
            {"id": 41, "user": {"id": 9, "username": "alex"}},
            None,
            {"id": 9, "username": "alex"},
        ),
        (
            {"id": 41, "user": 9},
            {"id": 9, "username": "alex"},
            {"id": 9, "username": "alex"},
        ),
    ],
)
def test_members_falls_back_and_normalizes_memberships(
    client: MagicMock, membership: dict, user_response: dict | None, expected: dict
) -> None:
    request = httpx.Request("GET", "https://taiga.example/api/v1/projects/12/members")
    response = httpx.Response(404, request=request)
    responses = [
        httpx.HTTPStatusError("Not Found", request=request, response=response),
        [membership],
    ]
    if user_response:
        responses.append(user_response)
    client.get.side_effect = responses

    assert server._members(client, 12) == [expected]
    expected_paths = [
        "/api/v1/projects/12/members",
        "/api/v1/memberships?project=12",
    ]
    if user_response:
        expected_paths.append("/api/v1/users/9")
    assert [call.args[0] for call in client.get.call_args_list] == expected_paths


def test_members_does_not_hide_non_404_errors(client: MagicMock) -> None:
    request = httpx.Request("GET", "https://taiga.example/api/v1/projects/12/members")
    response = httpx.Response(403, request=request)
    error = httpx.HTTPStatusError("Forbidden", request=request, response=response)
    client.get.side_effect = error

    with pytest.raises(httpx.HTTPStatusError) as raised:
        server._members(client, 12)

    assert raised.value is error
    client.get.assert_called_once_with("/api/v1/projects/12/members")


def test_list_epics_returns_concise_project_scoped_results(client: MagicMock) -> None:
    client.get.return_value = [
        {
            "id": 15,
            "ref": 8,
            "subject": "Plan release",
            "status_extra_info": {"name": "In progress"},
            "user_stories_counts": 3,
            "project_extra_info": {"slug": "platform"},
            "description": "Not returned",
        }
    ]

    result = server.list_epics(12)

    client.get.assert_called_once_with("/api/v1/epics?project=12")
    assert result == [
        {
            "id": 15,
            "ref": 8,
            "subject": "Plan release",
            "status": "In progress",
            "user_story_count": 3,
            "url": "https://taiga.example/project/platform/epic/8",
        }
    ]


@pytest.mark.parametrize(
    ("tool", "path", "response", "expected_url"),
    [
        (
            server.create_epic,
            "/api/v1/epics",
            {"id": 15, "ref": 8, "subject": "Plan release", "project_extra_info": {"slug": "platform"}},
            "https://taiga.example/project/platform/epic/8",
        ),
        (
            server.create_user_story,
            "/api/v1/userstories",
            {"id": 21, "ref": 13, "subject": "Build endpoint", "project_extra_info": {"slug": "platform"}},
            "https://taiga.example/project/platform/us/13",
        ),
    ],
)
def test_create_planning_item_posts_required_and_optional_fields(
    client: MagicMock,
    tool,
    path: str,
    response: dict,
    expected_url: str,
) -> None:
    client.post.return_value = response

    result = tool(12, response["subject"], "Useful context")

    client.post.assert_called_once_with(
        path,
        {"project": 12, "subject": response["subject"], "description": "Useful context"},
    )
    assert result == {
        "id": response["id"],
        "ref": response["ref"],
        "subject": response["subject"],
        "url": expected_url,
    }


def test_create_epic_omits_empty_description(client: MagicMock) -> None:
    client.post.return_value = {
        "id": 15,
        "ref": 8,
        "subject": "Plan release",
        "project_extra_info": {"slug": "platform"},
    }

    server.create_epic(12, "Plan release")

    client.post.assert_called_once_with(
        "/api/v1/epics", {"project": 12, "subject": "Plan release"}
    )


def test_link_story_to_epic_creates_relation_without_version(client: MagicMock) -> None:
    client.post.return_value = {"epic": 15, "user_story": 21, "order": 4}

    result = server.link_story_to_epic(15, 21)

    client.post.assert_called_once_with(
        "/api/v1/epics/15/related_userstories",
        {"epic": 15, "user_story": 21},
    )
    assert result == {
        "epic_id": 15,
        "user_story_id": 21,
        "order": 4,
        "linked": True,
    }


def test_create_milestone_posts_taiga_date_payload(client: MagicMock) -> None:
    client.post.return_value = {"id": 31, "name": "Week 1"}

    result = server.create_milestone(12, "Week 1", date(2026, 9, 7), date(2026, 9, 13))

    client.post.assert_called_once_with(
        "/api/v1/milestones",
        {
            "project": 12,
            "name": "Week 1",
            "estimated_start": "2026-09-07",
            "estimated_finish": "2026-09-13",
        },
    )
    assert result == {"id": 31, "name": "Week 1"}


def test_update_task_resolves_names_and_fetches_version_immediately_before_patch(
    client: MagicMock,
) -> None:
    client.get_entity_with_version.side_effect = [
        {"id": 41, "project": 12, "version": 3},
        {"id": 41, "project": 12, "version": 4},
    ]
    client.get.side_effect = [
        [{"id": 7, "name": "Done"}],
        [{"id": 9, "username": "alex"}],
    ]
    client.patch.return_value = {"id": 41, "subject": "Build scene"}

    result = server.update_task(
        41,
        status_name="done",
        assignee_username="alex",
        tags=["lab"],
        order=20,
    )

    assert client.method_calls[-2].args == ("tasks", 41)
    assert client.method_calls[-1].args == (
        "/api/v1/tasks/41",
        {"status": 7, "assigned_to": 9, "tags": ["lab"], "us_order": 20, "version": 4},
    )
    assert result["updated"] == ["assigned_to", "status", "tags", "us_order"]


@pytest.mark.parametrize(
    ("current", "expected_payload"),
    [
        ({"id": 31}, {"name": "Unit 1"}),
        ({"id": 31, "version": None}, {"name": "Unit 1"}),
        ({"id": 31, "version": 6}, {"name": "Unit 1", "version": 6}),
    ],
)
def test_patch_current_omits_missing_version_and_preserves_present_version(
    client: MagicMock, current: dict, expected_payload: dict
) -> None:
    client.get_entity_with_version.return_value = current
    client.patch.return_value = {"id": 31, "name": "Unit 1"}

    server._patch_current(client, "milestones", 31, {"name": "Unit 1"})

    client.patch.assert_called_once_with("/api/v1/milestones/31", expected_payload)


def test_update_milestone_uses_current_version_and_validates_effective_dates(
    client: MagicMock,
) -> None:
    client.get_entity_with_version.return_value = {
        "version": 6,
        "estimated_start": "2026-09-07",
        "estimated_finish": "2026-09-13",
    }
    client.patch.return_value = {"id": 31, "name": "Unit 1"}

    server.update_milestone(31, end_date=date(2026, 9, 14))

    assert client.method_calls[-2].args == ("milestones", 31)
    assert client.method_calls[-1].args == (
        "/api/v1/milestones/31",
        {"estimated_finish": "2026-09-14", "version": 6},
    )


def test_update_story_resolves_points_and_planning_metadata(client: MagicMock) -> None:
    client.get_entity_with_version.side_effect = [
        {"project": 12, "version": 3},
        {"project": 12, "version": 4},
    ]
    client.get.side_effect = [
        [{"id": 5, "name": "Ready"}],
        [{"id": 9, "username": "alex"}],
        [{"id": 2, "name": "Developer"}],
        [
            {"id": 7, "value": None},
            {"id": 8, "value": 3},
            {"id": 9, "value": "unavailable"},
        ],
    ]
    client.patch.return_value = {"id": 21, "subject": "Lesson"}

    server.update_user_story(
        21,
        status_name="ready",
        milestone_id=31,
        assignee_username="alex",
        tags=["lesson"],
        points=[server.PointEstimate(role="developer", value=3)],
        sprint_order=10,
    )

    assert client.method_calls[-2].args == ("userstories", 21)
    assert client.method_calls[-1].args == (
        "/api/v1/userstories/21",
        {
            "status": 5,
            "milestone": 31,
            "assigned_to": 9,
            "tags": ["lesson"],
            "points": {"2": 8},
            "sprint_order": 10,
            "version": 4,
        },
    )


def test_update_story_reports_no_valid_point_match_without_patch(client: MagicMock) -> None:
    client.get_entity_with_version.return_value = {"project": 12, "version": 3}
    client.get.side_effect = [
        [{"id": 2, "name": "Developer"}],
        [{"id": 7, "value": None}, {"id": 8, "value": "unavailable"}],
    ]

    with pytest.raises(
        ValueError,
        match="Point value '3.0' not found uniquely. Available: None, unavailable",
    ):
        server.update_user_story(
            21,
            points=[server.PointEstimate(role="developer", value=3)],
        )

    client.patch.assert_not_called()


def test_status_resolution_failure_lists_choices_without_patch(client: MagicMock) -> None:
    client.get_entity_with_version.return_value = {"id": 21, "project": 12, "version": 2}
    client.get.return_value = [{"id": 1, "name": "New"}, {"id": 2, "name": "Done"}]

    with pytest.raises(ValueError, match="Available: Done, New"):
        server.update_user_story(21, status_name="Missing")

    client.patch.assert_not_called()


def _plan() -> server.CoursePlan:
    return server.CoursePlan(
        project_id=12,
        plan_key="create-with-code",
        epic_subject="Create with Code",
        weeks=[
            server.CourseWeek(
                key="week-1",
                name="Unit 1",
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 13),
                stories=[
                    server.CourseStory(
                        key="lesson-1",
                        subject="Player control",
                        kind="lesson",
                        tags=["unity"],
                        tasks=[server.CourseTask(key="practice", subject="Practice")],
                    )
                ],
            )
        ],
    )


def test_preview_course_plan_is_deterministic_and_performs_no_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_client = MagicMock(side_effect=AssertionError("preview must not access Taiga"))
    monkeypatch.setattr(server, "get_client", get_client)

    first = server.preview_course_plan(_plan())
    second = server.preview_course_plan(_plan())

    assert first == second
    assert first["mutations"] == 0
    assert first["counts"] == {"milestones": 1, "stories": 1, "tasks": 1}
    assert first["operations"][0] == {
        "action": "reconcile",
        "type": "epic",
        "key": "create-with-code",
        "subject": "Create with Code",
        "identity": "[course:create-with-code:epic]",
    }
    assert first["operations"][1]["name"] == "Unit 1"
    assert first["operations"][2]["subject"] == "Player control"
    assert first["operations"][3]["subject"] == "Practice"
    get_client.assert_not_called()


def test_course_plan_rejects_invalid_dates_and_duplicate_story_keys_before_apply(
    client: MagicMock,
) -> None:
    with pytest.raises(ValueError, match="end_date must be on or after start_date"):
        server.CourseWeek(
            key="week-1",
            name="Unit 1",
            start_date=date(2026, 9, 14),
            end_date=date(2026, 9, 13),
            stories=[server.CourseStory(key="lesson", subject="One", kind="lesson")],
        )

    client.get.assert_not_called()
    client.post.assert_not_called()
    client.patch.assert_not_called()


def test_course_plan_rejects_duplicate_task_markers_before_client_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_client = MagicMock(side_effect=AssertionError("invalid plans must not access Taiga"))
    monkeypatch.setattr(server, "get_client", get_client)

    with pytest.raises(ValueError, match="task stable markers must be unique across the plan"):
        server.CoursePlan(
            project_id=12,
            plan_key="create-with-code",
            epic_subject="Create with Code",
            weeks=[
                server.CourseWeek(
                    key="week-1",
                    name="Unit 1",
                    start_date=date(2026, 9, 7),
                    end_date=date(2026, 9, 13),
                    stories=[
                        server.CourseStory(
                            key="lesson",
                            subject="Lesson",
                            kind="lesson",
                            tasks=[
                                server.CourseTask(key="practice", subject="First"),
                                server.CourseTask(key="practice", subject="Duplicate"),
                            ],
                        )
                    ],
                )
            ],
        )

    get_client.assert_not_called()


def test_apply_course_plan_rejects_duplicate_task_markers_before_mutation(
    client: MagicMock,
) -> None:
    plan = _plan()
    plan.weeks[0].stories.append(
        server.CourseStory(key="lesson-2", subject="Second lesson", kind="lesson")
    )
    marker = "[course:create-with-code:task:lesson-1:practice]"

    def get(path: str):
        if path in {
            "/api/v1/projects/12/members",
            "/api/v1/userstory-statuses?project=12",
            "/api/v1/task-statuses?project=12",
            "/api/v1/roles?project=12",
            "/api/v1/points?project=12",
            "/api/v1/epics?project=12",
            "/api/v1/milestones?project=12",
        }:
            return []
        if path == "/api/v1/userstories?project=12":
            return [
                {"id": 21, "subject": "[course:create-with-code:story:lesson-1] First"},
                {"id": 22, "subject": "[course:create-with-code:story:lesson-2] Second"},
            ]
        if path == "/api/v1/tasks?project=12&user_story=21":
            return [{"id": 31, "subject": f"{marker} First"}]
        if path == "/api/v1/tasks?project=12&user_story=22":
            return [{"id": 32, "subject": f"{marker} Duplicate"}]
        raise AssertionError(path)

    client.get.side_effect = get

    with pytest.raises(ValueError, match="Multiple Taiga objects use stable marker"):
        server.apply_course_plan(plan)

    client.post.assert_not_called()
    client.patch.assert_not_called()
    client.get_entity_with_version.assert_not_called()


def test_apply_course_plan_resolves_all_references_before_mutation(client: MagicMock) -> None:
    plan = _plan()
    plan.weeks[0].stories[0].status = "Unknown"
    client.get.side_effect = [[], [{"id": 1, "name": "Ready"}], [], [], []]

    with pytest.raises(ValueError, match="Available: Ready"):
        server.apply_course_plan(plan)

    client.post.assert_not_called()
    client.patch.assert_not_called()


def test_course_preflight_ignores_unavailable_points_and_resolves_valid_match(
    client: MagicMock,
) -> None:
    plan = _plan()
    plan.weeks[0].stories[0].points = [server.PointEstimate(role="developer", value=3)]
    client.get.side_effect = [
        [],
        [],
        [],
        [{"id": 2, "name": "Developer"}],
        [
            {"id": 7, "value": None},
            {"id": 8, "value": 3},
            {"id": 9, "value": "unavailable"},
        ],
    ]

    resolved = server._course_preflight(client, plan)

    assert resolved["stories"]["lesson-1"]["points"] == {"2": 8}
    client.post.assert_not_called()
    client.patch.assert_not_called()


def test_course_metadata_envelope_preserves_authored_description() -> None:
    marker = "[course:create-with-code:story:lesson-1]"
    description = "Authored **Markdown**\n\nwith whitespace preserved."

    stored = server._with_course_metadata(marker, description)

    assert stored == f"<!-- {marker} -->\n{description}"
    assert server._with_course_metadata(marker, stored) == stored
    assert server._has_course_metadata(stored, marker) is True


def test_course_metadata_duplicate_identity_aborts() -> None:
    marker = "[course:create-with-code:story:lesson-1]"
    items = [
        {"id": 1, "subject": "First", "description": f"<!-- {marker} -->"},
        {"id": 2, "subject": "Second", "description": f"<!-- {marker} -->"},
    ]

    with pytest.raises(ValueError, match="Multiple Taiga objects use stable marker"):
        server._find_marked(items, "subject", marker)


def test_apply_course_plan_migrates_legacy_markers_without_duplicates(client: MagicMock) -> None:
    plan = _plan()
    plan.epic_description = "Epic context"
    plan.weeks[0].stories[0].description = "Story context"
    plan.weeks[0].stories[0].tasks[0].description = "Task context"
    epic_marker = "[course:create-with-code:epic]"
    week_marker = "[course:create-with-code:week:week-1]"
    story_marker = "[course:create-with-code:story:lesson-1]"
    task_marker = "[course:create-with-code:task:lesson-1:practice]"
    state = {
        "epics": [{"id": 10, "subject": f"{epic_marker} Old title", "description": "Epic context"}],
        "milestones": [{"id": 11, "name": f"{week_marker} Old title", "estimated_start": "2026-09-07", "estimated_finish": "2026-09-13", "order": 1}],
        "stories": [{"id": 12, "subject": f"{story_marker} Old title", "description": "Story context", "milestone": 11, "tags": ["lesson", "unity"], "sprint_order": 1}],
        "tasks": [{"id": 13, "subject": f"{task_marker} Old title", "description": "Task context", "milestone": 11, "tags": [], "us_order": 1}],
    }

    def get(path: str):
        if path == "/api/v1/projects/12/members" or path.endswith(("statuses?project=12", "roles?project=12", "points?project=12")):
            return []
        if path == "/api/v1/epics?project=12":
            return state["epics"]
        if path == "/api/v1/milestones?project=12":
            return state["milestones"]
        if path == "/api/v1/userstories?project=12":
            return state["stories"]
        if path == "/api/v1/tasks?project=12&user_story=12":
            return state["tasks"]
        if path == "/api/v1/epics/10/related_userstories":
            return [{"epic": 10, "user_story": 12}]
        raise AssertionError(path)

    def get_entity(entity_type: str, entity_id: int) -> dict:
        collection = {"epics": "epics", "milestones": "milestones", "userstories": "stories", "tasks": "tasks"}[entity_type]
        return {**next(item for item in state[collection] if item["id"] == entity_id), "version": 1}

    def patch(path: str, data: dict) -> dict:
        entity_type, entity_id = path.rsplit("/", 1)
        collection = {"epics": "epics", "milestones": "milestones", "userstories": "stories", "tasks": "tasks"}[entity_type.split("/")[-1]]
        item = next(item for item in state[collection] if item["id"] == int(entity_id))
        item.update({key: value for key, value in data.items() if key != "version"})
        return item

    client.get.side_effect = get
    client.get_entity_with_version.side_effect = get_entity
    client.patch.side_effect = patch

    result = server.apply_course_plan(plan)

    assert result["ok"] is True
    assert result["counts"] == {"created": 0, "updated": 4, "skipped": 1, "failed": 0}
    assert state["epics"][0]["subject"] == "Create with Code"
    assert state["stories"][0]["subject"] == "Player control"
    assert state["tasks"][0]["subject"] == "Practice"
    assert state["milestones"][0]["name"] == "Unit 1"
    assert state["milestones"][0]["slug"] == "course-create-with-code-week-week-1"
    assert state["epics"][0]["description"] == f"<!-- {epic_marker} -->\nEpic context"
    assert state["stories"][0]["description"] == f"<!-- {story_marker} -->\nStory context"
    assert state["tasks"][0]["description"] == f"<!-- {task_marker} -->\nTask context"
    client.post.assert_not_called()


def test_apply_course_plan_is_retry_safe_after_partial_failure(client: MagicMock) -> None:
    state = {"epics": [], "milestones": [], "stories": [], "tasks": [], "relations": []}
    next_ids = iter(range(100, 110))
    fail_task_once = True

    def get(path: str):
        if path == "/api/v1/projects/12/members":
            return []
        if path in {
            "/api/v1/userstory-statuses?project=12",
            "/api/v1/task-statuses?project=12",
            "/api/v1/roles?project=12",
            "/api/v1/points?project=12",
        }:
            return []
        if path == "/api/v1/epics?project=12":
            return list(state["epics"])
        if path == "/api/v1/milestones?project=12":
            return list(state["milestones"])
        if path == "/api/v1/userstories?project=12":
            return list(state["stories"])
        if path.startswith("/api/v1/epics/"):
            return list(state["relations"])
        if path.startswith("/api/v1/tasks?project=12&user_story="):
            return list(state["tasks"])
        raise AssertionError(path)

    def post(path: str, data: dict):
        nonlocal fail_task_once
        if path == "/api/v1/tasks" and fail_task_once:
            fail_task_once = False
            raise RuntimeError("temporary remote failure")
        if path.endswith("/related_userstories"):
            relation = dict(data)
            state["relations"].append(relation)
            return relation
        kind = {
            "/api/v1/epics": "epics",
            "/api/v1/milestones": "milestones",
            "/api/v1/userstories": "stories",
            "/api/v1/tasks": "tasks",
        }[path]
        item = {"id": next(next_ids), **data}
        state[kind].append(item)
        return item

    client.get.side_effect = get
    client.post.side_effect = post

    first = server.apply_course_plan(_plan())
    second = server.apply_course_plan(_plan())

    assert first["ok"] is False
    assert first["retry_safe"] is True
    assert first["counts"] == {"created": 4, "updated": 0, "skipped": 0, "failed": 1}
    assert first["failed"] == [
        {"type": "task", "key": "practice", "user_story_key": "lesson-1", "error": "RuntimeError"}
    ]
    assert second["ok"] is True
    assert second["counts"] == {"created": 1, "updated": 0, "skipped": 4, "failed": 0}
    assert len(state["epics"]) == len(state["milestones"]) == len(state["stories"]) == 1
    assert len(state["tasks"]) == len(state["relations"]) == 1
    assert state["epics"][0]["subject"] == "Create with Code"
    assert state["epics"][0]["description"] == "<!-- [course:create-with-code:epic] -->"
    assert state["milestones"][0]["name"] == "Unit 1"
    assert state["milestones"][0]["slug"] == "course-create-with-code-week-week-1"
    assert state["stories"][0]["subject"] == "Player control"
    assert state["stories"][0]["description"] == "<!-- [course:create-with-code:story:lesson-1] -->"
    assert state["tasks"][0]["subject"] == "Practice"
    assert state["tasks"][0]["description"] == "<!-- [course:create-with-code:task:lesson-1:practice] -->"
