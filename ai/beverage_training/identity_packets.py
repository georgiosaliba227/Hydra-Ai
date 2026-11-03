"""Local, identity-only visual review packets; never performs model inference.

Small fixtures may use the packet helper. Only the CLI's complete provenance
gate and the separate final scorer can admit an actual test evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
from typing import Any
from uuid import uuid4

from ai.beverage_training import evaluation as ev

IDENTITY_POLICY_SHA256 = "46f54ec956bf3c267083a6f9cf0cc033fdbcf385013d81136af1f949aa189f18"
RUBRIC_FIELDS = ("identity_requirement", "equivalences", "failures", "review_rule", "reviewer_kind")
SOURCE_FIELDS = ("manifest_sha256", "split_policy_sha256", "predictions_sha256", "run_metadata_sha256")


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def checked_file(path: Path) -> Path:
    """Reject filesystem indirection before returning an absolute source path."""
    path = Path(path).absolute()
    if ".." in path.parts or any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise ValueError("source file is missing, traversing or symlinked")
    return path


def load_identity_policy(path: Path) -> tuple[dict, str]:
    path = checked_file(path)
    digest = ev.file_sha256(path)
    if digest != IDENTITY_POLICY_SHA256:
        raise ValueError("identity policy differs from immutable owner policy")
    policy = ev.read_json(path)
    expected = {"schema_version", "policy_version", "frozen_utc", "identity_requirement",
                "equivalences", "failures", "review_rule", "reviewer_kind", "legacy_metric",
                "target", "test_rule", "user_authorization", "volume_requirement"}
    if (set(policy) != expected or policy["schema_version"] != "beverage-identity-equivalence-policy-v1"
            or policy["policy_version"] != "full-identity-exact-volume-v1"):
        raise ValueError("invalid identity policy schema")
    for field in RUBRIC_FIELDS:
        value = policy[field]
        if field in ("equivalences", "failures"):
            if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v.strip() for v in value):
                raise ValueError("invalid identity policy rubric list")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError("invalid identity policy rubric text")
    ev._utc(policy["frozen_utc"])
    return policy, digest


def identity_projection(prediction: dict | None) -> dict:
    """Retain identity only; raw failed output and error text never reach judges."""
    if prediction is None:
        return dict(outcome="missing", brand=None, product=None)
    if not isinstance(prediction, dict) or not ev._valid_prediction(prediction):
        return dict(outcome="error", brand=None, product=None)
    return {"outcome": "success", "brand": prediction["brand"], "product": prediction["product"]}


def prepare_identity_packet(rows: list[dict], predictions: list[dict], *, split: str,
                            data_root: Path, output: Path, policy_path: Path,
                            source_bindings: dict) -> dict:
    """Write exactly packet.json and packet-map.json into an exclusive directory.

    source_bindings contains the full manifest's semantic SHA and the caller's
    verified split-policy, predictions-file and run-metadata-file SHAs. The CLI
    below derives these from strict source files; a small-fixture helper call
    alone can never establish a final result.
    """
    if split not in ("validation", "test"):
        raise ValueError("identity packets support only validation or test")
    policy, policy_sha = load_identity_policy(policy_path)
    if (not isinstance(source_bindings, dict) or set(source_bindings) != set(SOURCE_FIELDS)
            or any(not _sha(source_bindings[field]) for field in SOURCE_FIELDS)
            or source_bindings["manifest_sha256"] != ev.manifest_sha256(rows)):
        raise ValueError("packet source bindings are incomplete or inconsistent")
    ids = set()
    selected = []
    for row in rows:
        image_id = row.get("image_id")
        if (not isinstance(image_id, str) or not image_id.strip() or image_id in ids
                or row.get("split") not in ev.SPLITS):
            raise ValueError("duplicate or invalid manifest identity/split")
        ids.add(image_id)
        if row["split"] == split:
            selected.append(row)
    if not selected:
        raise ValueError("packet requires a nonempty selected split")
    selected_ids = {row["image_id"] for row in selected}
    by_id = {}
    for pred in predictions:
        image_id = pred.get("image_id") if isinstance(pred, dict) else None
        if not isinstance(image_id, str) or image_id not in selected_ids or image_id in by_id:
            raise ValueError("duplicate or out-of-split prediction")
        by_id[image_id] = pred
    cases = []
    mappings = []
    for row in selected:
        if any(not isinstance(row.get(field), str) or not row[field].strip() for field in ("brand", "product")):
            raise ValueError("review reference requires complete brand and product")
        photo = ev.safe_artifact_path(Path(data_root), row.get("image_path"))
        if not _sha(row.get("image_sha256")) or ev.file_sha256(photo) != row["image_sha256"]:
            raise ValueError("packet photo differs from frozen image hash")
        case_id = str(uuid4())
        cases.append(dict(case_id=case_id, image_sha256=row["image_sha256"], photo_path=str(photo.resolve()),
            reference={key: row[key] for key in ("brand", "product")}, prediction=identity_projection(by_id.get(row["image_id"]))))
        mappings.append(dict(case_id=case_id, image_id=row["image_id"], image_sha256=row["image_sha256"]))
    secrets.SystemRandom().shuffle(cases)
    # The private mapping shares packet order, without exposing the source IDs.
    mapping_by_case = {case["case_id"]:case for case in mappings}
    mappings = [mapping_by_case[case["case_id"]] for case in cases]
    created = datetime.now(timezone.utc).isoformat()
    packet = dict(schema_version="beverage-identity-packet-v1", policy_sha256=policy_sha,
        blind_id=str(uuid4()), created_utc=created, rubric={field:policy[field] for field in RUBRIC_FIELDS}, cases=cases)
    mapping = dict(schema_version="beverage-identity-packet-map-v1", policy_sha256=policy_sha,
        **source_bindings, inference_split=split, created_utc=created, packet_path="packet.json", cases=mappings)
    output = Path(output).absolute()
    if ".." in output.parts or any(part.is_symlink() for part in (output, *output.parents)) or output.exists():
        raise ValueError("packet output must be a fresh nonsymlink directory")
    output.mkdir(parents=True, exist_ok=False)
    packet_path = output / "packet.json"
    with packet_path.open("x", encoding="utf-8") as stream:
        json.dump(packet, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    mapping["packet_sha256"] = ev.file_sha256(packet_path)
    with (output / "packet-map.json").open("x", encoding="utf-8") as stream:
        json.dump(mapping, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return mapping
