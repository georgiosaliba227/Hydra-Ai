"""Prepare or record a personal Wonder owner-risk policy. Never sends a request.

Prepared drafts leave waive_billing_wait false and its reference null. The later
owner override is recorded only when explicitly supplied in a complete private
descriptor; this command never infers financial permission or invoice finality.
"""
import argparse
import json
from pathlib import Path

from backend.meta_accounts import AccountLedger
from backend.wonder_owner_once import _atomic_new_file, _private_destination
from backend.wonder_personal_owner_policy import OwnerPersonalAuthority, OwnerPersonalPolicy, quote_template


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--output", required=True, type=Path)
    p.add_argument("--quote-output", type=Path)
    p = sub.add_parser("authorize"); p.add_argument("--descriptor", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        owner = OwnerPersonalAuthority(AccountLedger(args.database))
        if args.command == "prepare":
            out = _private_destination(args.output, must_be_absent=True)
            quote = _private_destination(args.quote_output, must_be_absent=True) if args.quote_output else None
            draft = owner.prepare()
            _atomic_new_file(out, (json.dumps(draft, indent=2) + "\n").encode())
            if quote is not None: _atomic_new_file(quote, (json.dumps(quote_template(), indent=2) + "\n").encode())
            result = {"status":"unapproved_draft_saved", "request_sent":False, "financial_state_changed":False}
        else:
            path = _private_destination(args.descriptor)
            owner.authorize(OwnerPersonalPolicy.model_validate_json(path.read_text()))
            result = {"status":"owner_personal_policy_recorded", "request_sent":False}
        print(json.dumps(result, sort_keys=True))
    except Exception:
        raise SystemExit("Personal Wonder operation refused: invalid private inputs, references or financial state. No request sent.") from None


if __name__ == "__main__":
    main()
