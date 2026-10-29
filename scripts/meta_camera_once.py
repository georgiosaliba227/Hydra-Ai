"""One explicit operator invocation; no server, loops, retries or permit creation.

Requires the named risk permit already recorded in the authoritative ledger.
Output is an exclusive private file: a bounded provider reply, parsed result,
latency, and ledger observation. No images, prompts or credentials are saved.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import stat
from time import monotonic_ns

from backend.app import create_app
from backend.meta_accounts import AccountLedger, ACCOUNTS, RiskPermit
from backend.meta_camera_preparation import _private_jpeg
from backend.meta_observations import read_observation
from backend.meta_provider import OfficialMetaTransport
from backend.recognition import AnalysisRequest, MockMetaRecognizer
from scripts.meta_preflight import read_private_environment


def run_once(env_file: Path, database: Path, image_file: Path, output_file: Path) -> dict:
    environment = read_private_environment(env_file)
    session_token = environment.get("HYDRA_API_TOKEN", "")
    if (len(session_token) < 32 or not session_token.isascii()
            or any(character.isspace() for character in session_token)):
        raise ValueError("Existing private backend session authentication required")
    if (environment.get("HYDRA_AI_MODE") != "mock"
            or environment.get("META_BILLABLE_REQUESTS_ENABLED") != "false"
            or environment.get("HYDRA_META_ACCOUNT") != ACCOUNTS[0]
            or environment.get("HYDRA_DATABASE_PATH") != str(database)
            or environment.get("HYDRA_META_HYDRATION_ENABLED", "false") != "false"):
        raise ValueError("Explicit disabled Georgio configuration required")
    ledger = AccountLedger(database)
    ledger.preview_finality_schema()
    with ledger.transaction() as db:
        _, _, permit = ledger._policy(db, ACCOUNTS[0])
        if not isinstance(permit, RiskPermit):
            raise ValueError("Exact risk-policy permit required")
    request = AnalysisRequest(image_base64=base64.b64encode(_private_jpeg(image_file)).decode(),
                              photo_consent=True, meta_photo_consent=True, mode="meta_live")
    if (not output_file.is_absolute()
            or any(part.is_symlink() for part in (output_file, *output_file.parents))):
        raise ValueError("Private absolute output path required")
    parent = output_file.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError("Owned private output directory required")
    descriptor = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    saved_environment = dict(os.environ)
    app = None
    transport = None
    report = {"version": "first-camera-risk-execution-v1", "provider_reply": None,
              "recognition": None, "ledger_observation": None, "error": None}
    started = monotonic_ns()
    try:
        # Only this dedicated process becomes live; persisted config stays mock.
        os.environ.update(environment)
        os.environ.pop("HYDRA_META_AMINE_API_KEY", None)
        os.environ["HYDRA_AI_MODE"] = "guarded_meta"
        os.environ["META_BILLABLE_REQUESTS_ENABLED"] = "true"
        os.environ["HYDRA_META_HYDRATION_ENABLED"] = "false"
        app = create_app()
        transport = app.state.recognizer.transport
        if type(transport) is not OfficialMetaTransport:
            raise ValueError("Official guarded sender required")
        result = app.state.recognizer.analyze(request)  # Exactly one invocation.
        report["recognition"] = result.model_dump(mode="json")
    except Exception:
        # Never print provider/socket exception details or infer zero charges.
        report["error"] = "attempt_unavailable_or_unresolved; do not retry"
    finally:
        if app is not None:
            app.state.recognizer = MockMetaRecognizer()
            app.state.recognition_mode = "mock"
        os.environ.clear()
        os.environ.update(saved_environment)
        os.environ["HYDRA_AI_MODE"] = "mock"
        os.environ["META_BILLABLE_REQUESTS_ENABLED"] = "false"
        os.environ["HYDRA_META_HYDRATION_ENABLED"] = "false"
        report["backend_returned_to_mock"] = True
        report["operator_elapsed_ms"] = (monotonic_ns() - started) // 1_000_000
        if transport is not None and transport.last_reply is not None:
            report["provider_reply"] = {"status": transport.last_reply.status, "body": transport.last_reply.body}
        try:
            with ledger.transaction() as db:
                attempts = db.execute("SELECT id FROM live_attempts").fetchall()
            report["ledger_attempt_count"] = len(attempts)
            if len(attempts) == 1:
                report["attempt_id"] = attempts[0][0]
                report["ledger_observation"] = read_observation(database, attempts[0][0])
        except Exception:
            report["ledger_status"] = "requires_operator_reconciliation"
        with os.fdopen(descriptor, "w") as output:
            json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute-authorized-risk-test", required=True, action="store_true")
    args = parser.parse_args()
    try:
        report = run_once(args.env_file, args.database, args.image, args.output)
    except Exception:
        raise SystemExit("Operator execution refused; inspect ledger before any further action.") from None
    print(json.dumps({k: report.get(k) for k in ("backend_returned_to_mock", "ledger_attempt_count", "attempt_id", "error")}))
    if report["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

