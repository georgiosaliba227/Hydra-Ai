"""Restricted developer credentials for a shared backend (docs/architecture/SHARED_BACKEND.md).

The owner's HYDRA_API_TOKEN keeps full access. Another developer authenticates
with their own token, which the backend knows only as a SHA-256 hash in a
private file (HYDRA_DEVELOPER_CREDENTIALS). Each credential reaches only the
routes of its scopes and never the owner's logs, settings or export. The file
is re-read on every request, so revoking takes effect immediately.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

# Synthetic Muse Wonder features only: no route here reads the owner's logged data.
SCOPES = {
    "wonder": {
        ("GET", "/v1/wonder/live"), ("POST", "/v1/wonder/live"),
        ("POST", "/v2/hydration-context-comparison"),
        ("GET", "/v1/assistant/questions"), ("POST", "/v1/assistant"),  # context_scope must stay "none"
        ("POST", "/v1/workout-forecasts"), ("POST", "/v2/workout-forecasts"),
    },
}
MAX_FILE_BYTES = 65_536
DEVELOPER_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,38}")


def load_credentials(path: Path) -> list[dict]:
    """Active credentials; an unreadable, shared or malformed file grants nothing."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                return []
            raw = handle.read(MAX_FILE_BYTES + 1)
        value = json.loads(raw)
        if len(raw) > MAX_FILE_BYTES or value.get("version") != "developer-credentials-v1":
            return []
        active = []
        for item in value["developers"]:
            if (set(item) != {"id", "token_sha256", "scopes", "revoked"} or not DEVELOPER_ID.fullmatch(item["id"])
                    or not re.fullmatch(r"[a-f0-9]{64}", item["token_sha256"]) or item["revoked"] not in (True, False)
                    or not item["scopes"] or not set(item["scopes"]) <= set(SCOPES)):
                return []  # One malformed entry disables the whole file rather than guessing.
            if item["revoked"] is False:
                active.append(item)
        return active
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return []


def developer_for(path: Path | None, authorization: bytes) -> dict | None:
    """The active credential matching a `Bearer <token>` header, if any."""
    if path is None or not authorization.startswith(b"Bearer "):
        return None
    token = authorization[len(b"Bearer "):]
    if len(token) < 32 or len(token) > 512:
        return None
    digest = hashlib.sha256(token).hexdigest()
    match = None
    for item in load_credentials(path):
        if hmac.compare_digest(digest, item["token_sha256"]):
            match = item
    return match


def allowed(credential: dict, method: str, path: str) -> bool:
    return any((method, path) in SCOPES[scope] for scope in credential["scopes"])
