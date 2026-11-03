#!/usr/bin/env python3
"""Prepare blinded local photo review packets after saved inference; no model calls."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.beverage_training import evaluation as ev
from ai.beverage_training.identity_packets import checked_file, load_identity_policy, prepare_identity_packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("manifest", "predictions", "split-policy", "run-metadata", "data-root", "artifact-root", "identity-policy", "output"):
        parser.add_argument("--"+field, type=Path, required=True)
    parser.add_argument("--split-policy-sha256", required=True)
    parser.add_argument("--identity-policy-sha256", required=True)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    args = parser.parse_args(argv)
    try:
        policy, identity_sha = load_identity_policy(args.identity_policy)
        if args.identity_policy_sha256 != identity_sha:
            raise ValueError("identity policy fingerprint mismatch")
        for path in (args.manifest, args.predictions, args.split_policy, args.run_metadata):
            checked_file(path)
        rows = ev.read_jsonl(args.manifest)
        predictions = ev.read_jsonl(args.predictions)
        split_policy = ev.read_json(args.split_policy)
        if ev.canonical_sha256(split_policy) != args.split_policy_sha256:
            raise ValueError("split policy fingerprint mismatch")
        ev.validate_manifest(rows, args.data_root, split_policy)
        metadata = ev.read_json(args.run_metadata)
        bindings = dict(manifest_sha256=ev.manifest_sha256(rows), split_policy_sha256=args.split_policy_sha256,
                        predictions_sha256=ev.file_sha256(args.predictions), run_metadata_sha256=ev.file_sha256(args.run_metadata))
        if (metadata.get("inference_split") != args.split
                or any(metadata.get(field) != bindings[field] for field in ("manifest_sha256", "split_policy_sha256", "predictions_sha256"))):
            raise ValueError("saved run does not bind selected split and source bytes")
        output = args.output.absolute()
        artifact_root = args.artifact_root.absolute()
        if (any(part.is_symlink() for part in (artifact_root, *artifact_root.parents))
                or not artifact_root.is_dir() or not output.is_relative_to(artifact_root) or output == artifact_root):
            raise ValueError("output must be inside the explicit nonsymlink artifact root")
        if args.split == "test":
            # This complete legacy gate validates dataset, model, adapter updates,
            # inference selection/cache policy and all original test evidence.
            ev.evaluate_files(manifest_path=args.manifest, predictions_path=args.predictions,
                policy_path=args.split_policy, policy_sha256=args.split_policy_sha256,
                run_metadata_path=args.run_metadata, data_root=args.data_root, artifact_root=artifact_root)
            selection_path = ev.safe_artifact_path(artifact_root, metadata.get("selection_path"))
            if ev.file_sha256(selection_path) != metadata.get("selection_sha256"):
                raise ValueError("selection source bytes changed")
            selection = ev.read_json(selection_path)
            if (selection.get("identity_policy_sha256") != identity_sha
                    or ev._utc(policy["frozen_utc"]) > ev._utc(metadata.get("test_inference_started_utc"))):
                raise ValueError("identity policy was not frozen in selection before test inference")
        else:
            # Validation is development only. Check optional saved artifact
            # bindings when present, without requiring a final-test selection.
            for path_field, hash_field, canonical in (("runtime_config_path", "runtime_config_sha256", False),
                    ("inference_config_path", "inference_config_sha256", True)):
                if path_field in metadata or hash_field in metadata:
                    path = ev.safe_artifact_path(artifact_root, metadata.get(path_field))
                    actual = ev.canonical_sha256(ev.read_json(path)) if canonical else ev.file_sha256(path)
                    if actual != metadata.get(hash_field):
                        raise ValueError("validation artifact differs from saved source bytes")
        prepare_identity_packet(rows, predictions, split=args.split, data_root=args.data_root,
            output=output, policy_path=args.identity_policy, source_bindings=bindings)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        # Never print reference labels, model outputs, source paths or raw errors.
        print(f"Identity packet rejected ({type(error).__name__}); check frozen inputs and provenance.", file=sys.stderr)
        return 2
    print(f"Prepared blinded {args.split} identity review packet; no evaluation or target claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
