#!/usr/bin/env python3
"""Offline strict evaluator; never invokes inference or overwrites reports."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.beverage_training.evaluation import evaluate_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--split-policy", type=Path, required=True)
    parser.add_argument("--split-policy-sha256", required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output already exists; choose a new report path")
        report = evaluate_files(manifest_path=args.manifest, predictions_path=args.predictions,
            policy_path=args.split_policy, policy_sha256=args.split_policy_sha256,
            run_metadata_path=args.run_metadata, data_root=args.data_root, artifact_root=args.artifact_root)
        # Exclusive creation remains safe if another process writes after the check.
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Do not echo input contents, prediction error strings, image paths or model output.
        print(f"Evaluation rejected ({type(error).__name__}); check frozen inputs and provenance.", file=sys.stderr)
        return 2
    print(f"{report['measurement_class']}: {report['joint']['correct']}/{report['joint']['total']} joint; adapter target met={report['adapter_target_met']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
