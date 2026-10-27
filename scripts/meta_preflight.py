"""Read private configuration without activating Meta or modifying the ledger.

This reports local readiness only. It cannot authenticate an account, verify a
provider bill, authorize disclosure/spending, or establish exclusive key custody.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import sqlite3
import stat

from backend.meta_accounts import ACCOUNTS
from backend.meta_provider import OfficialMetaTransport
from backend.recognition import MODEL


def private_file(path: Path, maximum_bytes: int | None = None) -> None:
    if not path.is_absolute() or any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Private absolute regular file required")
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Private owned file required")
    if maximum_bytes is not None and info.st_size > maximum_bytes:
        raise ValueError("Configuration exceeds size limit")


def read_private_environment(path: Path) -> dict[str, str]:
    """Parse literal assignments; never source shell, expand variables or mutate env."""
    private_file(path, 32768)
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        parts = shlex.split(line, comments=True, posix=True)
        if not parts:
            continue
        if parts[0] == "export":
            parts = parts[1:]
        if len(parts) != 1 or "=" not in parts[0]:
            raise ValueError("Literal assignments required")
        name, value = parts[0].split("=", 1)
        if not name.isidentifier() or not name.isascii() or name in result:
            raise ValueError("Unique environment assignments required")
        result[name] = value
    return result


def inspect_configuration(env_file: Path, database: Path, account: str) -> dict:
    if account not in ACCOUNTS:
        raise ValueError("Known account required")
    environment = read_private_environment(env_file)
    key_name = "HYDRA_META_GEORGIO_API_KEY" if account == ACCOUNTS[0] else "HYDRA_META_AMINE_API_KEY"
    # Constructor performs local credential syntax validation; it sends nothing.
    try:
        fingerprint = OfficialMetaTransport(environment.get(key_name, "")).credential_fingerprint
        credential_valid = True
    except ValueError:
        fingerprint, credential_valid = None, False
    report = {
        "version": "meta-preflight-v1", "account": account, "model": MODEL,
        "credential_locally_loadable": credential_valid,
        "configured_account_matches": environment.get("HYDRA_META_ACCOUNT") == account,
        "configured_mock": environment.get("HYDRA_AI_MODE", "mock") == "mock",
        "configured_billable_disabled": environment.get("META_BILLABLE_REQUESTS_ENABLED", "false").lower() == "false",
        "notification_credential_present": bool(environment.get("HYDRA_GITHUB_NOTIFICATION_TOKEN")),
        "configured_ledger_matches": environment.get("HYDRA_DATABASE_PATH") == str(database),
        "ledger_readable_private": False, "credential_binding": "unverified",
        "finality_schema_present": False, "account_attestation_present": False,
        "provider_authentication_performed": False, "activation_authorized": False,
    }
    try:
        private_file(database)
        # Read-only open never creates a database, migrates schema or resets history.
        db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            db.execute("PRAGMA query_only=ON")
            report["ledger_readable_private"] = True
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            report["finality_schema_present"] = "live_finalities" in tables
            if "live_accounts" in tables:
                row = db.execute("SELECT evidence FROM live_accounts WHERE account_id=?", (account,)).fetchone()
                if row is not None:
                    report["account_attestation_present"] = True
                    evidence = json.loads(row[0])
                    report["credential_binding"] = "matches_local_attestation" if fingerprint and evidence.get("key_sha256") == fingerprint else "mismatch"
        finally:
            db.close()
    except (OSError, ValueError, sqlite3.Error, TypeError):
        report["ledger_readable_private"] = False
        report["credential_binding"] = "unverified"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--account", choices=ACCOUNTS, default=ACCOUNTS[0])
    args = parser.parse_args()
    try:
        result = inspect_configuration(args.env_file, args.database, args.account)
    except (OSError, ValueError, UnicodeError):
        raise SystemExit("Preflight refused: invalid or unavailable private configuration. No request sent.") from None
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
