"""Operator tooling for the Wonder hydration experiment. Never sends a Meta request.

prepare          Read-only approval package for one scenario (no ledger needed).
preview-schema   Read-only LIVE_SCHEMA compatibility check of an existing ledger.
migrate-schema   Add missing LIVE_SCHEMA objects to an existing ledger (needs --reference).
record-allocation / record-case
                 Import a reviewed JSON descriptor into the existing ledger.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from backend.hydration_context_v2 import SCENARIOS
from backend.meta_accounts import AccountLedger
from backend.meta_experiments import ExperimentApproval
from backend.wonder_experiment import ApprovedCase, WonderExperimentLedger
from backend.wonder_hydration import MODEL, payload_sha256, preview, wonder_payload

REQUIRED = "REQUIRED: replace with a reviewed reference"


def prepare(scenario: str) -> dict:
    template = {"case_id": str(uuid4()), "model": MODEL, "payload_sha256": payload_sha256(wonder_payload(scenario)),
                "valid_until": REQUIRED, "input_approval_reference": REQUIRED,
                "live_dispatch_reference": REQUIRED, "spending_approval_reference": REQUIRED}
    return {"preview": preview(scenario), "approved_case_template": template}


def ledger(path: Path) -> WonderExperimentLedger:
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Absolute path to an existing ledger required")
    return WonderExperimentLedger(AccountLedger(path))


def run(args: argparse.Namespace) -> dict:
    if args.command == "prepare":
        return prepare(args.scenario)
    target = ledger(args.database)
    if args.command == "preview-schema":
        return target.preview_live_schema()
    if args.command == "migrate-schema":
        return target.migrate_live_schema(review_reference=args.reference)
    raw = Path(args.descriptor).read_text(encoding="utf-8")
    if args.command == "record-allocation":
        target.record_approval(ExperimentApproval.model_validate_json(raw))
        return {"recorded": "allocation"}
    target.record_case(ApprovedCase.model_validate_json(raw))
    return {"recorded": "case"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["prepare", "preview-schema", "migrate-schema", "record-allocation", "record-case"])
    parser.add_argument("--scenario", choices=SCENARIOS, default="complete")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--reference")
    parser.add_argument("--descriptor", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True, allow_nan=False))
    except Exception:
        raise SystemExit("Wonder admin refused: invalid inputs or ledger state. No request sent.") from None


if __name__ == "__main__":
    main()
