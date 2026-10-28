"""Read-only linkage to the operator-designated authoritative gateway ledger."""
from pathlib import Path

from .models import EvaluationCase, Observation, Usage, VerifiedEvidence
from .scoring import camera_gateway_result


def ledger_verifier(path: Path):
    # Delayed import keeps the offline fixture runner independent of the ledger.
    from backend.meta_observations import read_observation, result_fingerprint

    def verify(case: EvaluationCase, observation: Observation) -> VerifiedEvidence:
        receipt = read_observation(path, observation.attempt_id)
        expected_outcome = receipt["outcome"] == "success"
        if (receipt["attempt_id"] != observation.attempt_id or receipt["purpose"] != case.purpose
                or receipt["input_sha256"] != case.input_sha256
                or receipt["model"] != "muse-spark-1.3"
                or receipt["transport_kind"] != "official_meta_https"
                or expected_outcome != (observation.outcome == "success")
                or receipt["outcome"] == "admission_denied"):
            raise ValueError("Observation does not match authoritative transport evidence")
        if observation.outcome == "success":
            canonical = camera_gateway_result(observation.result) if case.purpose == "camera" else observation.result
            if (receipt["result_sha256"] != result_fingerprint(canonical)
                    or receipt["billing_status"] not in ("invoice_verified", "usage_settled_invoice_pending")
                    or receipt["usage"] is None or receipt["provider_id"] is None):
                raise ValueError("Successful output lacks matching settled provider evidence")
        final = receipt["final_gross_micro_usd"] if receipt["billing_status"] == "invoice_verified" else None
        return VerifiedEvidence(account_id=receipt["account_id"],
                                usage=Usage.model_validate(receipt["usage"]) if receipt["usage"] is not None else None,
                                settled_cost_micro_usd=receipt["usage_cost_micro_usd"],
                                final_gross_micro_usd=final,
                                latency_ms=receipt["api_latency_ms"])

    return verify
