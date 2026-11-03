#!/usr/bin/env python3
"""Launch only local Muse Glimmer image LoRA jobs and bind reproducible artifacts.

No provider/API calls, model downloads, billing records or application backend changes.
Run `--help` for bounded model settings. Build instructions live with the Swift package.
"""
from __future__ import annotations
import argparse
import ctypes
import time
from datetime import datetime, timezone
import hashlib
import functools
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ai.beverage_training.evaluation import canonical_sha256, manifest_sha256, validate_manifest
from ai.beverage_training.MetaAdapter.cache_contract import verify_cache, POLICY, utc


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class LocalProcessError(ValueError):
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(kind)


class _ProcTaskInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
        ("virtual", "resident", "total_user", "total_system", "threads_user", "threads_system")] + [
        (name, ctypes.c_int32) for name in ("policy", "faults", "pageins", "cow_faults", "messages_sent",
        "messages_received", "syscalls_mach", "syscalls_unix", "csw", "threadnum", "numrunning", "priority")]


@functools.lru_cache(maxsize=1)
def _proc_library():
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    library.proc_pidinfo.restype = ctypes.c_int
    return library


def child_resident_bytes(pid: int) -> int:
    if sys.platform == "darwin":
        library = _proc_library()
        info = _ProcTaskInfo()
        count = library.proc_pidinfo(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info))
        if count != ctypes.sizeof(info):
            raise LocalProcessError("resident_measurement_unavailable")
        return int(info.resident)
    raise LocalProcessError("resident_monitor_requires_macos")


def run_local_process(command: list[str], *, rss_limit_bytes: int) -> None:
    """Independent 50ms RSS monitor; sampled checks are not a hard allocation cap."""
    child = subprocess.Popen(command)
    try:
        while child.poll() is None:
            try:
                resident = child_resident_bytes(child.pid)
            except LocalProcessError as measurement_error:
                # libproc can lose the task before waitpid/poll reports process exit.
                # Resolve that bounded race before classifying a monitoring failure.
                try:
                    completed_status = child.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    raise measurement_error
                if completed_status != 0:
                    raise LocalProcessError("local_runtime_failed")
                break
            if resident > rss_limit_bytes:
                raise LocalProcessError("rss_budget_exceeded")
            time.sleep(.05)
        if child.wait() != 0:
            raise LocalProcessError("local_runtime_failed")
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_relative(path: Path, root: Path) -> str:
    if path.is_symlink():
        raise ValueError("artifact symlinks are not allowed")
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError("artifact is outside explicit artifact root") from None
    return relative.as_posix()


def validate_selection(selection, *, split: str, adapter_sha256: str | None, policy_sha256: str, adapter_config_sha256: str | None = None, inference_config_sha256: str | None = None) -> str:
    if selection is None:
        if split == "test":
            raise ValueError("test inference requires a frozen validation-only checkpoint selection")
        return datetime.now(timezone.utc).isoformat()
    if (selection.get("selected_using") != "train_validation_only"
            or selection.get("split_policy_sha256") != policy_sha256
            or selection.get("adapter_sha256") != adapter_sha256
            or "adapter_config_sha256" not in selection
            or selection["adapter_config_sha256"] != adapter_config_sha256
            or selection.get("inference_config_sha256") != inference_config_sha256
            or not isinstance(selection.get("checkpoint_frozen_utc"), str)):
        raise ValueError("checkpoint selection does not bind this adapter/policy")
    frozen = datetime.fromisoformat(selection["checkpoint_frozen_utc"].replace("Z", "+00:00"))
    if frozen.utcoffset() is None or frozen > datetime.now(timezone.utc):
        raise ValueError("invalid checkpoint freeze timestamp")
    return selection["checkpoint_frozen_utc"]


def verify_base_provenance(model: Path, *, model_id: str, revision: str) -> tuple[bytes, str]:
    """Verify local bytes and recorded provider digests before assigning a pinned base ID."""
    proof_path = model / "base-provenance.json"
    if model.is_symlink() or proof_path.is_symlink():
        raise ValueError("model provenance must not use symlinks")
    proof_bytes = proof_path.read_bytes()
    proof = json.loads(proof_bytes)
    records = proof.get("files")
    if (proof.get("schema_version") != "meta-base-provenance-v1"
            or proof.get("repo") != model_id or proof.get("revision") != revision
            or not isinstance(records, dict)):
        raise ValueError("base provenance does not bind the pinned model/revision")
    required = {"config.json", "processor_config.json", "tokenizer.json", "tokenizer_config.json",
                "generation_config.json", "chat_template.jinja", "model.safetensors.index.json"}
    if not required <= records.keys():
        raise ValueError("base provenance omits required model/tokenizer/processor files")
    for name, record in records.items():
        if (not isinstance(name, str) or not name or Path(name).name != name or name in (".", "..", "base-provenance.json")
                or not isinstance(record, dict)):
            raise ValueError("invalid model provenance path/record")
        path = model / name
        size, digest = record.get("bytes"), record.get("sha256")
        lfs, git_blob = record.get("provider_lfs_sha256"), record.get("provider_git_blob_sha1")
        if (path.is_symlink() or not path.is_file() or type(size) is not int or size < 0
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or (lfs is None and git_blob is None)
                or (lfs is not None and (not isinstance(lfs, str) or re.fullmatch(r"[0-9a-f]{64}", lfs) is None))
                or (git_blob is not None and (not isinstance(git_blob, str) or re.fullmatch(r"[0-9a-f]{40}", git_blob) is None))
                or path.stat().st_size != size):
            raise ValueError("invalid or incomplete model provenance evidence")
        sha = hashlib.sha256()
        blob = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                sha.update(block); blob.update(block)
        if sha.hexdigest() != digest or (lfs is not None and lfs != digest) or (lfs is None and git_blob is not None and blob.hexdigest() != git_blob):
            raise ValueError("model file differs from its pinned provider evidence")
    index = read_json(model / "model.safetensors.index.json")
    mapping = index.get("weight_map")
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("empty model weight index")
    shard_names = list(mapping.values())
    if any(not isinstance(name, str) or Path(name).name != name or not name.endswith(".safetensors") for name in shard_names):
        raise ValueError("invalid model weight shard path")
    shards = set(shard_names)
    if (not shards
            or not shards <= records.keys()
            or {path.name for path in model.glob("*.safetensors")} != shards):
        raise ValueError("model weight shards differ from the pinned index/provenance")
    return proof_bytes, hashlib.sha256(proof_bytes).hexdigest()


def runtime_rows(rows: list[dict], *, command: str, split: str) -> list[dict]:
    keys = ("image_id", "image_sha256", "split", "review_status")
    if command == "prepare-features":
        keys += ("image_path",)
    elif command != "infer":
        keys += ("brand", "product", "capacity_ml", "capacity_visible")
        split = "train"
    return [{key: row[key] for key in keys} for row in sorted(rows, key=lambda row: row["image_id"]) if row["split"] == split]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("smoke", "train", "infer", "prepare-features"))
    for name in ("model", "data-root", "manifest", "split-policy", "output", "artifact-root"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--binary", type=Path, default=Path("/private/tmp/hydra-beverage-meta-build/release/meta-beverage"))
    p.add_argument("--adapter", type=Path)
    p.add_argument("--feature-cache", type=Path)
    p.add_argument("--preflight", action="store_true", help="Train-only incomplete encoder hardware preflight")
    p.add_argument("--cache-admission-selection", type=Path)
    p.add_argument("--selection", type=Path, help="Required before either baseline or adapter final-test inference")
    p.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    p.add_argument("--run-id")
    p.add_argument("--dataset-kind", choices=("real_photos", "synthetic_fixture"), default="real_photos")
    for name, default in (("image-tokens", 128), ("prefill-step", 32), ("max-answer-tokens", 96), ("max-output-tokens", 96), ("memory-limit-gb", 19), ("rss-limit-gb", 20), ("epochs", 1), ("layers", 1), ("rank", 4)):
        p.add_argument("--" + name, type=int, default=default)
    p.add_argument("--steps", type=int)
    p.add_argument("--learning-rate", type=float, default=0.0001)
    return p


def validate_experiment_dimensions(*, image_tokens: int, layers: int, rank: int) -> None:
    for name, value, low, high in (("image_tokens", image_tokens, 16, 1024), ("layers", layers, 1, 8), ("rank", rank, 1, 16)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"invalid experiment dimension: {name}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    validate_experiment_dimensions(image_tokens=args.image_tokens, layers=args.layers, rank=args.rank)
    if not 1 <= args.rss_limit_gb <= 20:
        raise ValueError("RSS budget must be between 1 and 20 GiB")
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    policy = read_json(args.split_policy)
    policy_sha = canonical_sha256(policy)
    if args.command == "smoke" or (args.command == "prepare-features" and args.preflight):
        # Hardware preflight is separately labeled and cannot satisfy evaluation.
        # A single reviewed train photo is enough to test the real visual update.
        if (not rows or any(row.get("split") != "train" or row.get("review_status") != "reviewed" for row in rows)
                or policy.get("manifest_sha256") != manifest_sha256(rows)):
            raise ValueError("smoke requires reviewed train-only rows and their matching frozen policy")
    else:
        validate_manifest(rows, args.data_root, policy)
    if args.output.exists():
        raise ValueError("output exists; choose a fresh artifact directory")
    artifact_relative(args.output, args.artifact_root)
    if not args.binary.is_file() and args.binary == Path("/private/tmp/hydra-beverage-meta-build/release/meta-beverage"):
        candidate = Path("/private/tmp/hydra-beverage-meta-build/out/Products/Release/meta-beverage")
        if candidate.is_file():
            args.binary = candidate
    if not args.binary.is_file():
        raise ValueError("build the pinned Swift executable before launching a model job")
    adapter_hash = file_sha(args.adapter / "adapters.safetensors") if args.adapter else None
    adapter_config_hash = file_sha(args.adapter / "adapter_config.json") if args.adapter else None
    selection = read_json(args.selection) if args.selection else None
    if args.command not in ("infer", "prepare-features") and (args.adapter or args.selection):
        raise ValueError("training starts from base weights; adapter/selection applies only to inference")
    train_rows = sorted((row for row in rows if row["split"] == "train"), key=lambda row: row["image_id"])
    info = json.loads(subprocess.run([str(args.binary), "info"], check=True, capture_output=True, text=True).stdout)
    proof_bytes, proof_hash = verify_base_provenance(args.model, model_id=info["model_id"], revision=info["base_revision"])
    executable_hash = file_sha(args.binary)
    if info["executable_sha256"] != executable_hash:
        raise ValueError("executable changed while reading its provenance")
    proof = json.loads(proof_bytes)
    encoder_config = {key: info[key] for key in ("model_id", "base_revision", "runtime_revision", "runtime_patch_sha256", "executable_sha256", "prompt_sha256", "generation_header", "template_current_date", "reasoning_strength")}
    encoder_config.update(schema_version="beverage-encoder-config-v1", execution_policy=POLICY,
        model_provenance_sha256=proof_hash, image_tokens=args.image_tokens,
        processor_sha256=proof["files"]["processor_config.json"]["sha256"], tokenizer_sha256=proof["files"]["tokenizer.json"]["sha256"],
        tokenizer_config_sha256=proof["files"]["tokenizer_config.json"]["sha256"], chat_template_sha256=proof["files"]["chat_template.jinja"]["sha256"],
        feature_format="safetensors-v1", feature_dtype_policy="frozen_encoder_output", token_dtype="I32")
    encoder_hash = canonical_sha256(encoder_config)
    cache = None
    selected_split = args.split if args.command in ("infer", "prepare-features") else "train"
    if args.command != "prepare-features":
        if not args.feature_cache:
            raise ValueError("language-only execution requires --feature-cache")
        artifact_relative(args.feature_cache, args.artifact_root)
        cache = verify_cache(args.feature_cache, rows=rows, split=selected_split, encoder_sha256=encoder_hash,
            source_manifest_sha256=manifest_sha256(rows), split_policy_sha256=policy_sha)
        if args.command != "infer" and any(entry["outcome"] != "success" for entry in cache["entries"]):
            raise ValueError("training requires every train feature to succeed")
    admission_path = args.cache_admission_selection or args.selection
    admission = read_json(admission_path) if admission_path else None
    if selected_split == "test":
        if not admission or not selection:
            raise ValueError("test cache/inference requires frozen admission and run selection")
        expected_validation = sorted(row["image_id"] for row in rows if row["split"] == "validation")
        for selected in (admission, selection):
            if (selected.get("selected_using") != "train_validation_only" or selected.get("split_policy_sha256") != policy_sha
                    or selected.get("encoder_config_sha256") != encoder_hash or sorted(selected.get("validation_image_ids", [])) != expected_validation
                    or utc(selected["checkpoint_frozen_utc"]) > datetime.now(timezone.utc)):
                raise ValueError("test cache admission differs from frozen validation encoder selection")
        if cache and (cache.get("cache_admission_selection_sha256") != file_sha(admission_path)
                or utc(cache["started_utc"]) < max(utc(admission["checkpoint_frozen_utc"]), utc(selection["checkpoint_frozen_utc"]))):
            raise ValueError("test cache was prepared before both frozen selections")
    inference_config = {
        "schema_version": "beverage-inference-config-v1", "execution_policy": POLICY, "encoder_config_sha256": encoder_hash, "model_id": info["model_id"],
        "base_revision": info["base_revision"], "runtime_revision": info["runtime_revision"],
        "runtime_patch_sha256": info["runtime_patch_sha256"], "vision_release_policy": info["vision_release_policy"], "vision_release_enabled": info["vision_release_enabled"],
        "executable_sha256": executable_hash, "model_provenance_sha256": proof_hash,
        "prompt_sha256": info["prompt_sha256"], "generation_header": info["generation_header"],
        "template_current_date": info["template_current_date"], "reasoning_strength": info["reasoning_strength"],
        "image_tokens": args.image_tokens, "prefill_step": args.prefill_step,
        "max_output_tokens": args.max_output_tokens, "decoding": "greedy",
        "adapter_config_sha256": adapter_config_hash,
        "memory_limit_bytes": args.memory_limit_gb * 1024 ** 3,
        "rss_limit_bytes": args.rss_limit_gb * 1024 ** 3,
    }
    inference_hash = canonical_sha256(inference_config)
    if args.command == "infer":
        frozen = validate_selection(selection, split=args.split, adapter_sha256=adapter_hash, policy_sha256=policy_sha,
            adapter_config_sha256=adapter_config_hash, inference_config_sha256=inference_hash)
    command = [str(args.binary), args.command, "--model", str(args.model.resolve()), "--data-root", str(args.data_root.resolve()), "--manifest", str(args.manifest.resolve()), "--output", str(args.output.resolve()), "--train-manifest-sha256", manifest_sha256(train_rows), "--split-policy-sha256", policy_sha]
    command += ["--model-provenance-sha256", proof_hash, "--source-manifest-sha256", manifest_sha256(rows), "--encoder-config-sha256", encoder_hash]
    if cache:
        command += ["--feature-cache", str(args.feature_cache.absolute()), "--feature-cache-sha256", file_sha(args.feature_cache),
            "--feature-cache-artifact-path", artifact_relative(args.feature_cache, args.artifact_root),
            "--encoder-config-artifact-path", artifact_relative(args.feature_cache.parent / cache["encoder_config_path"], args.artifact_root)]
    if args.command == "prepare-features":
        command += ["--split", args.split]
        if admission_path:
            command += ["--cache-admission-selection-sha256", file_sha(admission_path)]
    for name in ("image_tokens", "prefill_step", "max_answer_tokens", "max_output_tokens", "memory_limit_gb", "rss_limit_gb", "epochs", "layers", "rank", "learning_rate"):
        command += ["--" + name.replace("_", "-"), str(getattr(args, name))]
    if args.steps is not None:
        command += ["--steps", str(args.steps)]
    if args.command == "infer":
        command += ["--split", args.split]
        if args.adapter:
            command += ["--adapter", str(args.adapter.resolve())]
    started = datetime.now(timezone.utc).isoformat()
    # Keep held-out labels outside the runtime process entirely. The child gets
    # train rows for fitting, or a label-free projection for the selected inference split.
    runtime_input_rows = runtime_rows(rows, command=args.command, split=args.split)
    with tempfile.TemporaryDirectory(prefix="hydra-beverage-input-") as temp:
        encoder_path = Path(temp) / "encoder-config.json"
        encoder_path.write_text(json.dumps(encoder_config, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        if args.command == "prepare-features":
            command += ["--encoder-config", str(encoder_path)]
        runtime_manifest = Path(temp) / "manifest.jsonl"
        runtime_manifest.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in runtime_input_rows), encoding="utf-8")
        command[command.index("--manifest") + 1] = str(runtime_manifest)
        # The child reads only local files; stderr contains aggregate memory and bounded diagnostics.
        try:
            run_local_process(command, rss_limit_bytes=args.rss_limit_gb * 1024 ** 3)
        except LocalProcessError as error:
            # A rejected concurrent child must never modify another run's output.
            # RSS/monitor failures identify this live child; Swift records ordinary
            # backend/contract failures inside the directory it created itself.
            record_allowed = error.kind != "local_runtime_failed"
            if not args.output.exists():
                try:
                    args.output.mkdir(parents=True, exist_ok=False)
                    record_allowed = True
                except FileExistsError:
                    record_allowed = False
            failure = args.output / "failure.json"
            if record_allowed and not failure.exists():
                failure.write_text(json.dumps({"schema_version": "beverage-runtime-failure-v1", "kind": error.kind,
                    "phase": "launcher_child", "rss_budget_bytes": args.rss_limit_gb * 1024 ** 3,
                    "guard_limit": "independent sampled 50ms RSS guard; allocation spikes may overshoot"}, sort_keys=True, indent=2) + "\n")
            raise
    if args.command == "prepare-features":
        verify_cache(args.output / "feature-cache.json", rows=rows, split=args.split, encoder_sha256=encoder_hash,
            source_manifest_sha256=manifest_sha256(rows), split_policy_sha256=policy_sha)
        (args.output / "model-provenance.json").write_bytes(proof_bytes)
        print(json.dumps({"output": str(args.output), "command": args.command, "encoder_config_sha256": encoder_hash}))
        return 0
    runtime = read_json(args.output / "runtime.json")
    language_started = runtime["language_started_utc"]
    if utc(cache["completed_utc"]) > utc(language_started):
        raise ValueError("language worker started before cache completion")
    (args.output / "model-provenance.json").write_bytes(proof_bytes)
    (args.output / "inference-config.json").write_text(json.dumps(inference_config, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    prompt_path = args.output / "prompt.txt"
    if file_sha(prompt_path) != info["prompt_sha256"]:
        raise ValueError("runtime prompt differs from its advertised fingerprint")
    if args.command == "infer":
        metadata = {
            "schema_version": "beverage-run-v1", "run_id": args.run_id or args.output.name,
            "run_kind": "adapter" if args.adapter else "baseline", "dataset_kind": args.dataset_kind,
            "model_id": info["model_id"], "base_revision": info["base_revision"],
            "runtime_revision": info["runtime_revision"], "adapter_sha256": adapter_hash,
            "runtime_patch_sha256": info["runtime_patch_sha256"], "vision_release_policy": info["vision_release_policy"], "vision_release_enabled": info["vision_release_enabled"],
            "runtime_config_sha256": file_sha(args.output / "runtime.json"),
            "runtime_config_path": artifact_relative(args.output / "runtime.json", args.artifact_root),
            "executable_sha256": executable_hash,
            "inference_config_sha256": inference_hash,
            "inference_config_path": artifact_relative(args.output / "inference-config.json", args.artifact_root),
            "adapter_config_sha256": adapter_config_hash,
            "adapter_config_path": artifact_relative(args.adapter / "adapter_config.json", args.artifact_root) if args.adapter else None,
            "model_provenance_sha256": proof_hash,
            "model_provenance_path": artifact_relative(args.output / "model-provenance.json", args.artifact_root),
            "prompt_sha256": info["prompt_sha256"], "prompt_path": artifact_relative(prompt_path, args.artifact_root),
            "manifest_sha256": manifest_sha256(rows), "split_policy_sha256": policy_sha,
            "predictions_sha256": file_sha(args.output / "predictions.jsonl"),
            "selected_using": "train_validation_only", "checkpoint_frozen_utc": frozen,
            "test_inference_started_utc": language_started, "language_started_utc": language_started, "inference_split": args.split,
            "execution_policy": POLICY, "language_only": True, "vision_loaded": False,
            "encoder_config_sha256": encoder_hash,
            "encoder_config_path": artifact_relative(args.feature_cache.parent / cache["encoder_config_path"], args.artifact_root),
            "feature_cache_sha256": file_sha(args.feature_cache), "feature_cache_path": artifact_relative(args.feature_cache, args.artifact_root),
        }
        if admission_path:
            metadata.update(cache_admission_selection_sha256=file_sha(admission_path), cache_admission_selection_path=artifact_relative(admission_path,args.artifact_root))
        if args.selection:
            metadata.update(selection_sha256=file_sha(args.selection), selection_path=artifact_relative(args.selection, args.artifact_root))
        if args.adapter:
            training = args.adapter / "training.json"
            metadata.update(adapter_path=artifact_relative(args.adapter / "adapters.safetensors", args.artifact_root),
                training_run_sha256=file_sha(training), training_run_path=artifact_relative(training, args.artifact_root))
        (args.output / "run.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    else:
        training = read_json(args.output / "training.json")
        if training["updated_steps"] <= 0 or training["parameter_delta_l2"] <= 0:
            raise ValueError("runtime did not prove an optimizer update")
        if args.command == "train" and set(training["train_image_ids"]) != {row["image_id"] for row in train_rows}:
            raise ValueError("partial training run preserved, but not accepted as a completed full-train checkpoint")
    print(json.dumps({"output": str(args.output.resolve()), "command": args.command, "runtime_revision": info["runtime_revision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # No source rows, pixels, labels, prompts or raw model generations are printed.
        print(f"local adapter job failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
