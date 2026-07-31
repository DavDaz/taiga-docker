"""Secure local launcher for the Taiga MCP server."""

import os
import stat
from pathlib import Path


ALLOWED_KEYS = frozenset(
    {"TAIGA_URL", "TAIGA_USERNAME", "TAIGA_PASSWORD", "TAIGA_TOKEN"}
)


class CredentialFileError(RuntimeError):
    """Raised when the local credential file fails validation."""


def load_credentials(path: Path) -> dict[str, str]:
    """Atomically open, validate, and parse a local credential file."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise CredentialFileError("Taiga MCP credentials file cannot be opened safely") from exc

    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise CredentialFileError("Taiga MCP credentials file must be a regular file")
        if stat.S_IMODE(file_stat.st_mode) not in (0o400, 0o600):
            raise CredentialFileError(
                "Taiga MCP credentials file has unsafe permissions; require mode 400 or 600"
            )
        with os.fdopen(descriptor, "r", encoding="utf-8", newline=None) as credential_file:
            descriptor = -1
            content = credential_file.read()
    except (OSError, UnicodeError) as exc:
        raise CredentialFileError("Taiga MCP credentials file cannot be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    credentials: dict[str, str] = {}
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CredentialFileError(
                f"Invalid Taiga MCP credentials entry on line {line_number}"
            )
        key, value = line.split("=", 1)
        if key not in ALLOWED_KEYS:
            raise CredentialFileError(
                f"Unknown Taiga MCP credentials key on line {line_number}"
            )
        if key in credentials:
            raise CredentialFileError(
                f"Duplicate Taiga MCP credentials key on line {line_number}"
            )
        credentials[key] = value
    return credentials


def main() -> None:
    credential_path = Path(__file__).resolve().parents[1] / ".env"
    os.environ.update(load_credentials(credential_path))

    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
