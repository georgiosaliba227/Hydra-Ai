"""Operator-only one-shot synthetic test. No retries and no HTTP admin endpoint."""
import argparse
import os
from pathlib import Path
import stat

from backend.hydration_intelligence import SyntheticContext, HydrationIntelligence, HydrationMetaTransport, context_fingerprint
from backend.meta_accounts import AccountLedger, ACCOUNTS
from backend.meta_gateway import GitHubNotifier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context-file', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--execute-approved-once', action='store_true')
    args = parser.parse_args()
    file = Path(args.context_file)
    info = file.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16384:
        raise ValueError
    context = SyntheticContext.model_validate_json(file.read_text())
    if not args.execute_approved_once:
        print(context_fingerprint(context))
        return
    if os.getenv('HYDRA_META_HYDRATION_ENABLED', 'false') != 'true' or os.getenv('META_BILLABLE_REQUESTS_ENABLED', 'false') != 'true':
        raise ValueError
    database = Path(args.database)
    if not database.is_absolute() or database.is_symlink():
        raise ValueError
    result = HydrationIntelligence(AccountLedger(database), ACCOUNTS[1],
        HydrationMetaTransport(os.getenv('HYDRA_META_AMINE_API_KEY', '')),
        GitHubNotifier(os.getenv('HYDRA_GITHUB_NOTIFICATION_TOKEN', ''))).explain(context)
    # No input/output bodies in stdout: operator can inspect separately under policy.
    print('Settled synthetic attempt: ' + result['attempt_id'])


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Test refused or attempt uncertain. Do not retry; inspect authoritative ledger.') from None
