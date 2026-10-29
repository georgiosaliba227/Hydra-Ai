"""Operator tooling for the Wonder hydration experiment. Only run-case can send a (billable) request.

prepare          Read-only approval package for one scenario (no ledger needed).
preview-schema   Read-only LIVE_SCHEMA compatibility check of an existing ledger.
migrate-schema   Add missing LIVE_SCHEMA objects to an existing ledger (needs --reference).
record-allocation / record-case
                 Import a reviewed JSON descriptor into the existing ledger.
run-case         BILLABLE. Send one approved case to Muse Wonder on Georgio's account
                 (HYDRA_META_GEORGIO_API_KEY), then save the validated result for
                 replay. Requires --confirm-billable and every ledger gate.
"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from ai.assistant import SUGGESTED
from backend.hydration_context_v2 import SCENARIOS
from backend.meta_accounts import AccountLedger
from backend.meta_experiments import ExperimentApproval, ExperimentQuote
from backend.meta_gateway import GitHubNotifier
from backend.wonder_experiment import ApprovedCase, WonderExperimentLedger, WonderHydrationGateway, WonderMetaTransport
from backend.wonder_results import save_result
from backend.wonder_assistant import assistant_payload
from backend.wonder_hydration import MODEL, input_bound, payload_sha256, preview, wonder_payload, worst_case_micro_usd

REQUIRED = "REQUIRED: replace with a reviewed reference"


def prepare(scenario: str, question_id: str | None = None) -> dict:
    payload = assistant_payload(question_id) if question_id else wonder_payload(scenario)
    template = {"case_id": str(uuid4()), "model": MODEL, "payload_sha256": payload_sha256(payload),
                "valid_until": REQUIRED, "input_approval_reference": REQUIRED,
                "live_dispatch_reference": REQUIRED, "spending_approval_reference": REQUIRED}
    if question_id:
        bound = input_bound(payload)
        summary = {"question_id": question_id, "model": MODEL, "payload_sha256": template["payload_sha256"],
                   "input_bound_tokens": bound, "byte_bound_micro_usd": worst_case_micro_usd(bound),
                   "dispatch_enabled": False, "billing_evidence": False}
        return {"preview": summary, "approved_case_template": template}
    return {"preview": preview(scenario), "approved_case_template": template}


def ledger(path: Path) -> WonderExperimentLedger:
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Absolute path to an existing ledger required")
    return WonderExperimentLedger(AccountLedger(path))


def run_case(target: WonderExperimentLedger, args: argparse.Namespace, quote: ExperimentQuote) -> dict:
    if args.confirm_billable is not True or not args.results_dir or not args.results_dir.is_absolute():
        raise ValueError("Explicit billable confirmation and an absolute results directory are required")
    gateway = WonderHydrationGateway(target, WonderMetaTransport(os.environ.get("HYDRA_META_GEORGIO_API_KEY", "")),
                                     GitHubNotifier(os.environ.get("HYDRA_GITHUB_NOTIFICATION_TOKEN", "")))
    if args.question_id:
        result = gateway.answer(args.question_id, args.case_id, quote, args.input_reference)
    else:
        result = gateway.explain(args.scenario, args.case_id, quote, args.input_reference)
    try:
        recorded = str(save_result(args.results_dir, result))
    except (OSError, ValueError):
        recorded = None  # The settled attempt stays in the ledger; keep the printed result.
    return {"recorded_path": recorded, "result": result}


def run(args: argparse.Namespace) -> dict:
    if args.command == "prepare":
        return prepare(args.scenario, args.question_id)
    target = ledger(args.database)
    if args.command == "preview-schema":
        return target.preview_live_schema()
    if args.command == "migrate-schema":
        return target.migrate_live_schema(review_reference=args.reference)
    raw = Path(args.descriptor).read_text(encoding="utf-8")
    if args.command == "run-case":
        return run_case(target, args, ExperimentQuote.model_validate_json(raw))
    if args.command == "record-allocation":
        target.record_approval(ExperimentApproval.model_validate_json(raw))
        return {"recorded": "allocation"}
    target.record_case(ApprovedCase.model_validate_json(raw))
    return {"recorded": "case"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["prepare", "preview-schema", "migrate-schema", "record-allocation", "record-case", "run-case"])
    parser.add_argument("--scenario", choices=SCENARIOS, default="complete")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--reference")
    parser.add_argument("--descriptor", type=Path, help="JSON approval, case, or (run-case) quote")
    parser.add_argument("--question-id", choices=list(SUGGESTED), help="run-case/prepare: a suggested assistant question instead of a scenario")
    parser.add_argument("--case-id")
    parser.add_argument("--input-reference")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--confirm-billable", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True, allow_nan=False))
    except Exception:
        raise SystemExit("Wonder admin refused: invalid inputs or ledger state. No request sent.") from None


if __name__ == "__main__":
    main()
