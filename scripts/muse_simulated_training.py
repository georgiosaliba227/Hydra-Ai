"""Prepare frozen synthetic holdouts, then explicitly train from a verified plan.

Only generate-plan --confirm-billable can contact Meta. It uses the existing
authoritative owner-policy gateway; no command initializes a spending ledger.
Records remain outside Git. An offline stub is never called a Muse response.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from ai.forecasting import muse_synthetic

MAX_JSON_BYTES = 64 * 1024 * 1024


def _read_json(path: Path):
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Research JSON exceeds the size limit")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    def finite(value):
        raise ValueError("Nonfinite JSON")
    return json.loads(path.read_text(), object_pairs_hook=unique, parse_constant=finite)


def _private_json(path: Path):
    info = path.stat(follow_symlinks=False)
    if (not path.is_absolute() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError("Owned absolute mode-0600 operator file required")
    return _read_json(path)


def _new_directory(path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("Row-level research output must stay outside the repository")
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("New absolute research directory required")


def _write_file(path: Path, value) -> None:
    content = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())


def _write_bundle(directory: Path, files: dict) -> None:
    _new_directory(directory)
    directory.mkdir(mode=0o700)
    for name, value in files.items():
        _write_file(directory / name, value)


def _prepared(directory: Path) -> dict:
    # Read/validate the existing frozen manifest before reading any plan file.
    prepared = {"records": _read_json(directory / "base-records.json"),
                "split_manifest": _read_json(directory / "split-manifest.json")}
    muse_synthetic.validate_prepared(prepared)
    return prepared


def _existing_authority(path: Path):
    if path is None or not path.is_absolute() or not path.is_file():
        raise ValueError("Existing absolute authoritative ledger required")
    from backend.meta_accounts import AccountLedger
    from backend.wonder_personal_owner_policy import OwnerPersonalAuthority
    return OwnerPersonalAuthority(AccountLedger(path))


def _operator_descriptors(policy_path: Path, quote_path: Path):
    from backend.wonder_personal_owner_policy import OwnerPersonalPolicy, OwnerRiskQuote
    # Strict models accept ISO datetimes through their JSON boundary, not an
    # already-decoded Python dictionary containing strings.
    policy = OwnerPersonalPolicy.model_validate_json(json.dumps(_private_json(policy_path), allow_nan=False))
    quote = OwnerRiskQuote.model_validate_json(json.dumps(_private_json(quote_path), allow_nan=False))
    return policy, quote


def _generate(args, prepared: dict) -> dict:
    from backend.wonder_personal_owner_gateway import OwnerPersonalMetaTransport, OwnerPersonalWonderGateway
    from backend.wonder_owner_once import _private_destination
    # A result destination must be safe before any reservation or network send.
    _private_destination(args.output, must_be_absent=True)
    authority = _existing_authority(args.database)
    policy, quote = _operator_descriptors(args.policy, args.quote)
    transport = OwnerPersonalMetaTransport(os.environ.get("HYDRA_META_GEORGIO_API_KEY", ""))
    gateway = OwnerPersonalWonderGateway(authority, policy, transport)
    try:
        result = gateway.generate_training_plan(quote, args.consent_reference)
        authority.verify_training_plan_record(result)
        try:
            _write_file(args.output, result)
            gateway.record_result_saved(result)
        except Exception:
            gateway.record_save_failure()
            raise
        return {"status": "validated_plan_saved", "plan_origin": "muse_wonder",
            "path": str(args.output), "attempt_id": result["provenance"]["attempt_id"],
            "frozen_manifest_sha256": muse_synthetic.digest(prepared["split_manifest"]),
            "provider_invoice_final": False}
    except Exception:
        if gateway.last_attempt is not None:
            raise SystemExit("Research request may have been charged. Do not retry; inspect the existing authoritative ledger.") from None
        raise ValueError("Financial admission refused before a research reservation") from None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--records", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    train = commands.add_parser("train")
    train.add_argument("--prepared", type=Path, required=True)
    train.add_argument("--plan", type=Path, required=True)
    train.add_argument("--origin", choices=("offline_stub", "muse_wonder"), required=True)
    train.add_argument("--database", type=Path)
    train.add_argument("--output", type=Path, required=True)
    generate = commands.add_parser("generate-plan")
    generate.add_argument("--prepared", type=Path, required=True)
    generate.add_argument("--database", type=Path, required=True)
    generate.add_argument("--policy", type=Path, required=True)
    generate.add_argument("--quote", type=Path, required=True)
    generate.add_argument("--consent-reference", required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--confirm-billable", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            _new_directory(args.output)
            prepared = muse_synthetic.prepare_base(_read_json(args.records))
            from backend.muse_training_plan import fixed_payload
            from backend.wonder_hydration import input_bound, payload_sha256
            payload = fixed_payload(); bound = input_bound(payload)
            preview = {"model": payload["model"], "payload_sha256": payload_sha256(payload),
                "input_bound_tokens": bound, "max_output_tokens": payload["max_output_tokens"],
                "published_token_bound_micro_usd": bound * 4 + payload["max_output_tokens"] * 20,
                "provider_extras_bounded": False, "personal_data_used": False, "dispatch_enabled": False}
            _write_bundle(args.output, {"base-records.json": prepared["records"],
                "split-manifest.json": prepared["split_manifest"], "payload-preview.json": preview})
            summary = {"status": "frozen_base_prepared", "path": str(args.output),
                "base_records": len(prepared["records"]), "manifest_sha256": muse_synthetic.digest(prepared["split_manifest"]),
                "muse_request_sent": False}
        elif args.command == "train":
            _new_directory(args.output)
            prepared = _prepared(args.prepared)
            record = _read_json(args.plan)
            authority = _existing_authority(args.database) if args.origin == "muse_wonder" else None
            result = muse_synthetic.train_prepared(prepared, record, plan_origin=args.origin, authority=authority)
            _write_bundle(args.output, {"records.json": result["records"], "model.json": result["model"],
                "evaluation.json": result["evaluation"], "split-manifest.json": result["split_manifest"],
                "plan-provenance.json": result["plan_provenance"]})
            summary = {"status": "offline_research_training_complete", "path": str(args.output),
                "plan_origin": args.origin, "records": len(result["records"]),
                "selected_model": result["model"]["selected_model"],
                "synthetic_test_mae_ml": result["evaluation"]["guided_test"]["mae_ml"],
                "personal_serving_promotion": False, "muse_request_sent": False}
        else:
            if args.confirm_billable is not True:
                raise ValueError("Explicit billable confirmation required")
            prepared = _prepared(args.prepared)
            summary = _generate(args, prepared)
        print(json.dumps(summary, sort_keys=True, allow_nan=False))
    except Exception:
        raise SystemExit("Research operation refused: invalid source, frozen data, plan provenance or private output. No permission is created by this command.") from None


if __name__ == "__main__":
    main()
