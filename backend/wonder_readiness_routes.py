"""Owner-authenticated readiness inspection; no writes, provider call or permission change."""
from fastapi import FastAPI

from .wonder_personal_owner_policy import readiness_response


def install_wonder_readiness_routes(app: FastAPI) -> None:
    @app.get("/v1/wonder/readiness")
    def wonder_readiness() -> dict:
        config = app.state.wonder_live_config
        if config is None:
            return readiness_response(["live_disabled"], configured=False, account=None, policy=None, all_charges=None)
        return config.readiness()
