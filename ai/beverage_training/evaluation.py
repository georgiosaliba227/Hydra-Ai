"""Offline scoring; no providers, inference, training or credential access.

Hashes establish artifact consistency, not authenticity of training or labels.
Use independent photo review and actual training inspection before making claims.
"""
from __future__ import annotations

from ai.beverage_training.MetaAdapter.cache_contract import validate_encoder_writes

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
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
        aliases_sha256=canonical_sha256([dict(image_id=row["image_id"], identity_aliases=row["identity_aliases"],
                                             brand_aliases=row.get("brand_aliases", [])) for row in ordered]),
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
    identity_splits: dict[str, str] = {}
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
        brand_aliases = row.get("brand_aliases", [])
        if (not isinstance(brand_aliases, list)
                or any(not _text(alias) or not normalize_identity(alias) for alias in brand_aliases)):
            raise ValueError("preregistered brand aliases must be a list of nonempty names")
        brands = {normalize_identity(brand) for brand in [row["brand"], *brand_aliases]}
        if "" in brands:
            raise ValueError("brand must contain a name")
        if not isinstance(aliases, list) or not aliases or any(not _text(alias) for alias in aliases):
            raise ValueError("preregistered full identity aliases required")
        for alias in aliases:
            normalized = normalize_identity(alias)
            if normalized in brands or not any(normalized.startswith(brand + " ") for brand in brands):
                raise ValueError("identity alias must include full brand and product phrase")
            if normalized in identity_splits and identity_splits[normalized] != row["split"]:
                raise ValueError("full identity alias leaks across splits")
            identity_splits[normalized] = row["split"]
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
        and all(field in prediction and (prediction[field] is None or isinstance(prediction[field], str))
                for field in ("brand", "product"))
        and "capacity_ml" in prediction
        and (prediction["capacity_ml"] is None or _capacity(prediction["capacity_ml"]))
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
            brand = normalize_identity(pred["brand"] or "")
            product = normalize_identity(pred["product"] or "")
            identity = normalize_identity((pred["brand"] or "") + " " + (pred["product"] or ""))
            complete_identity = bool(brand and product)
            identity_ok = complete_identity and identity in {normalize_identity(alias) for alias in row["identity_aliases"]}
            capacity_ok = known and pred["capacity_ml"] == row["capacity_ml"]
            counts["abstained_identity"] += not complete_identity
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


SEPARATE_VISION_POLICY = "separate-frozen-vision-v1"


def _canonical_evidence(holder: Row, path_field: str, hash_field: str, root: Path) -> Row:
    obj = read_json(safe_artifact_path(root, holder.get(path_field)))
    if not _sha(holder.get(hash_field)) or canonical_sha256(obj) != holder[hash_field]:
        raise ValueError("canonical artifact hash mismatch")
    return obj


def validate_feature_tensor(path: Path, entry: Row, image_tokens: int) -> None:
    """Inspect safetensors without loading MLX, GPU tensors or a model."""
    if not _sha(entry.get("tensor_sha256")) or file_sha256(path) != entry["tensor_sha256"]:
        raise ValueError("feature tensor file hash mismatch")
    with path.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError("truncated safetensors header")
        header_size = struct.unpack("<Q", prefix)[0]
        if not 2 <= header_size <= 1024 * 1024:
            raise ValueError("invalid safetensors header bound")
        raw_header = stream.read(header_size)
        if len(raw_header) != header_size:
            raise ValueError("truncated safetensors header")
        header = _parse_json(raw_header.decode("utf-8"))
        if not isinstance(header, dict):
            raise ValueError("safetensors header object required")
        metadata = header.pop("__metadata__", {})
        # The pinned Swift MLX writer serializes absent optional metadata as null.
        if metadata is None:
            metadata = {}
        if (not isinstance(metadata, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                for k, v in metadata.items())):
            raise ValueError("invalid safetensors metadata")
        if set(header) != {"vision_features", "prompt_tokens"}:
            raise ValueError("feature cache requires exactly vision_features and prompt_tokens")
        if (entry.get("feature_key") != "vision_features" or entry.get("tokens_key") != "prompt_tokens"
                or entry.get("feature_dtype") not in {"BF16", "F16", "F32"}
                or entry.get("tokens_dtype") != "I32"):
            raise ValueError("unsupported cached tensor key or dtype")
        shapes = (("feature_shape",2), ("tokens_shape",1))
        for field, rank in shapes:
            shape = entry.get(field)
            if (not isinstance(shape, list) or len(shape) != rank
                    or any(type(value) is not int or value <= 0 for value in shape)):
                raise ValueError("invalid cached feature shape")
        if (not 1 <= entry["feature_shape"][0] <= image_tokens or entry["feature_shape"][1] != 6656
                or not 1 <= entry["tokens_shape"][0] <= image_tokens + 512):
            raise ValueError("cached tensor exceeds selected feature dimensions")
        payload_size = path.stat().st_size - 8 - header_size
        segments = []
        for key, dtype, shape in (("vision_features", entry["feature_dtype"], entry["feature_shape"]),
                                  ("prompt_tokens", "I32", entry["tokens_shape"])):
            tensor = header[key]
            if (not isinstance(tensor, dict) or set(tensor) != {"dtype", "shape", "data_offsets"}
                    or tensor.get("dtype") != dtype or tensor.get("shape") != shape
                    or not isinstance(tensor.get("shape"), list)
                    or any(type(value) is not int for value in tensor["shape"])):
                raise ValueError("safetensors descriptor dtype/shape mismatch")
            offsets = tensor.get("data_offsets")
            size = math.prod(shape) * {"BF16":2, "F16":2, "F32":4, "I32":4}[dtype]
            if (not isinstance(offsets, list) or len(offsets) != 2
                    or any(type(value) is not int for value in offsets)
                    or not 0 <= offsets[0] <= offsets[1] <= payload_size or offsets[1] - offsets[0] != size):
                raise ValueError("invalid safetensors tensor offsets")
            segments.append(offsets)
        ordered = sorted(segments)
        if ordered[0][0] != 0 or ordered[0][1] != ordered[1][0] or ordered[1][1] != payload_size:
            raise ValueError("overlapping, incomplete or trailing safetensors payload")
        offsets = header["prompt_tokens"]["data_offsets"]
        stream.seek(8 + header_size + offsets[0])
        raw_tokens = stream.read(offsets[1] - offsets[0])
        if (not _sha(entry.get("prompt_tokens_sha256"))
                or hashlib.sha256(raw_tokens).hexdigest() != entry["prompt_tokens_sha256"]
                or any(token[0] < 0 for token in struct.iter_unpack("<i", raw_tokens))):
            raise ValueError("cached fixed-prompt token bytes are invalid")


def validate_feature_cache(holder: Row, rows: list[Row], artifact_root: Path, config: Row,
                           model_provenance: Row, actual: Row, *, split: str,
                           selection: Row | None = None, predictions: list[Row] | None = None) -> None:
    """Check split cache, actual worker evidence and post-selection test admission.

    File consistency does not authenticate an encoder process or independently
    decode tokenizer semantics; the reviewed worker must recompute fixed tokens.
    """
    if (holder.get("execution_policy") != SEPARATE_VISION_POLICY
            or actual.get("execution_policy") != SEPARATE_VISION_POLICY
            or actual.get("language_only") is not True or actual.get("vision_loaded") is not False):
        raise ValueError("separate language-only worker evidence required")
    cache = _evidence(holder, "feature_cache_path", "feature_cache_sha256", artifact_root)
    cache_path = safe_artifact_path(artifact_root, holder.get("feature_cache_path"))
    cache_root = cache_path.parent
    encoder = _canonical_evidence(holder, "encoder_config_path", "encoder_config_sha256", artifact_root)
    cached_encoder = _canonical_evidence(cache, "encoder_config_path", "encoder_config_sha256", cache_root)
    encoder_sha = config.get("encoder_config_sha256")
    if (encoder != cached_encoder or not _sha(encoder_sha)
            or holder.get("encoder_config_sha256") != encoder_sha
            or cache.get("encoder_config_sha256") != encoder_sha
            or actual.get("encoder_config_sha256") != encoder_sha
            or actual.get("feature_cache_sha256") != holder["feature_cache_sha256"]):
        raise ValueError("feature cache/encoder config differs from selected or actual pipeline")
    if (encoder.get("schema_version") != "beverage-encoder-config-v1"
            or encoder.get("execution_policy") != SEPARATE_VISION_POLICY
            or encoder.get("feature_format") != "safetensors-v1"
            or encoder.get("feature_dtype_policy") != "frozen_encoder_output"
            or encoder.get("token_dtype") != "I32"):
        raise ValueError("versioned frozen vision encoder configuration required")
    for field in ("model_id", "base_revision", "model_provenance_sha256", "runtime_revision", "runtime_patch_sha256",
                  "executable_sha256", "prompt_sha256", "generation_header", "template_current_date", "reasoning_strength", "image_tokens"):
        if field not in encoder or type(encoder[field]) is not type(config[field]) or encoder[field] != config[field]:
            raise ValueError("encoder settings differ from selected inference pipeline")
    for field, filename in (("processor_sha256","processor_config.json"), ("tokenizer_sha256","tokenizer.json"),
                            ("tokenizer_config_sha256","tokenizer_config.json"), ("chat_template_sha256","chat_template.jinja")):
        expected = model_provenance["files"].get(filename, {}).get("sha256")
        if not _sha(encoder.get(field)) or encoder[field] != expected:
            raise ValueError("encoder tokenizer/processor settings differ from verified base provenance")
    if (cache.get("schema_version") != "beverage-feature-cache-v1"
            or cache.get("execution_policy") != SEPARATE_VISION_POLICY or cache.get("split") != split
            or cache.get("outcome") != "complete" or cache.get("source_manifest_sha256") != manifest_sha256(rows)
            or cache.get("split_policy_sha256") != holder.get("split_policy_sha256")):
        raise ValueError("feature cache does not bind the complete frozen split")
    started, completed = _utc(cache.get("started_utc")), _utc(cache.get("completed_utc"))
    language_started = _utc(holder.get("language_started_utc"))
    if started > completed or completed > language_started:
        raise ValueError("cache must complete before language-only execution starts")
    if _utc(actual.get("language_started_utc")) != language_started:
        raise ValueError("actual language worker start differs from run evidence")
    encoder_run = _evidence(cache, "encoder_run_path", "encoder_run_sha256", cache_root)
    namespaces = encoder_run.get("loaded_weight_namespaces")
    if (encoder_run.get("schema_version") != "beverage-encoder-run-v1"
            or encoder_run.get("encoder_config_sha256") != encoder_sha
            or encoder_run.get("vision_only") is not True or encoder_run.get("language_loaded") is not False
            or not isinstance(namespaces, list) or len(namespaces) != 3
            or any(not isinstance(name, str) for name in namespaces)
            or set(namespaces) != {"vision_tower","vision_adapter","vision_projection"}
            or not started <= _utc(encoder_run.get("started_utc")) <= _utc(encoder_run.get("completed_utc")) <= completed):
        raise ValueError("actual frozen vision-only worker provenance invalid")
    if split == "test":
        if selection is None or _utc(holder.get("test_inference_started_utc")) != language_started:
            raise ValueError("frozen selection and actual test language start required")
        admission = _evidence(holder, "cache_admission_selection_path", "cache_admission_selection_sha256", artifact_root)
        validation_ids = {row["image_id"] for row in rows if row["split"] == "validation"}
        admission_ids = admission.get("validation_image_ids")
        if (cache.get("cache_admission_selection_sha256") != holder.get("cache_admission_selection_sha256")
                or admission.get("encoder_config_sha256") != encoder_sha
                or selection.get("encoder_config_sha256") != encoder_sha
                or admission.get("selected_using") != "train_validation_only"
                or admission.get("split_policy_sha256") != holder["split_policy_sha256"]
                or not isinstance(admission_ids,list) or len(admission_ids) != len(validation_ids)
                or any(not isinstance(image_id,str) for image_id in admission_ids) or set(admission_ids) != validation_ids
                or started < _utc(admission.get("checkpoint_frozen_utc"))
                or started < _utc(selection.get("checkpoint_frozen_utc"))):
            raise ValueError("test cache was not admitted after both frozen selections")
    elif cache.get("cache_admission_selection_sha256") is not None:
        raise ValueError("training/validation cache must not claim final-test admission")
    truth = {row["image_id"]:row for row in rows if row["split"] == split}
    entries = cache.get("entries")
    if not isinstance(entries,list) or len(entries) != len(truth):
        raise ValueError("cache must retain every split image including failures")
    successful: dict[str,str] = {}
    seen = set()
    tensor_fields = ("tensor_path","tensor_sha256","feature_key","feature_dtype","feature_shape",
                     "tokens_key","tokens_dtype","tokens_shape","prompt_tokens_sha256")
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get("image_id"),str):
            raise ValueError("invalid feature cache entry")
        image_id = entry["image_id"]
        if image_id not in truth or image_id in seen:
            raise ValueError("duplicate or out-of-split cache image")
        seen.add(image_id)
        if entry.get("split") != split or entry.get("image_sha256") != truth[image_id]["image_sha256"]:
            raise ValueError("cache image hash or split mismatch")
        if entry.get("outcome") == "success" and entry.get("error") in (None,""):
            tensor = safe_artifact_path(cache_root,entry.get("tensor_path"))
            validate_feature_tensor(tensor,entry,encoder["image_tokens"])
            successful[image_id] = entry["tensor_sha256"]
        elif entry.get("outcome") == "error" and _text(entry.get("error")):
            if any(entry.get(field) is not None for field in tensor_fields):
                raise ValueError("failed cache entry cannot assert successful tensors")
        else:
            raise ValueError("cache entry outcome must be explicit")
    validate_encoder_writes(encoder_run.get("actual_feature_writes"), successful)
    uses = actual.get("actual_feature_uses")
    used = set()
    if not isinstance(uses,list):
        raise ValueError("actual feature usage evidence required")
    for use in uses:
        if (not isinstance(use,dict) or not isinstance(use.get("image_id"),str)
                or use["image_id"] in used or use["image_id"] not in successful
                or not _sha(use.get("feature_sha256")) or use["feature_sha256"] != successful[use["image_id"]]):
            raise ValueError("actual feature use differs from validated tensors")
        used.add(use["image_id"])
    if split == "train" and (set(successful) != set(truth) or used != set(truth)):
        raise ValueError("completed training must use every successful train feature")
    for prediction in predictions or []:
        if prediction.get("outcome") == "success" and prediction.get("image_id") not in used:
            raise ValueError("successful prediction lacks actual validated feature use")


def validate_inference_evidence(metadata: Row, rows: list[Row], artifact_root: Path, predictions: list[Row]) -> Row:
    """Bind selected configuration and wrapper-produced provenance artifacts.

    The scorer does not read multi-GB base weights or authenticate the provider.
    The launcher verifies its pinned download; this checks the retained evidence.
    """
    model_provenance = _evidence(metadata, "model_provenance_path", "model_provenance_sha256", artifact_root)
    if (model_provenance.get("schema_version") != "meta-base-provenance-v1"
            or model_provenance.get("repo") != metadata["model_id"]
            or model_provenance.get("revision") != metadata["base_revision"]
            or not isinstance(model_provenance.get("files"), dict) or not model_provenance["files"]):
        raise ValueError("base model provenance does not bind the declared model/revision")
    for name, evidence in model_provenance["files"].items():
        relative = Path(name)
        if (relative.is_absolute() or not relative.parts or ".." in relative.parts
                or not isinstance(evidence, dict) or type(evidence.get("bytes")) is not int
                or evidence["bytes"] <= 0 or not _sha(evidence.get("sha256"))):
            raise ValueError("invalid base model file provenance")
        lfs = evidence.get("provider_lfs_sha256")
        git = evidence.get("provider_git_blob_sha1")
        if ((lfs is not None and lfs != evidence["sha256"])
                or (git is not None and (not isinstance(git, str) or not re.fullmatch(r"[0-9a-f]{40}", git)))):
            raise ValueError("provider file hash evidence is inconsistent")
    expected_config_hash = metadata.get("inference_config_sha256")
    config = read_json(safe_artifact_path(artifact_root, metadata.get("inference_config_path")))
    if not _sha(expected_config_hash) or canonical_sha256(config) != expected_config_hash:
        raise ValueError("inference config artifact hash mismatch")
    separate = config.get("execution_policy") == "separate-frozen-vision-v1"
    expected_vision_policy = "separate-frozen-vision-v1" if separate else "hydra-frozen-vision-release-v1"
    if (config.get("schema_version") != "beverage-inference-config-v1"
            or metadata.get("inference_split") != "test"
            or config.get("decoding") != "greedy"
            or not _sha(config.get("runtime_patch_sha256"))
            or config.get("vision_release_policy") != expected_vision_policy
            or config.get("vision_release_enabled") is not (not separate)
            or type(metadata.get("vision_release_enabled")) is not bool
            or not _text(config.get("generation_header"))
            or not _text(config.get("template_current_date"))
            or not _text(config.get("reasoning_strength"))):
        raise ValueError("versioned frozen test inference configuration required")
    for field in ("model_id", "base_revision", "runtime_revision", "executable_sha256",
                  "model_provenance_sha256", "prompt_sha256", "adapter_config_sha256",
                  "runtime_patch_sha256", "vision_release_policy", "vision_release_enabled"):
        if field not in metadata or field not in config or config[field] != metadata[field]:
            raise ValueError("inference config differs from run provenance")
    if (not _sha(metadata["executable_sha256"]) or not isinstance(metadata["runtime_revision"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", metadata["runtime_revision"])):
        raise ValueError("pinned executable and runtime provenance required")
    for field, low, high in (("image_tokens",16,1024), ("prefill_step",1,128), ("max_output_tokens",16,192),
                             ("memory_limit_bytes",16*1024**3,19*1024**3),
                             ("rss_limit_bytes",1024**3,20*1024**3)):
        if type(config.get(field)) is not int or not low <= config[field] <= high:
            raise ValueError("invalid frozen inference bound")
    if metadata["run_kind"] == "adapter":
        _evidence(metadata, "adapter_config_path", "adapter_config_sha256", artifact_root)
    elif metadata["adapter_config_sha256"] is not None:
        raise ValueError("baseline cannot bind adapter configuration")
    runtime = _evidence(metadata, "runtime_config_path", "runtime_config_sha256", artifact_root)
    for field in ("model_id", "base_revision", "runtime_revision", "image_tokens", "prefill_step",
                  "max_output_tokens", "generation_header", "template_current_date", "reasoning_strength",
                  "prompt_sha256", "executable_sha256", "model_provenance_sha256", "adapter_config_sha256", "decoding",
                  "memory_limit_bytes", "rss_limit_bytes", "runtime_patch_sha256", "vision_release_policy", "vision_release_enabled"):
        if field not in runtime or type(runtime[field]) is not type(config[field]) or runtime[field] != config[field]:
            raise ValueError("actual runtime differs from selected inference configuration")
    if runtime.get("predictions_sha256") != metadata["predictions_sha256"]:
        raise ValueError("runtime predictions hash mismatch")
    if separate:
        for field in ("execution_policy", "encoder_config_sha256"):
            if field not in metadata or field not in runtime or metadata[field] != config.get(field) or runtime[field] != config.get(field):
                raise ValueError("selected and actual separate-execution policy differs")
    elif any("execution_policy" in obj for obj in (config, metadata, runtime)):
        raise ValueError("unsupported or mixed execution policy")
    selection = _evidence(metadata, "selection_path", "selection_sha256", artifact_root)
    for field in ("adapter_sha256", "adapter_config_sha256", "inference_config_sha256", "split_policy_sha256",
                  "checkpoint_frozen_utc", "selected_using"):
        if field not in selection or selection[field] != metadata.get(field):
            raise ValueError("test selection does not bind this frozen configuration")
    val_ids = {row["image_id"] for row in rows if row["split"] == "validation"}
    selected_ids = selection.get("validation_image_ids")
    if (not isinstance(selected_ids, list) or len(selected_ids) != len(val_ids)
            or any(not isinstance(image_id, str) for image_id in selected_ids) or set(selected_ids) != val_ids):
        raise ValueError("selection requires exact validation-only IDs")
    if separate:
        validate_feature_cache(metadata, rows, artifact_root, config, model_provenance, runtime,
                               split="test", selection=selection, predictions=predictions)
    return selection


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
    selection = validate_inference_evidence(metadata, rows, artifact_root, predictions)
    if kind == "adapter":
        if not _sha(metadata.get("adapter_sha256")):
            raise ValueError("adapter artifact SHA256 required")
        adapter = safe_artifact_path(artifact_root, metadata.get("adapter_path"))
        if file_sha256(adapter) != metadata["adapter_sha256"]:
            raise ValueError("adapter artifact hash mismatch")
        training = _evidence(metadata, "training_run_path", "training_run_sha256", artifact_root)
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
        if metadata.get("execution_policy") == SEPARATE_VISION_POLICY:
            config = _canonical_evidence(metadata, "inference_config_path", "inference_config_sha256", artifact_root)
            proof = _evidence(metadata, "model_provenance_path", "model_provenance_sha256", artifact_root)
            validate_feature_cache(training, rows, artifact_root, config, proof, training, split="train")
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
        adapter_config_sha256=metadata["adapter_config_sha256"],
        inference_config_sha256=metadata["inference_config_sha256"],
        model_provenance_sha256=metadata["model_provenance_sha256"],
        executable_sha256=metadata["executable_sha256"],
        runtime_patch_sha256=metadata["runtime_patch_sha256"],
        vision_release_policy=metadata["vision_release_policy"], vision_release_enabled=metadata["vision_release_enabled"],
        execution_policy=metadata.get("execution_policy", "direct-pixel-frozen-prefix-v1"),
        encoder_config_sha256=metadata.get("encoder_config_sha256"),
        feature_cache_sha256=metadata.get("feature_cache_sha256"),
        metric_role="legacy_name_alias_comparison", adapter_target_met=False,
        provenance_limit="Artifact hashes do not authenticate real training updates, independent photo labels or provider origin of base weights; the launcher verifies files against externally trusted provider provenance.",
        target_definition="Legacy literal-name comparison only; current target requires the separately bound dual identity reviews in evaluate_equivalence_files(). Exact printed capacity and all test cases remain required.",
        generated_utc=datetime.now(timezone.utc).isoformat())
    return report
