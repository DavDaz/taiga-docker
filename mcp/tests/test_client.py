from unittest.mock import MagicMock

import httpx

from taiga_mcp.client import TaigaClient


def test_post_sends_json_with_bearer_auth(monkeypatch) -> None:
    monkeypatch.setenv("TAIGA_URL", "https://taiga.example/")
    monkeypatch.setenv("TAIGA_TOKEN", "test-token")
    response = MagicMock()
    response.json.return_value = {"id": 15}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(httpx, "post", post)
    client = TaigaClient()

    result = client.post("/api/v1/epics", {"project": 12, "subject": "Plan release"})

    post.assert_called_once_with(
        "https://taiga.example/api/v1/epics",
        json={"project": 12, "subject": "Plan release"},
        headers={"Authorization": "Bearer test-token"},
        timeout=10,
    )
    response.raise_for_status.assert_called_once_with()
    assert result == {"id": 15}
