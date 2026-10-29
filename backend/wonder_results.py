"""Immutable recorded Muse Wonder results for replay without another billable request.

A recorded result is accepted only if rebuilding it from the deterministic
scenario, its validated selection and its provenance reproduces it exactly.
"""
import json
import os
from pathlib import Path
import stat
from uuid import UUID

from .hydration_context_v2 import SCENARIOS, build_scenario, comparison_result, validate_selection
from .meta_experiments import ACCOUNT
from .wonder_hydration import MODEL

SELECTION_FIELDS = ("factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions",
                    "numerical_abstention")
OBSERVATION_FIELDS = {"latency_ms", "input_tokens", "output_tokens", "usage_derived_cost_micro_usd", "billed_cost_usd"}
MAX_RESULT_BYTES = 65_536


def validate_recorded(result: dict) -> dict:
    try:
        scenario = result["scenario"]
        if scenario not in SCENARIOS:
            raise ValueError
        provenance, observations = result["provenance"], result["provider_observations"]
        if (provenance["mode"], provenance["model"], provenance["candidate_model"], provenance["account_id"]) != (
                "meta_live", MODEL, MODEL, ACCOUNT) or str(UUID(provenance["attempt_id"])) != provenance["attempt_id"]:
            raise ValueError
        if set(observations) != OBSERVATION_FIELDS or observations["billed_cost_usd"] is not None or any(
                type(observations[name]) is not int or observations[name] < 0
                for name in OBSERVATION_FIELDS - {"billed_cost_usd"}):
            raise ValueError
        context, prediction = build_scenario(scenario)
        interpretation = result["systems"]["B"]["interpretation"]
        selection = validate_selection({name: interpretation[name] for name in SELECTION_FIELDS}, context, prediction)
        if comparison_result(scenario, prediction, selection, provenance, observations) != result:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Recorded Wonder result failed validation") from None
    return result


def _private_directory(directory: Path) -> Path:
    try:
        if not directory.is_absolute():
            raise OSError
        info = os.stat(directory, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise OSError
    except OSError:
        raise ValueError("Results directory must be an absolute, owned, private directory") from None
    return directory


def save_result(directory: Path, result: dict) -> Path:
    """Write once; an existing record for the scenario is never replaced."""
    validate_recorded(result)
    target = _private_directory(directory) / (result["scenario"] + ".json")
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return target


def load_recorded(directory: Path, scenario: str) -> dict | None:
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    target = _private_directory(directory) / (scenario + ".json")
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        raw = handle.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError("Recorded result too large")
    return validate_recorded(json.loads(raw))
