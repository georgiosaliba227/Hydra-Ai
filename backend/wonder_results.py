"""Immutable recorded Muse Wonder results for replay without another billable request.

A recorded result is accepted only if rebuilding it from the deterministic
scenario, its validated selection and its provenance reproduces it exactly.
Trend and planned-workout explanations are re-checked against their own facts the same way.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from ai.assistant import SUGGESTED
from .hydration_context_v2 import SCENARIOS, build_scenario, comparison_result, validate_selection
from .meta_accounts import ACCOUNTS
from .wonder_assistant import ALLOWED, live_answer
from .wonder_hydration import MODEL, live_comparison_provenance
from .wonder_trends import trend_result, validate_explanation, validate_facts
from . import wonder_workout

SELECTION_FIELDS = ("factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions",
                    "numerical_abstention")
OBSERVATION_FIELDS = {"latency_ms", "input_tokens", "output_tokens", "usage_derived_cost_micro_usd", "billed_cost_usd"}
MAX_RESULT_BYTES = 65_536
MAX_TREND_RECORDS = 500
TREND_NAME = re.compile(r"trends-[a-f0-9]{64}")
WORKOUT_NAME = re.compile(r"workout-[a-f0-9]{64}")


def validate_recorded(result: dict) -> dict:
    try:
        scenario = result["scenario"]
        if scenario not in SCENARIOS:
            raise ValueError
        provenance, observations = result["provenance"], result["provider_observations"]
        if (str(UUID(provenance["attempt_id"])) != provenance["attempt_id"] or provenance["account_id"] not in ACCOUNTS
                or provenance != live_comparison_provenance(provenance["attempt_id"], provenance["account_id"])):
            raise ValueError
        if not _valid_observations(observations):
            raise ValueError
        context, prediction = build_scenario(scenario)
        interpretation = result["systems"]["B"]["interpretation"]
        selection = validate_selection({name: interpretation[name] for name in SELECTION_FIELDS}, context, prediction)
        if comparison_result(scenario, prediction, selection, provenance, observations) != result:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Recorded Wonder result failed validation") from None
    return result


def _valid_observations(observations: dict) -> bool:
    return (set(observations) == OBSERVATION_FIELDS and observations["billed_cost_usd"] is None
            and all(type(observations[name]) is int and observations[name] >= 0
                    for name in OBSERVATION_FIELDS - {"billed_cost_usd"}))


def validate_recorded_answer(result: dict) -> dict:
    """A recorded Wonder topic selection for one suggested question, rebuilt exactly."""
    try:
        question_id, topics = result["question_id"], tuple(result["topics"])
        provenance, observations = result["provenance"], result["provider_observations"]
        if question_id not in SUGGESTED or not _valid_observations(observations):
            raise ValueError
        if ((provenance["mode"], provenance["model"], provenance["topic_selection"]) != ("meta_live", MODEL, MODEL)
                or provenance["account_id"] not in ACCOUNTS or str(UUID(provenance["attempt_id"])) != provenance["attempt_id"]):
            raise ValueError
        if not set(topics) <= set(ALLOWED[question_id]) or not set(topics) & set(SUGGESTED[question_id][1]):
            raise ValueError
        if live_answer(question_id, topics, attempt_id=provenance["attempt_id"], observations=observations,
                       account=provenance["account_id"]) != result:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Recorded Wonder answer failed validation") from None
    return result


def validate_recorded_trends(result: dict) -> dict:
    """A recorded trend explanation: facts consistent, text re-checked, result rebuilt exactly."""
    try:
        facts, provenance, observations = validate_facts(result["facts"]), result["provenance"], result["provider_observations"]
        if (provenance["account_id"] not in ACCOUNTS or str(UUID(provenance["attempt_id"])) != provenance["attempt_id"]
                or not _valid_observations(observations)):
            raise ValueError
        generated = datetime.fromisoformat(result["generated_at"])
        if generated.tzinfo is None or generated.utcoffset().total_seconds() != 0:
            raise ValueError
        explanation = validate_explanation({"summary": result["summary_template"],
                                            "insights": [{"id": item["id"], "text": item["template"]}
                                                         for item in result["insights"]]}, facts)
        if trend_result(facts, explanation, account=provenance["account_id"], attempt_id=provenance["attempt_id"],
                        observations=observations, generated_at=result["generated_at"]) != result:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Recorded Wonder trends failed validation") from None
    return result


def validate_recorded_workout(result: dict) -> dict:
    """A recorded planned-workout explanation: facts consistent, text re-checked, result rebuilt exactly."""
    try:
        facts = wonder_workout.validate_facts(result["facts"])
        provenance, observations = result["provenance"], result["provider_observations"]
        if (provenance["account_id"] not in ACCOUNTS or str(UUID(provenance["attempt_id"])) != provenance["attempt_id"]
                or not _valid_observations(observations)):
            raise ValueError
        generated = datetime.fromisoformat(result["generated_at"])
        if generated.tzinfo is None or generated.utcoffset().total_seconds() != 0:
            raise ValueError
        explanation = wonder_workout.validate_explanation(
            {"summary": result["summary_template"],
             "insights": [{"id": item["id"], "text": item["template"]} for item in result["insights"]]}, facts)
        if wonder_workout.workout_result(facts, explanation, account=provenance["account_id"],
                                         attempt_id=provenance["attempt_id"], observations=observations,
                                         generated_at=result["generated_at"]) != result:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Recorded Wonder workout explanation failed validation") from None
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
    """Write once; an existing record for the scenario or question is never replaced."""
    if "scenario" in result:
        validate_recorded(result)
        name = result["scenario"]
    elif result.get("version") == wonder_workout.VERSION:
        validate_recorded_workout(result)
        name = "workout-" + result["payload_sha256"]
    elif "facts" in result:
        validate_recorded_trends(result)
        name = "trends-" + result["payload_sha256"]
    else:
        validate_recorded_answer(result)
        name = "assistant-" + result["question_id"]
    target = _private_directory(directory) / (name + ".json")
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return target


def load_recorded_answer(directory: Path, question_id: str) -> dict | None:
    if question_id not in SUGGESTED:
        raise ValueError("Unknown suggested question")
    raw = _read(directory, "assistant-" + question_id)
    return None if raw is None else validate_recorded_answer(raw)


def load_recorded(directory: Path, scenario: str) -> dict | None:
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    raw = _read(directory, scenario)
    return None if raw is None else validate_recorded(raw)


def load_trends(directory: Path, payload_sha256: str) -> dict | None:
    """The saved explanation of exactly this payload, so the same data is never paid for twice."""
    if not re.fullmatch(r"[a-f0-9]{64}", payload_sha256):
        raise ValueError("Payload fingerprint required")
    raw = _read(directory, "trends-" + payload_sha256)
    if raw is None:
        return None
    if raw.get("payload_sha256") != payload_sha256:
        raise ValueError("Recorded trends belong to another payload")
    return validate_recorded_trends(raw)


def latest_trends(directory: Path) -> dict | None:
    """The most recent valid saved trend explanation; unreadable or tampered records are skipped."""
    entries = [entry for entry in os.scandir(_private_directory(directory))
               if entry.name.endswith(".json") and TREND_NAME.fullmatch(entry.name[:-5])]
    entries.sort(key=lambda entry: entry.stat(follow_symlinks=False).st_mtime_ns, reverse=True)
    latest = None
    for entry in entries[:MAX_TREND_RECORDS]:
        try:
            result = load_trends(directory, entry.name[len("trends-"):-5])
        except (ValueError, TypeError, OSError):
            continue
        if latest is None or result["generated_at"] > latest["generated_at"]:
            latest = result
    return latest


def saved_trends(directory: Path) -> list[dict]:
    """Every valid saved trend explanation, for the user's data export."""
    results = []
    for entry in os.scandir(_private_directory(directory)):
        if entry.name.endswith(".json") and TREND_NAME.fullmatch(entry.name[:-5]):
            try:
                results.append(load_trends(directory, entry.name[len("trends-"):-5]))
            except (ValueError, TypeError, OSError):
                continue
    return sorted(results, key=lambda result: result["generated_at"])


def delete_trends(directory: Path) -> int:
    """Remove the user's saved trend explanations (delete-all). Synthetic demo results stay."""
    removed = 0
    for entry in os.scandir(_private_directory(directory)):
        if entry.name.endswith(".json") and TREND_NAME.fullmatch(entry.name[:-5]) and entry.is_file(follow_symlinks=False):
            os.unlink(entry.path)
            removed += 1
    return removed


def load_workout(directory: Path, payload_sha256: str) -> dict | None:
    """The saved explanation of exactly this planned-workout payload; the same data is never paid for twice."""
    if not re.fullmatch(r"[a-f0-9]{64}", payload_sha256):
        raise ValueError("Payload fingerprint required")
    raw = _read(directory, "workout-" + payload_sha256)
    if raw is None:
        return None
    if raw.get("payload_sha256") != payload_sha256:
        raise ValueError("Recorded workout explanation belongs to another payload")
    return validate_recorded_workout(raw)


def saved_workouts(directory: Path) -> list[dict]:
    """Every valid saved planned-workout explanation, for the user's data export."""
    results = []
    for entry in os.scandir(_private_directory(directory)):
        if entry.name.endswith(".json") and WORKOUT_NAME.fullmatch(entry.name[:-5]):
            try:
                results.append(load_workout(directory, entry.name[len("workout-"):-5]))
            except (ValueError, TypeError, OSError):
                continue
    return sorted(results, key=lambda result: result["generated_at"])


def delete_workouts(directory: Path) -> int:
    """Remove the user's saved planned-workout explanations (delete-all)."""
    removed = 0
    for entry in os.scandir(_private_directory(directory)):
        if entry.name.endswith(".json") and WORKOUT_NAME.fullmatch(entry.name[:-5]) and entry.is_file(follow_symlinks=False):
            os.unlink(entry.path)
            removed += 1
    return removed


def _read(directory: Path, name: str) -> dict | None:
    target = _private_directory(directory) / (name + ".json")
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Recorded result must be a regular file")
        raw = handle.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError("Recorded result too large")
    try:
        value = json.loads(raw)
    except RecursionError:
        raise ValueError("Recorded result nests too deeply") from None
    if not isinstance(value, dict):
        raise ValueError("Recorded result must be an object")
    return value
