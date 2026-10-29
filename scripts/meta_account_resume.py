"""Operator tool to lift a frozen account after full reconciliation. No network, keys or resets.

Usage: python -m scripts.meta_account_resume --database /ABS/ledger.sqlite3 \
           --approval /ABS/resume-approval.json --evidence /ABS/fresh-evidence.json {preview,resume}

preview  Read-only: lists every blocker for this exact approval and evidence.
resume   Lifts the freeze only if preview would pass; one audit event, no history changes.

Both files must be owned, mode-0600 regular files written from reviewed evidence.
See docs/architecture/ACCOUNT_RESUME.md.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from pydantic import ValidationError

from backend.meta_accounts import AccountLedger, Evidence
from backend.meta_budget import BudgetDenied
from backend.meta_resume import ResumeApproval, preview_resume, resume_account


def private_json(path: str) -> str:
    file = Path(path)
    info = file.stat(follow_symlinks=False)
    if not file.is_absolute() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Use an absolute, owned, mode-0600 regular file")
    return file.read_text()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["preview", "resume"])
    parser.add_argument("--database", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)
    try:
        path = Path(args.database)
        if not path.is_absolute():
            raise ValueError
        ledger = AccountLedger(path)
        approval = ResumeApproval.model_validate_json(private_json(args.approval))
        evidence = Evidence.model_validate_json(private_json(args.evidence))
        result = (preview_resume if args.command == "preview" else resume_account)(ledger, approval, evidence)
    except BudgetDenied as refusal:
        raise SystemExit(str(refusal)) from None
    except (ValidationError, OSError, ValueError):
        raise SystemExit("Resume refused: invalid, expired or non-private approval or evidence files.") from None
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
