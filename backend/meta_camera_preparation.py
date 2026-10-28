"""Read-only, exact-image camera plan. This module cannot dispatch or approve."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Callable

from scripts.meta_preflight import private_file, read_private_environment
from .meta_accounts import ACCOUNTS, CAP, PROPOSED_CAP, AccountLedger, ControlledPermit, Evidence, Price, parse_permit
from .meta_budget import BudgetDenied
from .meta_gateway import GitHubNotifier
from .meta_images import sanitized_jpeg
from .meta_policy import MAX_INPUT_TOKENS, MODEL_CONTEXT, OUTPUT_LIMIT
from .meta_provider import OfficialMetaTransport, request_payload, strict_json
from .recognition import AnalysisRequest, MAX_IMAGE_BYTES, MODEL


def _gate(status: str, requirement: str) -> dict:
    return {"status": status, "requirement": requirement}


def _check(gates: dict, name: str, predicate: Callable[[], object], requirement: str) -> object | None:
    try:
        value = predicate()
        gates[name] = _gate("locally_satisfied", requirement)
        return value
    except (BudgetDenied, ValueError, TypeError, KeyError, AttributeError, OSError, sqlite3.Error):
        gates[name] = _gate("blocked", requirement)
        return None


def _validated_json(raw: str, model):
    # Reject duplicate/nonfinite fields before the existing typed boundary.
    return model.model_validate_json(json.dumps(strict_json(raw), allow_nan=False))


def _required_json_row(row: tuple | None, model):
    if row is None:
        raise ValueError("Required local evidence missing")
    return _validated_json(row[0], model)


def _private_jpeg(path: Path) -> bytes:
    private_file(path, MAX_IMAGE_BYTES)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds existing API limit")
    return data


def _ledger_snapshot(database: Path) -> sqlite3.Connection:
    private_file(database)
    # The current ledger uses SQLite's rollback journal. Refuse WAL/hot-journal
    # state before opening: mode=ro can otherwise create or update WAL sidecars.
    with database.open("rb") as stream:
        header = stream.read(100)
    if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
        raise ValueError("Unsupported or malformed ledger format")
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Ledger has active recovery or WAL sidecars")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.5)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        return connection
    except Exception:
        connection.close()
        raise


def prepare_camera(env_file: Path, database: Path, image_file: Path, account: str = ACCOUNTS[0]) -> dict:
    """Inspect only explicitly supplied files; no environment or ledger mutation.

    Local evidence is an attestation, not provider authentication. Snapshot gates
    cannot reserve funds or substitute for the gateway's atomic admission checks.
    """
    if account not in ACCOUNTS:
        raise ValueError("Known workstream account required")
    gates: dict[str, dict] = {}
    # model_construct supplies only the existing fixed rate defaults to pure
    # integer arithmetic. It creates no dated/reviewed price attestation.
    reference_quote = Price.cost(Price.model_construct(), MAX_INPUT_TOKENS, OUTPUT_LIMIT)
    report = {
        "version": "meta-camera-local-plan-v1", "kind": "read_only_local_plan",
        "account": account, "model": MODEL, "dispatch_authorized": False,
        "provider_authentication_performed": False, "network_requests_sent": 0,
        "ledger_mutations_performed": False,
        "normalized_image_sha256": None, "canonical_payload_sha256": None,
        "request_options": {"store": False, "stream": False, "background": False,
                            "max_output_tokens": OUTPUT_LIMIT, "reasoning_effort": "minimal",
                            "structured_output": "beverage_recognition", "tools": False,
                            "files": False, "sam": False, "retries": 0, "images": 1},
        "reservation": {"model_context_tokens": MODEL_CONTEXT, "input_bound_tokens": MAX_INPUT_TOKENS,
                        "output_bound_tokens": OUTPUT_LIMIT, "cache_discount_assumed": False,
                        "code_rate_token_reference_micro_usd": reference_quote,
                        "reference_is_verified_provider_bound": False,
                        "locally_attested_token_quote_micro_usd": None,
                        "locally_attested_extra_charge_bound_micro_usd": None,
                        "locally_attested_total_bound_micro_usd": None},
        "policy": {"active_first_request_cap_micro_usd": CAP, "proposed_disabled_cap_micro_usd": PROPOSED_CAP,
                   "proposed_policy_authorized": False, "project_request_count": 1,
                   "account_notice_micro_usd": 75_000_000, "account_further_approval_micro_usd": 100_000_000,
                   "account_operational_cutoff_micro_usd": 120_000_000, "account_absolute_ceiling_micro_usd": 150_000_000},
        "gates": gates,
        "limits": ["This local plan never authorizes dispatch or authenticates a provider account.",
                   "Do not re-encode the approved iPhone-prepared JPEG; compare its backend-normalized hash.",
                   "The authoritative gateway rechecks admission, budget races and one-use permits at send time.",
                   "Reported evidence statuses describe local attestations, not independent provider verification."],
    }
    gates["camera_account"] = _gate("locally_satisfied" if account == ACCOUNTS[0] else "blocked",
                                    "Georgio's camera must select georgiosaliba227; no account fallback.")
    environment = _check(gates, "private_environment", lambda: read_private_environment(env_file),
                         "Provide the existing owned 0600 literal-assignment environment file; no shell sourcing.")
    fingerprint = None
    if environment is not None:
        gates["configured_account"] = _gate("locally_satisfied" if environment.get("HYDRA_META_ACCOUNT") == ACCOUNTS[0] and account == ACCOUNTS[0] else "blocked",
                                              "Select Georgio's account explicitly in private backend configuration.")
        gates["configured_ledger"] = _gate("locally_satisfied" if environment.get("HYDRA_DATABASE_PATH") == str(database) else "blocked",
                                             "Private backend configuration must name this existing authoritative ledger exactly.")
        gates["disabled_configuration"] = _gate("locally_satisfied" if environment.get("HYDRA_AI_MODE", "mock") == "mock" and environment.get("META_BILLABLE_REQUESTS_ENABLED", "false").lower() == "false" else "blocked",
                                                 "Keep mock mode and billable requests disabled throughout preparation.")
        transport = _check(gates, "credential_locally_loadable", lambda: OfficialMetaTransport(environment.get("HYDRA_META_GEORGIO_API_KEY", "")),
                           "Provide Georgio's existing server credential privately; local syntax is not authenticated access.")
        if transport is not None:
            fingerprint = transport.credential_fingerprint
        _check(gates, "notification_credential_locally_loadable", lambda: GitHubNotifier(environment.get("HYDRA_GITHUB_NOTIFICATION_TOKEN", "")),
               "Provide the server-side notification credential; actual delivery to both developers remains separately verified.")
    try:
        raw_image = _private_jpeg(image_file)
        # True flags only construct the exact payload locally; they are not
        # evidence of disclosure consent and this function has no sender.
        image = AnalysisRequest(image_base64=base64.b64encode(raw_image).decode(), photo_consent=True,
                                meta_photo_consent=True, mode="meta_live")
        normalized = sanitized_jpeg(image)
        payload = request_payload(image)
        report["normalized_image_sha256"] = hashlib.sha256(normalized).hexdigest()
        report["canonical_payload_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        gates["prepared_jpeg"] = _gate("locally_satisfied", "Use the exact bounded iPhone-prepared JPEG; structural validation is not pixel/ownership verification.")
    except (OSError, ValueError, TypeError):
        gates["prepared_jpeg"] = _gate("blocked", "Provide an owned 0600 bounded JPEG matching the iPhone export; invalid inputs are not normalized or disclosed.")
    db = None
    try:
        db = _ledger_snapshot(database)
        gates["authoritative_ledger_readable"] = _gate("locally_satisfied", "Operator must identify the existing authoritative ledger; this command does not establish custody.")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"live_accounts", "live_prices", "live_permit", "controlled_permits", "live_attempts", "live_finalities", "live_notices"}
        if not required <= tables:
            gates["ledger_schema"] = _gate("blocked", "Review the missing authoritative ledger schema/finality migration separately; preparation never migrates.")
        else:
            gates["ledger_schema"] = _gate("locally_satisfied", "Required existing financial and finality tables are present.")
            _inspect_evidence(db, AccountLedger(database), account, fingerprint, report)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error, BudgetDenied):
        gates["authoritative_ledger_readable"] = _gate("blocked", "Provide an existing owned 0600 ledger with valid rollback-journal schema; close writers or resolve recovery state without copying/resetting it.")
    finally:
        if db is not None:
            db.close()
    gates["active_cost_ceiling"] = _gate("blocked" if reference_quote > CAP else "unverified",
                                         "The full-context uncached token reference exceeds $0.25; obtain a provider-backed lower total bound with reviewed enforcement, or an explicit separate policy decision. $2 is not authorized.")
    gates["external_account_authentication"] = _gate("unverified", "Owner must independently verify selected provider identity/key binding, model access, gross and pending usage, credits/expiry/terms, and exclusive gateway custody.")
    gates["external_billing_and_notices"] = _gate("unverified", "Verify all charge categories, request-level billing/finality and actual notice delivery to both developers; local credential syntax is insufficient.")
    gates["dispatch"] = _gate("blocked", "This command only prepares a local plan; exact-image consent, account/model/price-bound human spending approval and authoritative gateway admission remain mandatory.")
    dependent_gates = {
        "configured_account": "A readable private environment must explicitly select Georgio's camera account.",
        "configured_ledger": "A readable private environment must select the existing authoritative ledger exactly.",
        "disabled_configuration": "Verify mock mode and billable=false in the existing private environment.",
        "credential_locally_loadable": "Read Georgio's server credential from valid private configuration; never substitute Amine's key.",
        "notification_credential_locally_loadable": "Read the server notification credential from valid private configuration.",
        "ledger_schema": "A readable existing ledger must have the reviewed financial/finality schema.",
        "project_unfrozen": "Check all account freeze flags in the readable existing ledger.",
        "prior_invoice_finality": "Check every prior attempt's immutable finality in the readable existing ledger.",
        "prior_billing_resolved": "Verify there is no unresolved attempt in either account.",
        "pending_notices": "Verify delivery receipts for every outstanding developer notice.",
        "first_project_request_unused": "Verify the first project-wide request has never been attempted.",
        "account_evidence": "Read current independently verified account evidence; missing data never proves zero spending.",
        "credential_binding": "Match Georgio's private credential to current selected-account evidence.",
        "permit_schema_current": "Read a current exact-account/image/price permit with human authorization references.",
        "active_permit_policy": "Verify the permit uses the active $0.25 first-camera policy; dual-test-v1 is not authorized.",
        "permit_account_unused": "Verify the camera permit belongs to Georgio and is unused.",
        "exact_image_consent": "Compare exact normalized prepared-JPEG hash against the current owner-consented permit.",
        "bound_price_evidence": "Read the valid Standard-model price snapshot named by that permit.",
        "existing_policy_validation": "Run the existing gateway's read-only policy validation after prerequisites are present.",
    }
    for name, requirement in dependent_gates.items():
        gates.setdefault(name, _gate("not_evaluated", requirement))
    report["blocking_gates"] = [name for name, gate in gates.items() if gate["status"] != "locally_satisfied"]
    return report


def _inspect_evidence(db: sqlite3.Connection, ledger: AccountLedger, account: str, fingerprint: str | None, report: dict) -> None:
    gates = report["gates"]
    _check(gates, "project_unfrozen", lambda: ledger.verify_project_unfrozen(db), "Resolve any frozen account through reviewed provider reconciliation; either account freezes the whole project.")
    _check(gates, "prior_invoice_finality", lambda: ledger.verify_prior_finalities(db), "Every previous attempt needs matching, reviewed provider invoice finality before another request.")
    pending = db.execute("SELECT 1 FROM live_attempts WHERE actual IS NULL LIMIT 1").fetchone()
    gates["prior_billing_resolved"] = _gate("blocked" if pending else "locally_satisfied", "No new request while any project attempt has unresolved billing.")
    notices = db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL LIMIT 1").fetchone()
    gates["pending_notices"] = _gate("blocked" if notices else "locally_satisfied", "Existing notices must have verified delivery receipts; preparation sends no notifications.")
    attempts = db.execute("SELECT 1 FROM live_attempts LIMIT 1").fetchone()
    gates["first_project_request_unused"] = _gate("blocked" if attempts else "locally_satisfied", "The active policy permits only the first project-wide request; never reset attempts or permits.")
    row = db.execute("SELECT evidence FROM live_accounts WHERE account_id=?", (account,)).fetchone()
    evidence = _check(gates, "account_evidence", lambda: _required_json_row(row, Evidence),
                      "Record independently verified, current account billing/credit/retention/grant evidence; absence never means zero usage.")
    if evidence is not None:
        if evidence.account_id != account:
            evidence = None
            gates["account_evidence"]["status"] = "blocked"
    gates["credential_binding"] = _gate("locally_satisfied" if evidence is not None and fingerprint is not None and evidence.key_sha256 == fingerprint and account == ACCOUNTS[0] else "blocked",
                                         "The selected local key must match independently verified evidence for Georgio's provider account.")
    grant = ledger.grant(db, account)
    permit = None
    if grant:
        permit = _check(gates, "permit_schema_current", lambda: parse_permit(json.dumps(strict_json(grant[0]), allow_nan=False)),
                        "Provide a current exact-account/image/price one-use permit with both developer reviews and owner/spending/disclosure references.")
    else:
        gates["permit_schema_current"] = _gate("blocked", "No selected permit exists; obtain and record exact-account/image/price human consent and spending approval through the reviewed operator process.")
    if permit is not None:
        supported = not isinstance(permit, ControlledPermit)
        gates["active_permit_policy"] = _gate("locally_satisfied" if supported else "blocked", "Only the active $0.25 first-camera policy applies; dual-test-v1 remains a disabled proposal.")
        gates["permit_account_unused"] = _gate("locally_satisfied" if permit.account_id == account == ACCOUNTS[0] and grant[1] == 0 else "blocked", "Permit must belong to Georgio and be unused; never reset or substitute accounts.")
        gates["exact_image_consent"] = _gate("locally_satisfied" if permit.image_sha256 == report["normalized_image_sha256"] and bool(permit.image_owner_consent_reference.strip()) else "blocked",
                                              "Obtain disclosure consent for this exact backend-normalized prepared JPEG; source-photo consent does not authorize a re-encoding.")
        price_row = db.execute("SELECT snapshot FROM live_prices WHERE version=?", (permit.price_version,)).fetchone()
        price = _check(gates, "bound_price_evidence", lambda: _required_json_row(price_row, Price),
                       "Permit must bind current independently reviewed Standard-model rates, with both developer reviews.")
        if price is not None and price.version != permit.price_version:
            gates["bound_price_evidence"]["status"] = "blocked"
            price = None
        if price is not None:
            token_quote = price.cost(MAX_INPUT_TOKENS, OUTPUT_LIMIT)
            report["reservation"]["locally_attested_token_quote_micro_usd"] = token_quote
            if evidence is not None:
                report["reservation"]["locally_attested_extra_charge_bound_micro_usd"] = evidence.extra_charge_bound_micro_usd
                report["reservation"]["locally_attested_total_bound_micro_usd"] = token_quote + evidence.extra_charge_bound_micro_usd
    _check(gates, "existing_policy_validation", lambda: ledger._policy(db, account),
           "Existing gateway validation must accept current evidence, price and unused permit; this read-only check cannot reserve funds or grant admission.")
