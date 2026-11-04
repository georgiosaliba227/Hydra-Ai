"""Operator-only one-use synthetic Wonder policy. Only run can send a request.

prepare writes an invalid private descriptor for review, without ledger changes.
authorize imports the owner's exact reviewed acknowledgement into the existing
ledger. run permanently consumes it and never retries, even after a failure.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from backend.meta_accounts import AccountLedger
from backend.meta_budget import BudgetDenied
from backend.recognition import RecognitionUnavailable
from backend.wonder_owner_once import (OwnerOnceAuthority, OwnerOnceAuthorization, OwnerOnceMetaTransport,
                                       _atomic_new_file, _private_destination)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", required=True, type=Path)
    authorize = commands.add_parser("authorize")
    authorize.add_argument("--descriptor", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--result", required=True, type=Path)
    run.add_argument("--confirm-billable", action="store_true")
    args = parser.parse_args(argv)
    try:
        owner = OwnerOnceAuthority(AccountLedger(args.database))
        if args.command == "prepare":
            path = _private_destination(args.output, must_be_absent=True)
            _atomic_new_file(path, (json.dumps(owner.prepare(), indent=2, allow_nan=False) + "\n").encode())
            result = {"status": "unapproved_template_saved", "descriptor_path": str(path), "request_sent": False}
        elif args.command == "authorize":
            path = _private_destination(args.descriptor)
            descriptor = OwnerOnceAuthorization.model_validate_json(path.read_text())
            owner.authorize(descriptor)
            result = {"status": "owner_authorization_recorded", "request_sent": False}
        else:
            if args.confirm_billable is not True:
                raise ValueError("Explicit billable confirmation required")
            transport = OwnerOnceMetaTransport(os.environ.get("HYDRA_META_GEORGIO_API_KEY", ""))
            result = owner.run(transport, args.result)
            result = {"status": result["receipt"]["state"], "attempt_id": result["receipt"]["attempt_id"],
                      "result_path": str(args.result), "provider_invoice_final": False,
                      "provider_extras_bounded": False}
        print(json.dumps(result, sort_keys=True))
    except RecognitionUnavailable:
        raise SystemExit("Owner Wonder attempt did not produce a saved valid result. Authorization may be consumed; do not retry. Inspect the existing ledger privately.") from None
    except Exception:
        raise SystemExit("Owner Wonder operation refused: invalid inputs, private storage or financial state. No new permission was granted; never retry a consumed attempt.") from None


if __name__ == "__main__":
    main()
