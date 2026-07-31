import os
from pathlib import Path

import pytest

from taiga_mcp.launcher import CredentialFileError, load_credentials


def write_credentials(path: Path, content: str, mode: int = 0o600) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_load_credentials_accepts_safe_modes(tmp_path: Path, mode: int) -> None:
    path = write_credentials(tmp_path / ".env", "TAIGA_URL=https://taiga.example\n", mode)

    assert load_credentials(path) == {"TAIGA_URL": "https://taiga.example"}


def test_load_credentials_rejects_symlink(tmp_path: Path) -> None:
    target = write_credentials(tmp_path / "target", "TAIGA_TOKEN=dummy\n")
    symlink = tmp_path / ".env"
    symlink.symlink_to(target)

    with pytest.raises(CredentialFileError, match="cannot be opened safely"):
        load_credentials(symlink)


def test_load_credentials_rejects_unsafe_mode(tmp_path: Path) -> None:
    path = write_credentials(tmp_path / ".env", "TAIGA_TOKEN=dummy\n", 0o644)

    with pytest.raises(CredentialFileError, match="unsafe permissions"):
        load_credentials(path)


def test_load_credentials_rejects_non_regular_file(tmp_path: Path) -> None:
    with pytest.raises(CredentialFileError, match="regular file"):
        load_credentials(tmp_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not-an-entry\n", "Invalid"),
        ("PATH=/tmp\n", "Unknown"),
        ("TAIGA_TOKEN=first\nTAIGA_TOKEN=second\n", "Duplicate"),
    ],
)
def test_load_credentials_rejects_invalid_entries(
    tmp_path: Path, content: str, message: str
) -> None:
    path = write_credentials(tmp_path / ".env", content)

    with pytest.raises(CredentialFileError, match=message):
        load_credentials(path)


def test_load_credentials_preserves_literal_value(tmp_path: Path) -> None:
    value = " leading $HOME;$(command)='quoted'\\path # literal "
    path = write_credentials(tmp_path / ".env", f"TAIGA_PASSWORD={value}\n")

    assert load_credentials(path)["TAIGA_PASSWORD"] == value


def test_load_credentials_allows_missing_file(tmp_path: Path) -> None:
    assert load_credentials(tmp_path / ".env") == {}
