"""Offline scoring; no providers, inference, training or credential access.

Hashes establish artifact consistency, not authenticity of training or labels.
Use independent photo review and actual training inspection before making claims.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
import unicodedata
from urllib.parse import urlparse

Row = dict[str, Any]
LICENSES = frozenset({"CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "CC-BY-SA-3.0", "CC-BY-SA-4.0"})
BACKGROUNDS = frozenset({"natural", "studio", "plain"})
DRINK_FAMILIES = ("water", "soda", "juice", "sports", "energy", "milk", "plant_milk",
                  "tea", "coffee", "beer", "wine", "other")
FAMILY_REQUIREMENTS = dict(minimum_families_overall=6, minimum_photos_per_family_overall=10,
    maximum_photos_per_family=75, minimum_families_test=5, minimum_photos_per_family_test=5)
SPLITS = ("train", "validation", "test")
DIVERSITY_REQUIREMENTS = dict(minimum_natural_overall=100, minimum_natural_test=30,
                              minimum_natural_test_settings=3)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_sha256(rows: list[Row]) -> str:
    return canonical_sha256(sorted(rows, key=lambda row: row["image_id"]))


def freeze_split_policy(rows: list[Row], *, adjustment_reason: str | None = None) -> Row:
    """Return preregistration content; caller must write it once, before inference."""
    ordered = sorted(rows, key=lambda row: row["image_id"])
    policy: Row = dict(schema_version="beverage-split-v1", manifest_sha256=manifest_sha256(rows),
        assignments=[{key: row[key] for key in ("image_id", "image_sha256", "source_product_id", "split")}
                     for row in ordered],
        aliases_sha256=canonical_sha256([{key: row[key] for key in ("image_id", "identity_aliases")}
                                        for row in ordered]),
        split_counts={split: sum(row["split"] == split for row in rows) for split in SPLITS},
        diversity_requirements=dict(DIVERSITY_REQUIREMENTS), diversity_counts=dataset_diversity_counts(rows),
        drink_families=list(DRINK_FAMILIES), family_requirements=dict(FAMILY_REQUIREMENTS),
        family_counts=dataset_family_counts(rows))
    if adjustment_reason is not None:
        policy["adjustment_reason"] = adjustment_reason
    return policy


def normalize_identity(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(" " if unicodedata.category(ch).startswith("P") else ch
                            for ch in text).split())


def dataset_family_counts(rows: list[Row]) -> Row:
    return {split: {family: sum(row.get("drink_family") == family for row in rows
                                if split == "overall" or row.get("split") == split)
                    for family in DRINK_FAMILIES}
            for split in ("overall", *SPLITS)}


def dataset_diversity_counts(rows: list[Row]) -> Row:
    natural = [row for row in rows if row.get("background") == "natural"]
    test = [row for row in natural if row.get("split") == "test"]
    settings = sorted({normalize_identity(row["background_detail"]) for row in test
                       if _text(row.get("background_detail"))})
    return dict(natural_overall=len(natural), natural_test=len(test),
                natural_test_settings=len(settings), natural_test_setting_names=settings)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _capacity(value: Any) -> bool:
    return type(value) is int and 0 < value <= 100_000


def safe_artifact_path(root: Path, relative: str) -> Path:
    """Forbid absolute paths, traversal and every symlink component."""
    root = Path(root)
    candidate = Path(relative) if isinstance(relative, str) else Path("/")
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ValueError("artifact path must be relative to the explicit root")
    # A symlink root also hides filesystem indirection and is rejected.
    for part in [root, *root.parents]:
        if part.is_symlink():
            raise ValueError("symlink roots are forbidden")
    path = root
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink artifacts are forbidden")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("artifact missing or outside explicit root")
    return path


def validate_manifest(rows: list[Row], data_root: Path, policy: Row) -> dict[str, int]:
    """Reject incomplete review, mutable truth, leakage and unverifiable pixels."""
    expected = freeze_split_policy(rows, adjustment_reason=policy.get("adjustment_reason"))
    if policy != expected:
        raise ValueError("manifest or aliases differ from frozen fingerprint")
    counts = expected["split_counts"]
    if counts != dict(train=150, validation=25, test=75):
        if not (_text(policy.get("adjustment_reason")) and 240 <= len(rows) <= 260
                and 140 <= counts["train"] <= 160 and 20 <= counts["validation"] <= 30
                and 75 <= counts["test"] <= 85):
            raise ValueError("require 150/25/75 split or documented indivisible-group adjustment")
    seen: dict[str, set[str]] = {key: set() for key in ("image_id", "image_sha256", "original_sha256")}
    product_splits: dict[str, str] = {}
    duplicate_splits: dict[str, str] = {}
    for row in rows:
        for key in ("image_id", "source_product_id", "source_revision", "author", "brand", "product", "capacity_evidence", "reviewer", "background_detail"):
            if not _text(row.get(key)):
                raise ValueError(f"missing reviewed field: {key}")
        source = urlparse(row.get("source_url", ""))
        if source.scheme not in ("https", "http") or not source.netloc or source.username or source.password:
            raise ValueError("source URL must identify public attribution without credentials")
        if row.get("review_status") != "reviewed" or row.get("license") not in LICENSES:
            raise ValueError("reviewed photo and supported image license required")
        if row.get("background") not in BACKGROUNDS or row.get("split") not in SPLITS:
            raise ValueError("reviewed background and valid split required")
        if row.get("drink_family") not in DRINK_FAMILIES:
            raise ValueError("reviewed drink family enum required")
        aliases = row.get("identity_aliases")
        brand = normalize_identity(row["brand"])
        if not isinstance(aliases, list) or not aliases or any(not _text(alias) for alias in aliases):
            raise ValueError("preregistered full identity aliases required")
        for alias in aliases:
            normalized = normalize_identity(alias)
            if not normalized.startswith(brand + " ") or len(normalized) <= len(brand) + 1:
                raise ValueError("identity alias must include full brand and product phrase")
        if row.get("capacity_ml") is None:
            if row.get("capacity_visible") is not False:
                raise ValueError("unknown capacity cannot be visibly verified")
        elif not _capacity(row["capacity_ml"]) or row.get("capacity_visible") is not True:
            raise ValueError("positive integer capacity requires reviewed visible evidence")
        for key in seen:
            value = row.get(key)
            if key != "image_id" and not _sha(value):
                raise ValueError(f"invalid {key}")
            if value in seen[key]:
                raise ValueError(f"duplicate {key}")
            seen[key].add(value)
        product = row["source_product_id"]
        if product in product_splits and product_splits[product] != row["split"]:
            raise ValueError("source product leaks across splits")
        product_splits[product] = row["split"]
        duplicate_group = row.get("duplicate_group_id")
        if duplicate_group is not None:
            if not _text(duplicate_group):
                raise ValueError("near-duplicate group must be nonempty")
            if duplicate_group in duplicate_splits and duplicate_splits[duplicate_group] != row["split"]:
                raise ValueError("near-duplicate group leaks across splits")
            duplicate_splits[duplicate_group] = row["split"]
        path = safe_artifact_path(Path(data_root), row.get("image_path"))
        if file_sha256(path) != row["image_sha256"]:
            raise ValueError("processed image hash mismatch")
    family_counts = expected["family_counts"]
    requirements = FAMILY_REQUIREMENTS
    if (sum(count >= requirements["minimum_photos_per_family_overall"]
            for count in family_counts["overall"].values()) < requirements["minimum_families_overall"]
            or max(family_counts["overall"].values()) > requirements["maximum_photos_per_family"]
            or sum(count >= requirements["minimum_photos_per_family_test"]
                   for count in family_counts["test"].values()) < requirements["minimum_families_test"]):
        raise ValueError("drink family diversity requires >=6 families with >=10 photos overall, no family >75 photos and >=5 test families with >=5 photos")
    diversity = expected["diversity_counts"]
    if any(diversity[key.removeprefix("minimum_")] < minimum
           for key, minimum in DIVERSITY_REQUIREMENTS.items()):
        raise ValueError("dataset diversity requires >=100 natural photos overall, >=30 natural test photos and >=3 reviewed natural test settings")
    return counts


def wilson_interval(correct: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = correct / total
    denominator = 1 + z*z / total
    center = (p + z*z / (2*total)) / denominator
    radius = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denominator
    return [max(0.0, center-radius), min(1.0, center+radius)]


def _metric(correct: int, total: int) -> Row:
    return dict(correct=correct, total=total, rate=correct/total if total else None,
                wilson95=wilson_interval(correct, total))


def _valid_prediction(prediction: Row) -> bool:
    return (prediction.get("outcome") == "success"
        and isinstance(prediction.get("brand"), str) and isinstance(prediction.get("product"), str)
        and (prediction.get("capacity_ml") is None or _capacity(prediction["capacity_ml"]))
        and type(prediction.get("latency_ms")) in (int, float)
        and math.isfinite(prediction["latency_ms"]) and prediction["latency_ms"] >= 0
        and prediction.get("error") in (None, ""))


def score_predictions(rows: list[Row], predictions: list[Row], *, strata: bool = True) -> Row:
    """Score all supplied truth rows; missing/malformed/error rows are failures.

    This low-level function also permits small fixtures. Only evaluate_files()
    validates the complete real experiment and can issue a measured result.
    """
    by_id: dict[str, Row] = {}
    truth_ids = {row["image_id"] for row in rows}
    if len(truth_ids) != len(rows) or not rows:
        raise ValueError("nonempty unique truth IDs required")
    for prediction in predictions:
        image_id = prediction.get("image_id")
        if image_id not in truth_ids or image_id in by_id:
            raise ValueError("duplicate or out-of-split prediction")
        by_id[image_id] = prediction
    counts = dict(total=len(rows), received=len(predictions), missing=0, failed=0, valid=0,
        identity_correct=0, capacity_correct=0, joint_correct=0, abstained_identity=0,
        abstained_capacity=0, unsupported_capacity=0, known_capacity=0, unknown_capacity=0)
    cases = []
    for row in rows:
        pred = by_id.get(row["image_id"])
        known = row["capacity_ml"] is not None
        counts["known_capacity" if known else "unknown_capacity"] += 1
        identity_ok = capacity_ok = False
        if pred is None:
            counts["missing"] += 1
            status = "missing"
        elif not _valid_prediction(pred):
            counts["failed"] += 1
            status = "failed"
        else:
            counts["valid"] += 1
            status = "valid"
            identity = normalize_identity(pred["brand"] + " " + pred["product"])
            identity_ok = identity in {normalize_identity(alias) for alias in row["identity_aliases"]}
            capacity_ok = known and pred["capacity_ml"] == row["capacity_ml"]
            counts["abstained_identity"] += not bool(identity)
            counts["abstained_capacity"] += pred["capacity_ml"] is None
            counts["unsupported_capacity"] += not known and pred["capacity_ml"] is not None
        counts["identity_correct"] += identity_ok
        counts["capacity_correct"] += capacity_ok
        counts["joint_correct"] += identity_ok and capacity_ok
        cases.append(dict(image_id=row["image_id"], status=status, identity_correct=identity_ok,
                          capacity_correct=capacity_ok, joint_correct=identity_ok and capacity_ok))
    report = dict(counts=counts, identity=_metric(counts["identity_correct"], len(rows)),
        capacity=_metric(counts["capacity_correct"], len(rows)),
        joint=_metric(counts["joint_correct"], len(rows)), coverage=_metric(counts["valid"], len(rows)),
        above_70_percent=counts["joint_correct"] * 10 > len(rows) * 7, cases=cases)
    report["identity_abstention"] = _metric(counts["abstained_identity"], len(rows))
    report["capacity_abstention"] = _metric(counts["abstained_capacity"], len(rows))
    report["unsupported_capacity"] = _metric(counts["unsupported_capacity"], len(rows))
    if strata:
        for report_key, field in (("backgrounds", "background"), ("drink_families", "drink_family")):
            report[report_key] = {}
            for value in sorted({row[field] for row in rows}):
                subset = [row for row in rows if row[field] == value]
                subset_ids = {row["image_id"] for row in subset}
                report[report_key][value] = score_predictions(subset,
                    [pred for pred in predictions if pred["image_id"] in subset_ids], strata=False)
    return report


def _unique_object(pairs: list[tuple[str, Any]]) -> Row:
    obj: Row = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON object key")
        obj[key] = value
    return obj


def _parse_json(text: str) -> Any:
    def invalid_constant(value: str) -> None:
        raise ValueError("nonfinite JSON number")
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=invalid_constant)


def read_json(path: Path) -> Row:
    obj = _parse_json(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("JSON object required")
    return obj


def read_jsonl(path: Path) -> list[Row]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = _parse_json(line)
        if not isinstance(obj, dict):
            raise ValueError("JSONL object required")
        rows.append(obj)
    return rows


def _utc(value: Any) -> datetime:
    if not _text(value):
        raise ValueError("UTC timestamp required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("UTC timestamp required")
    return stamp


def _evidence(metadata: Row, path_field: str, hash_field: str, artifact_root: Path) -> Row:
    expected_hash = metadata.get(hash_field)
    if not _sha(expected_hash):
        raise ValueError(f"missing evidence hash: {hash_field}")
    path = safe_artifact_path(artifact_root, metadata.get(path_field))
    if file_sha256(path) != expected_hash:
        raise ValueError("evidence artifact hash mismatch")
    return read_json(path)


def validate_run_metadata(metadata: Row, rows: list[Row], predictions: list[Row],
                          policy: Row, predictions_path: Path, artifact_root: Path) -> str:
    if (metadata.get("schema_version") != "beverage-run-v1" or not _text(metadata.get("run_id"))
            or not _text(metadata.get("model_id"))):
        raise ValueError("versioned run identity required")
    kind = metadata.get("run_kind")
    dataset_kind = metadata.get("dataset_kind")
    if kind not in {"baseline", "adapter", "fixture"} or dataset_kind not in {"real_photos", "synthetic_fixture"}:
        raise ValueError("explicit run and dataset kind required")
    if kind == "fixture" and dataset_kind != "synthetic_fixture":
        raise ValueError("fixture cannot be labeled a real measurement")
    if not isinstance(metadata.get("base_revision"), str) or not re.fullmatch(r"[0-9a-f]{40}", metadata["base_revision"]):
        raise ValueError("immutable base revision required")
    if not _sha(metadata.get("prompt_sha256")):
        raise ValueError("fixed prompt SHA256 required")
    prompt = safe_artifact_path(artifact_root, metadata.get("prompt_path"))
    if file_sha256(prompt) != metadata["prompt_sha256"]:
        raise ValueError("fixed prompt artifact hash mismatch")
    if (metadata.get("manifest_sha256") != manifest_sha256(rows)
            or metadata.get("split_policy_sha256") != canonical_sha256(policy)
            or metadata.get("predictions_sha256") != file_sha256(predictions_path)):
        raise ValueError("run manifest/policy/predictions hash mismatch")
    if metadata.get("selected_using") != "train_validation_only":
        raise ValueError("selection must exclude test data")
    if _utc(metadata.get("checkpoint_frozen_utc")) > _utc(metadata.get("test_inference_started_utc")):
        raise ValueError("checkpoint must be frozen before test inference")
    if kind == "adapter":
        if not _sha(metadata.get("adapter_sha256")):
            raise ValueError("adapter artifact SHA256 required")
        adapter = safe_artifact_path(artifact_root, metadata.get("adapter_path"))
        if file_sha256(adapter) != metadata["adapter_sha256"]:
            raise ValueError("adapter artifact hash mismatch")
        training = _evidence(metadata, "training_run_path", "training_run_sha256", artifact_root)
        selection = _evidence(metadata, "selection_path", "selection_sha256", artifact_root)
        train_rows = [row for row in rows if row["split"] == "train"]
        train_ids = {row["image_id"] for row in train_rows}
        val_ids = {row["image_id"] for row in rows if row["split"] == "validation"}
        if (training.get("schema_version") != "beverage-training-v1"
                or type(training.get("updated_steps")) is not int or training["updated_steps"] <= 0
                or not _sha(training.get("initial_adapter_sha256"))
                or training["initial_adapter_sha256"] == metadata["adapter_sha256"]
                or type(training.get("parameter_delta_l2")) not in (int, float)
                or not math.isfinite(training["parameter_delta_l2"]) or training["parameter_delta_l2"] <= 0
                or type(training.get("save_reload_max_abs_error")) not in (int, float)
                or not math.isfinite(training["save_reload_max_abs_error"])
                or not 0 <= training["save_reload_max_abs_error"] <= 1e-3
                or training.get("adapter_sha256") != metadata["adapter_sha256"]
                or training.get("split_policy_sha256") != metadata["split_policy_sha256"]
                or training.get("train_manifest_sha256") != manifest_sha256(train_rows)
                or not isinstance(training.get("train_image_ids"), list)
                or len(training["train_image_ids"]) != len(train_ids)
                or set(training["train_image_ids"]) != train_ids):
            raise ValueError("training update or train-only evidence invalid")
        if (selection.get("selected_using") != "train_validation_only"
                or selection.get("adapter_sha256") != metadata["adapter_sha256"]
                or selection.get("split_policy_sha256") != metadata["split_policy_sha256"]
                or not isinstance(selection.get("validation_image_ids"), list)
                or len(selection["validation_image_ids"]) != len(val_ids)
                or set(selection["validation_image_ids"]) != val_ids):
            raise ValueError("validation-only selection evidence invalid")
    elif metadata.get("adapter_sha256") is not None:
        raise ValueError("baseline/fixture cannot assert adapter weights")
    for prediction in predictions:
        for field in ("model_id", "base_revision", "adapter_sha256", "prompt_sha256"):
            if field not in prediction or prediction[field] != metadata.get(field):
                raise ValueError("prediction provenance differs from run metadata")
    return "synthetic_fixture" if dataset_kind == "synthetic_fixture" else "measured_" + kind


def evaluate_files(*, manifest_path: Path, predictions_path: Path, policy_path: Path,
                   policy_sha256: str, run_metadata_path: Path, data_root: Path,
                   artifact_root: Path) -> Row:
    """Validate experiment and evidence, then score one untouched test run.

    This cannot authenticate that a human reviewed labels or that update evidence
    came from genuine training. Those facts need external review of source data,
    runtime, weights and independent baseline/after inference artifacts.
    """
    rows = read_jsonl(manifest_path)
    predictions = read_jsonl(predictions_path)
    policy = read_json(policy_path)
    if not _sha(policy_sha256) or canonical_sha256(policy) != policy_sha256:
        raise ValueError("split policy differs from supplied preregistration fingerprint")
    counts = validate_manifest(rows, data_root, policy)
    metadata = read_json(run_metadata_path)
    measurement_class = validate_run_metadata(metadata, rows, predictions, policy,
                                              predictions_path, artifact_root)
    report = score_predictions([row for row in rows if row["split"] == "test"], predictions)
    report.update(schema_version="beverage-evaluation-v1", measurement_class=measurement_class,
        run_id=metadata["run_id"], dataset_counts=counts,
        dataset_diversity=policy["diversity_counts"], diversity_requirements=policy["diversity_requirements"],
        dataset_family_counts=policy["family_counts"], family_requirements=policy["family_requirements"],
        manifest_sha256=manifest_sha256(rows), split_policy_sha256=policy_sha256,
        predictions_sha256=file_sha256(predictions_path), run_metadata_sha256=file_sha256(run_metadata_path),
        adapter_sha256=metadata.get("adapter_sha256"),
        adapter_target_met=measurement_class == "measured_adapter" and report["above_70_percent"],
        provenance_limit="Artifact hashes do not authenticate real training updates or independent photo labels.",
        target_definition="Strictly >70% top1 full identity AND exact positive printed capacity over all test images; unknown capacity is not positive success.",
        generated_utc=datetime.now(timezone.utc).isoformat())
    return report
