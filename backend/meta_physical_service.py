"""Arm one explicitly approved photo on a private development app process."""
import json
import os
import threading
from time import monotonic_ns

from .meta_gateway import GuardedMetaGateway
from .recognition import MockMetaRecognizer, RecognitionUnavailable


def arm_physical_once(app, ledger, transport, notifier, output_file):
    """No permit creation or credentials here. Caller supplies existing approval.

    Even concurrent calls can invoke the gateway only once. Every completed or
    failed attempt restores mock mode before returning to the HTTP adapter.
    The exclusive output file must be opened before any possibility of a send.
    """
    output = output_file.open("x", encoding="utf-8")
    os.fchmod(output.fileno(), 0o600)
    lock = threading.Lock()
    app.state.meta_ledger = ledger
    app.state.recognition_mode = "meta_live"
    app.state.physical_live_enabled = True
    gateway = GuardedMetaGateway(ledger, "georgiosaliba227", transport, notifier)

    class OnceRecognizer:
        def analyze(self, payload):
            if not lock.acquire(blocking=False):
                raise RecognitionUnavailable()
            report = {"policy_version": "georgio-physical-camera-once-risk-v1",
                      "recognition": None, "provider_reply": None, "error": None}
            started = monotonic_ns()
            try:
                result = gateway.analyze(payload)
                report["recognition"] = result.model_dump(mode="json")
                return result
            except Exception:
                report["error"] = "unavailable_or_unresolved_do_not_retry"
                raise
            finally:
                app.state.recognizer = MockMetaRecognizer()
                app.state.recognition_mode = "mock"
                app.state.physical_live_enabled = False
                report["backend_returned_to_mock"] = True
                report["elapsed_ms"] = (monotonic_ns() - started) // 1_000_000
                if getattr(transport, "last_reply", None) is not None:
                    report["provider_reply"] = {"status": transport.last_reply.status,
                                                "body": transport.last_reply.body}
                try:
                    json.dump(report, output, allow_nan=False)
                    output.flush()
                    os.fsync(output.fileno())
                finally:
                    output.close()
                # Intentionally never release the one-use process lock.

    app.state.recognizer = OnceRecognizer()
    app.router.routes[:] = [route for route in app.router.routes
                           if getattr(route, "path", None) not in ("/health", "/v1/recognition-capabilities")]

    @app.get("/health")
    def health():
        return {"status": "ok", "ai_mode": app.state.recognition_mode,
                "billable_requests_enabled": app.state.physical_live_enabled,
                "dispatch_requires_account_permit_and_verified_bound": True}

    @app.get("/v1/recognition-capabilities")
    def capabilities():
        return {"version": "recognition-v1", "mode": app.state.recognition_mode,
                "provider": "Meta" if app.state.physical_live_enabled else None,
                "model": "muse-spark-1.3", "dispatch_requires_account_permit_and_verified_bound": True,
                "privacy": "Meta may retain content under its service, safety and legal terms; no zero-retention claim."}
