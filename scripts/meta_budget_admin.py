"""Local operator evidence tools. No provider/notification calls, keys or resets.

Usage: python -m scripts.meta_budget_admin --database /absolute/private/ledger.sqlite3 COMMAND
Evidence files must be private and based on independently reviewed account facts.
This program records human attestations; it does not authenticate their truth.
"""
import argparse
import base64
import hashlib
import json
from backend.meta_images import sanitized_jpeg
from backend.recognition import AnalysisRequest
import os
from pathlib import Path
import stat
from pydantic import ValidationError
from backend.meta_budget import BudgetDenied

from backend.meta_accounts import AccountLedger, Evidence, Price, FirstPermit, ControlledPermit, InvoiceFinality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('command', choices=['init','preview-finality-schema','migrate-finality-schema','attest-account','record-price','approve-first-test','approve-controlled-test','record-invoice-finality','view','reconciliation-reference','image-fingerprint'])
    parser.add_argument('--evidence-file')
    parser.add_argument('--image')
    parser.add_argument('--account')
    parser.add_argument('--reference')
    args = parser.parse_args()
    path = Path(args.database)
    if not path.is_absolute() or path.is_symlink():
        parser.error('Use an absolute path to one authoritative local ledger, not a symlink.')
    ledger = AccountLedger(path)
    if args.command == 'image-fingerprint':
        if not args.image: parser.error('An explicitly selected JPEG is required.')
        image_path = Path(args.image)
        if image_path.stat().st_size > 1_048_576: parser.error('JPEG exceeds the 1 MiB limit.')
        data = image_path.read_bytes()
        image = AnalysisRequest(image_base64=base64.b64encode(data).decode(),photo_consent=True)
        print(hashlib.sha256(sanitized_jpeg(image)).hexdigest())
    elif args.command == 'init':
        ledger.initialize_accounts()
    elif args.command == 'preview-finality-schema':
        print(json.dumps(ledger.preview_finality_schema(), sort_keys=True))
    elif args.command == 'migrate-finality-schema':
        print(json.dumps(ledger.migrate_finality_schema(review_reference=args.reference or ''), sort_keys=True))
    elif args.command == 'view':
        print(ledger.project_view())
    elif args.command == 'reconciliation-reference':
        ledger.record_reconciliation_reference(args.account or '',args.reference or '')
    else:
        if not args.evidence_file:
            parser.error('A private evidence file is required; do not pass keys or amounts as flags.')
        file = Path(args.evidence_file)
        info = file.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            parser.error('Evidence must be an owned mode-0600 regular file.')
        raw = file.read_text()
        if args.command == 'record-invoice-finality': ledger.record_invoice_finality(InvoiceFinality.model_validate_json(raw))
        elif args.command == 'attest-account': ledger.attest_account(Evidence.model_validate_json(raw))
        elif args.command == 'record-price': ledger.record_price(Price.model_validate_json(raw))
        elif args.command == 'approve-controlled-test': ledger.approve_controlled_test(ControlledPermit.model_validate_json(raw))
        elif args.command == 'approve-first-test': ledger.approve_first_test(FirstPermit.model_validate_json(raw))


if __name__ == '__main__':
    try:
        main()
    except (BudgetDenied, ValidationError, OSError, ValueError):
        raise SystemExit("Budget operation refused; verify private account evidence and ledger state.") from None
