"""One-account, one-request gateway; only the transport can supply provider usage."""
import hashlib
import http.client
import json
from time import monotonic_ns
from typing import Protocol

from .meta_accounts import ACCOUNTS, AccountLedger
from .meta_budget import BudgetDenied
from .meta_images import sanitized_jpeg
from .meta_observations import record_observation
from .meta_provider import MetaTransport, parse_recognition, request_payload
from .recognition import AnalysisRequest, AnalysisResult, RecognitionUnavailable


class Notifier(Protocol):
    def deliver(self, notice: dict) -> str: ...


class GitHubNotifier:
    def __init__(self, token: str) -> None:
        if not token or not token.isascii() or any(c.isspace() or ord(c) < 33 for c in token):
            raise ValueError("Server-side developer-notification credential required")
        self._token = token

    def deliver(self, notice: dict) -> str:
        if notice["recipient"] not in ACCOUNTS or notice["account_id"] not in ACCOUNTS:
            raise BudgetDenied("Unknown notification recipient")
        return self._comment(f"@{notice['recipient']} Hydra Meta account {notice['account_id']} reached its $75 gross-exposure checkpoint. Review the authoritative gateway ledger. Credits are account-specific and not transferable.")

    def verify_delivery(self) -> str:
        """Explicit operator check; never called automatically by admission."""
        return self._comment("@georgiosaliba227 @aminealichaouche Hydra budget notification delivery check for the owner-authorized single camera test. This is a delivery check only; no spend threshold has been crossed and this message does not authorize inference.")

    def _comment(self, message: str) -> str:
        body = {"body": message}
        connection = http.client.HTTPSConnection("api.github.com", timeout=10)
        try:
            connection.request("POST", "/repos/georgiosaliba227/Hydra-Ai/issues/6/comments", body=json.dumps(body).encode(), headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json", "User-Agent": "Hydra-Budget-Notifier", "Accept": "application/vnd.github+json"})
            response = connection.getresponse()
            raw = response.read(32769)
            if response.status != 201 or len(raw) > 32768:
                raise ValueError
            identifier = json.loads(raw)["id"]
            if type(identifier) is not int or identifier <= 0:
                raise ValueError
            return f"github-comment:{identifier}"
        except Exception:
            raise BudgetDenied("Developer notification delivery unavailable") from None
        finally:
            connection.close()


class GuardedMetaGateway:
    def __init__(self, ledger: AccountLedger, account: str, transport: MetaTransport, notifier: Notifier) -> None:
        if account not in ACCOUNTS:
            raise ValueError("Select exactly one known Meta account")
        self.ledger, self.account, self.transport, self.notifier = ledger, account, transport, notifier

    def deliver_pending_notices(self) -> None:
        for notice in self.ledger.notices():
            if notice["delivered_at"] is None:
                receipt = self.notifier.deliver(notice)
                if not receipt:
                    raise BudgetDenied("Notification lacks delivery receipt")
                self.ledger.notice_delivered(notice["id"], receipt)

    def analyze(self, image: AnalysisRequest) -> AnalysisResult:
        if image.mode != "meta_live" or image.meta_photo_consent is not True:
            raise RecognitionUnavailable()
        attempt = None
        provider_replied = False
        latency_ms = None
        provider_http_status = None
        outcome = "admission_denied"
        try:
            self.ledger.verify_credential(self.account, self.transport.credential_fingerprint)
            self.ledger.verify_purpose(self.account, "camera")
            payload = request_payload(image)
            # Bounds come from the selected trusted transport, never an HTTP field.
            bound = self.transport.input_bound(payload)
            self.ledger.quote(self.account, bound)
            digest = hashlib.sha256(sanitized_jpeg(image)).hexdigest()
            attempt = self.ledger.reserve_first(self.account, digest, bound)
            self.deliver_pending_notices()
            # Durable dispatch marker precedes the sole network operation. A crash
            # on either side of this boundary keeps the reservation unresolved.
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            ticket = self.ledger.mark_dispatched(attempt, fingerprint)
            outcome = "transport_error"
            started = monotonic_ns()
            try:
                reply = self.transport.generate(payload, ticket)
            finally:
                latency_ms = max(0, (monotonic_ns() - started) // 1_000_000)
            provider_replied = True
            provider_http_status = reply.status
            outcome = "usage_unresolved"
            self.ledger.settle_provider_reply(attempt, reply)
            outcome = "output_rejected"
            result = parse_recognition(reply, attempt)
            self.ledger.mark_recognized(attempt)
            record_observation(self.ledger, attempt, purpose="camera", result=result.model_dump(mode="json"),
                               latency_ms=latency_ms, outcome="success", transport=self.transport,
                               provider_http_status=provider_http_status)
            return result
        except Exception:
            if attempt is not None:
                try:
                    # Even non-billable-looking failures never release money based
                    # on an optimistic interpretation of an exception/status code.
                    self.ledger.quarantine(attempt)
                except Exception:
                    pass  # Unavailable/corrupt ledger cannot admit another call.
                try:
                    record_observation(self.ledger, attempt, purpose="camera", result=None,
                                       latency_ms=latency_ms, outcome=outcome, transport=self.transport,
                                       provider_http_status=provider_http_status)
                except Exception:
                    pass  # Missing observation cannot claim successful evaluation.
                if provider_replied:
                    try:
                        # A provider breach of the reserved bound may itself cross
                        # $75. Keep its durable outbox and freeze even if delivery fails.
                        self.deliver_pending_notices()
                    except Exception:
                        pass
            raise RecognitionUnavailable() from None
