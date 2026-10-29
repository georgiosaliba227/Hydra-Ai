"""Operator tooling for the Wonder hydration experiment. Only run-case can send a (billable) request.

templates        Print allocation and quote descriptors for --account, with every
                 reviewed reference left REQUIRED (no ledger needed).
prepare          Read-only approval package for one scenario (no ledger needed).
preview-schema   Read-only LIVE_SCHEMA compatibility check of an existing ledger.
migrate-schema   Add missing LIVE_SCHEMA objects to an existing ledger (needs --reference).
record-allocation / record-case
                 Import a reviewed JSON descriptor into the existing ledger.
run-case         BILLABLE. Send one approved case to Muse Wonder on the quote's account
                 (HYDRA_META_GEORGIO_API_KEY or HYDRA_META_AMINE_API_KEY), then save the
                 validated result for replay. Requires --confirm-billable and every ledger gate.
"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from ai.assistant import SUGGESTED
from backend.hydration_context_v2 import SCENARIOS
from backend.meta_accounts import AccountLedger
from backend.meta_accounts import ACCOUNTS
from backend.meta_experiments import ALLOCATIONS, REFERENCE_PRICES, ExperimentApproval, ExperimentQuote
from backend.meta_gateway import GitHubNotifier
from backend.wonder_experiment import ApprovedCase, WonderExperimentLedger, WonderHydrationGateway, WonderMetaTransport
from backend.wonder_trend_routes import KEY_NAMES
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


def templates(account: str) -> dict:
    """Descriptors to fill in from reviewed evidence; the limits are fixed per account."""
    allocation = ALLOCATIONS[account]
    return {"allocation": {"allocation_id": allocation.allocation_id, "account_id": account,
                           "hard_limit_micro_usd": allocation.hard_limit,
                           "spark_soft_target_micro_usd": allocation.soft_targets["muse-spark-1.3"],
                           "wonder_soft_target_micro_usd": allocation.soft_targets["muse-wonder-1.0"],
                           "key_sha256": "REQUIRED: sha256 of the account's API key (never the key)",
                           "valid_until": REQUIRED, "owner_authorization_reference": REQUIRED,
                           "spending_authority_reference": REQUIRED, "policy_transition_reference": REQUIRED,
                           "georgio_review_reference": REQUIRED, "amine_review_reference": REQUIRED,
                           "further_spend_approval_reference": None, "trend_dispatch_reference": REQUIRED},
            "quote": {"account_id": account, "model": MODEL, "tier": "Standard", "version": REQUIRED,
                      "source": "https://dev.meta.ai/docs/pricing-rate-limits", "valid_until": REQUIRED,
                      "input_micro_per_million": REFERENCE_PRICES[MODEL][0],
                      "output_micro_per_million": REFERENCE_PRICES[MODEL][1], "extra_charge_bound_micro_usd": 0,
                      "all_charge_categories_verified": True, "model_access_verified": True, "reference": REQUIRED,
                      "model_access_reference": REQUIRED, "all_charge_bound_reference": REQUIRED},
            "account_cutoff_micro_usd": allocation.cutoff}


def ledger(path: Path) -> WonderExperimentLedger:
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Absolute path to an existing ledger required")
    return WonderExperimentLedger(AccountLedger(path))


class RunCaseFailed(Exception):
    def __init__(self, attempt: str | None) -> None:
        super().__init__(attempt)
        self.attempt = attempt


def run_case(target: WonderExperimentLedger, args: argparse.Namespace, quote: ExperimentQuote) -> dict:
    if args.confirm_billable is not True or not args.results_dir or not args.results_dir.is_absolute():
        raise ValueError("Explicit billable confirmation and an absolute results directory are required")
    # The quote names the account; the ledger refuses a quote for any account but its allocation's.
    gateway = WonderHydrationGateway(target, WonderMetaTransport(os.environ.get(KEY_NAMES[quote.account_id], "")),
                                     GitHubNotifier(os.environ.get("HYDRA_GITHUB_NOTIFICATION_TOKEN", "")))
    try:
        if args.question_id:
            result = gateway.answer(args.question_id, args.case_id, quote, args.input_reference)
        else:
            result = gateway.explain(args.scenario, args.case_id, quote, args.input_reference)
    except Exception:
        raise RunCaseFailed(gateway.last_attempt) from None
    try:
        recorded = str(save_result(args.results_dir, result))
    except (OSError, ValueError):
        recorded = None  # The settled attempt stays in the ledger; keep the printed result.
    return {"recorded_path": recorded, "result": result}


def run(args: argparse.Namespace) -> dict:
    if args.command == "prepare":
        return prepare(args.scenario, args.question_id)
    if args.command == "templates":
        return templates(args.account)
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
    parser.add_argument("command", choices=["templates", "prepare", "preview-schema", "migrate-schema", "record-allocation", "record-case", "run-case"])
    parser.add_argument("--scenario", choices=SCENARIOS, default="complete")
    parser.add_argument("--account", choices=ACCOUNTS, default=ACCOUNTS[0], help="templates: whose allocation")
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
    except RunCaseFailed as failure:
        if failure.attempt is None:
            raise SystemExit("Wonder run-case refused before any reservation. No request was sent.") from None
        raise SystemExit(f"Wonder run-case failed after reserving attempt {failure.attempt}. A billable request may "
                         "already have been sent. Do not retry; inspect that attempt in the ledger and reconcile "
                         "the provider invoice first.") from None
    except Exception:
        raise SystemExit("Wonder admin refused: invalid inputs or ledger state. No request sent.") from None


if __name__ == "__main__":
    main()
