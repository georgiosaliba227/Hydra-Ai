"""Explicit operator-only physical test server. No retries or public arm route.

The user-approved exception must already exist in the selected original ledger.
This process reads the existing private legacy credential file into memory only;
it never saves new provider credentials or exposes them to the iPhone.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--legacy-env", required=True, type=Path)
    parser.add_argument("--authority", required=True, type=Path)
    parser.add_argument("--enable-approved-once", action="store_true")
    args = parser.parse_args()
    if not args.enable_approved_once:
        parser.error("Explicit one-use activation is required")
    os.umask(0o077)
    from scripts.meta_preflight import private_file, read_private_environment
    private_file(args.session / "config.json")
    config = json.loads((args.session / "config.json").read_text())
    legacy = read_private_environment(args.legacy_env)
    if (legacy.get("HYDRA_AI_MODE") != "mock"
            or legacy.get("META_BILLABLE_REQUESTS_ENABLED") != "false"
            or legacy.get("HYDRA_DATABASE_PATH") != str(args.authority)
            or config["host"] not in ("192.168.1.4",)
            or config["port"] != 8771 or config["url"] != "http://192.168.1.4:8771"):
        raise ValueError("Expected private disabled configuration and local device session required")
    for name in list(os.environ):
        if name.startswith(("HYDRA_", "META_", "WONDER_")) or name == "MODEL_API_KEY":
            os.environ.pop(name, None)
    os.environ.update(HYDRA_AI_MODE="mock", META_BILLABLE_REQUESTS_ENABLED="false",
                      HYDRA_META_HYDRATION_ENABLED="false", HYDRA_WONDER_LIVE="false")
    from backend.app import create_app
    from backend.meta_physical_once import PhysicalCameraLedger, ACCOUNT
    from backend.meta_physical_service import arm_physical_once
    from backend.meta_provider import OfficialMetaTransport
    from backend.meta_gateway import GitHubNotifier
    import uvicorn
    key = legacy["HYDRA_META_GEORGIO_API_KEY"]
    ledger = PhysicalCameraLedger(args.authority)
    ledger.verify_credential(ACCOUNT, hashlib.sha256(key.encode()).hexdigest())
    ledger.quote(ACCOUNT, 1048064)
    # Bind the socket BEFORE arming, so a busy port cannot consume authorization.
    import socket
    listener = socket.socket()
    listener.bind((config["host"], config["port"]))
    listener.listen(16)
    app = create_app(config["database"], config["token"])
    arm_physical_once(app, ledger, OfficialMetaTransport(key),
                      GitHubNotifier(legacy["HYDRA_GITHUB_NOTIFICATION_TOKEN"]),
                      args.session / "physical-meta-provider-result.json")

    @app.middleware("http")
    async def private_evidence(request, call_next):
        response = await call_next(request)
        # No bodies, query strings, images, prompts or credentials.
        print(json.dumps({"method": request.method, "path": request.url.path,
                          "status": response.status_code}), flush=True)
        return response

    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning"))
    try:
        server.run(sockets=[listener])
    finally:
        app.state.physical_live_enabled = False
        app.state.recognition_mode = "mock"
        listener.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Physical test startup refused; no automatic retry. Review private evidence.") from None
