"""Personal aggregate explanations with an explicit owner-risk authority."""
from time import monotonic_ns
from typing import Callable, Protocol, TypeVar

from . import wonder_analysis, wonder_workout, wonder_trends
from .meta_accounts import stamp
from .meta_provider import OfficialMetaTransport, ProviderReply
from .recognition import RecognitionUnavailable
from .wonder_hydration import input_bound, payload_sha256
from .wonder_personal_owner_policy import (ACCOUNT, MODEL, OwnerPersonalAuthority, OwnerPersonalPolicy,
                                          OwnerPersonalTicket, OwnerRiskQuote, canonical)
from .wonder_personal_owner_policy import digest

Parsed = TypeVar("Parsed")


class OwnerPersonalTransport(Protocol):
    credential_fingerprint: str

    def input_bound(self, payload: dict) -> int: ...
    def generate(self, payload: dict, ticket: OwnerPersonalTicket) -> ProviderReply: ...


def validate_purpose_payload(payload: dict) -> str:
    """Recognize exact allowlisted payloads, never arbitrary prompts or raw inputs."""
    try:
        facts = wonder_trends.facts_from_payload(payload)
        if canonical(payload) != canonical(wonder_trends.trends_payload(facts)):
            raise ValueError
        return "personal_trends"
    except ValueError:
        pass
    try:
        facts = wonder_workout.facts_from_payload(payload)
        if canonical(payload) != canonical(wonder_workout.workout_payload(facts)):
            raise ValueError
        return "personal_workout"
    except ValueError:
        pass
    try:
        facts = wonder_analysis.facts_from_payload(payload)
        if facts["mode"] != "personal" or canonical(payload) != canonical(wonder_analysis.analysis_payload(facts)):
            raise ValueError
        return "personal_analysis"
    except ValueError:
        pass
    try:
        from . import wonder_score
        facts = wonder_score.facts_from_payload(payload)
        if canonical(payload) != canonical(wonder_score.score_payload(facts)):
            raise ValueError
        return "personal_home_score"
    except (ImportError, AttributeError, ValueError):
        pass
    try:
        from . import muse_training_plan
        muse_training_plan.validate_payload(payload)
        return "synthetic_training_plan"
    except (ImportError, AttributeError, ValueError):
        raise ValueError("Unsupported personal/research Wonder payload") from None


class OwnerPersonalMetaTransport(OfficialMetaTransport):
    ticket_type = OwnerPersonalTicket

    def validate_payload(self, payload: dict) -> None:
        validate_purpose_payload(payload)

    def input_bound(self, payload: dict) -> int:
        self.validate_payload(payload)
        return input_bound(payload)


class OwnerPersonalWonderGateway:
    def __init__(self, authority: OwnerPersonalAuthority, policy: OwnerPersonalPolicy,
                 transport: OwnerPersonalTransport) -> None:
        if type(authority) is not OwnerPersonalAuthority:
            raise ValueError("Explicit owner-personal authority required")
        self.ledger, self.policy, self.transport = authority, policy, transport
        self.account = ACCOUNT
        self.last_attempt: str | None = None
        self.rejected_reply = None  # Personal provider output is never logged for diagnosis.

    def _run(self, payload: dict, quote: OwnerRiskQuote, consent: str, purpose: str,
             parse: Callable[[ProviderReply], Parsed]) -> tuple[Parsed, str, dict[str, int | None]]:
        attempt = None
        try:
            if validate_purpose_payload(payload) != purpose:
                raise ValueError("Payload purpose mismatch")
            bound = self.transport.input_bound(payload)
            attempt = self.ledger.reserve(self.policy, quote, purpose, payload_sha256(payload), bound,
                payload["max_output_tokens"], self.transport.credential_fingerprint, consent)
            self.last_attempt = attempt
            ticket = self.ledger.dispatch(self.policy, quote, attempt)
            started = monotonic_ns()
            reply = self.transport.generate(payload, ticket)
            latency = max(0, (monotonic_ns() - started) // 1_000_000)
            cost = self.ledger.record_reply(attempt, reply)
            result = parse(reply)
            usage = reply.body["usage"]
            observations = {"latency_ms": latency, "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"], "usage_derived_cost_micro_usd": cost, "billed_cost_usd": None}
            return result, attempt, observations
        except Exception:
            if attempt is not None:
                try: self.ledger.failure(attempt, "request_or_output_failure")
                except Exception: pass  # The durable hold survives unavailable storage.
            raise RecognitionUnavailable() from None

    def explain_trends(self, facts: dict, quote: OwnerRiskQuote, consent_reference: str) -> dict:
        payload = wonder_trends.trends_payload(facts)
        parsed, attempt, observations = self._run(payload, quote, consent_reference, "personal_trends",
            lambda reply: wonder_trends.parse_explanation(reply, facts))
        return self._validated_result(wonder_trends.trend_result(facts, parsed, account=ACCOUNT, attempt_id=attempt,
            observations=observations, generated_at=stamp()))

    def explain_workout(self, facts: dict, quote: OwnerRiskQuote, consent_reference: str) -> dict:
        payload = wonder_workout.workout_payload(facts)
        parsed, attempt, observations = self._run(payload, quote, consent_reference, "personal_workout",
            lambda reply: wonder_workout.parse_explanation(reply, facts))
        return self._validated_result(wonder_workout.workout_result(facts, parsed, account=ACCOUNT, attempt_id=attempt,
            observations=observations, generated_at=stamp()))

    def explain_analysis(self, facts: dict, quote: OwnerRiskQuote, consent_reference: str) -> dict:
        facts = wonder_analysis.validate_facts(facts)
        if facts["mode"] != "personal" or not (facts["calibration"]["total_samples"] or facts["intake"]["beverage_count"]
                or facts["trends"]["logged_days"] or facts["forecast"]["status"] == "estimated"):
            raise RecognitionUnavailable()
        payload = wonder_analysis.analysis_payload(facts)
        parsed, attempt, observations = self._run(payload, quote, consent_reference, "personal_analysis",
            lambda reply: wonder_analysis.parse_selection(reply, facts))
        return self._validated_result(wonder_analysis.analysis_result(facts, parsed, account=ACCOUNT, attempt_id=attempt,
            observations=observations, generated_at=stamp()))

    def _validated_result(self, result: dict) -> dict:
        try:
            self.ledger.record_output(self.last_attempt, digest(result))
            return result
        except Exception:
            self.record_save_failure()
            raise RecognitionUnavailable() from None

    def record_result_saved(self, result: dict) -> None:
        """Call only after the result file has been durably saved."""
        try:
            self.ledger.record_result_saved(self.last_attempt, digest(result))
        except Exception:
            self.record_save_failure()
            raise RecognitionUnavailable() from None

    def record_save_failure(self) -> None:
        if self.last_attempt is not None:
            self.ledger.failure(self.last_attempt, "result_publication_failed")

    def explain_score(self, facts: dict, quote: OwnerRiskQuote, consent_reference: str) -> dict:
        from . import wonder_score
        facts = wonder_score.validate_facts(facts)
        payload = wonder_score.score_payload(facts)
        parsed, attempt, observations = self._run(payload, quote, consent_reference, "personal_home_score",
            lambda reply: wonder_score.parse_explanation(reply, facts))
        return self._validated_result(wonder_score.score_result(facts, parsed, account=ACCOUNT, attempt_id=attempt,
            observations=observations, generated_at=stamp()))

    def generate_training_plan(self, quote: OwnerRiskQuote, consent_reference: str) -> dict:
        from . import muse_training_plan
        payload=muse_training_plan.fixed_payload()
        plan,attempt,observations=self._run(payload,quote,consent_reference,
            "synthetic_training_plan",muse_training_plan.parse_reply)
        envelope={"version":"muse-training-plan-result-v1","plan":plan,"generated_at":stamp(),
            "provenance":{"mode":"meta_live","provider":"Meta","model":MODEL,"account_id":ACCOUNT,
                "attempt_id":attempt,"payload_sha256":payload_sha256(payload),"personal_data_used":False},
            "provider_observations":observations}
        try:
            self.ledger.record_training_plan(envelope)
        except Exception:
            self.record_save_failure()
            raise RecognitionUnavailable() from None
        return self._validated_result(envelope)
