"""Authenticated read-only replay; this route cannot authorize or dispatch."""
import os
from pathlib import Path

from fastapi import HTTPException

from .wonder_owner_once import load_result


def install_owner_once_routes(app) -> None:
    configured = os.getenv("HYDRA_WONDER_OWNER_ONCE_RESULT", "")
    path = Path(configured) if configured else None
    if path is not None and not path.is_absolute():
        raise ValueError("HYDRA_WONDER_OWNER_ONCE_RESULT must be absolute")

    @app.get("/v1/wonder/owner-once/result")
    def owner_once_result():
        if path is None or not path.exists():
            raise HTTPException(404, "wonder_owner_once_unavailable")
        try:
            return load_result(path)
        except (OSError, ValueError):
            raise HTTPException(503, "wonder_owner_once_unavailable") from None
