"""
TaigaClient — minimal HTTP client for Taiga REST API v1.

Auth flow:
  - If TAIGA_TOKEN env var is set, use it directly as Bearer token
  - Otherwise POST /api/v1/auth with {type: "normal", username, password}
    and cache the returned auth_token

All mutations (PATCH) must read the entity's current `version` first.
"""
import os
import httpx


class TaigaClient:
    def __init__(self):
        self.base_url = os.environ.get("TAIGA_URL", "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("TAIGA_URL environment variable is required")
        self._token: str | None = os.environ.get("TAIGA_TOKEN")
        self._username = os.environ.get("TAIGA_USERNAME", "")
        self._password = os.environ.get("TAIGA_PASSWORD", "")

    def _ensure_auth(self) -> str:
        if self._token:
            return self._token
        resp = httpx.post(
            f"{self.base_url}/api/v1/auth",
            json={"type": "normal", "username": self._username, "password": self._password},
            timeout=10,
        )
        resp.raise_for_status()
        self._token = resp.json()["auth_token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._ensure_auth()}"}

    def get(self, path: str) -> dict:
        resp = httpx.get(f"{self.base_url}{path}", headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict) -> dict:
        resp = httpx.post(f"{self.base_url}{path}", json=data, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def patch(self, path: str, data: dict) -> dict:
        resp = httpx.patch(f"{self.base_url}{path}", json=data, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_entity_with_version(self, entity_type: str, entity_id: int) -> dict:
        """Fetch entity and return full object (includes 'version' needed for PATCH)."""
        return self.get(f"/api/v1/{entity_type}/{entity_id}")
