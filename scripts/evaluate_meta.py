"""Offline evaluation; never dispatches Meta requests or modifies a ledger."""
import argparse
import json
import os
from pathlib import Path
import stat

from ai.evaluation.models import Dataset, ObservationFile
from ai.evaluation.scoring import evaluate
from backend.meta_provider import strict_json

MAX_FILE_BYTES = 2_097_152


def read_json(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise ValueError("Bounded regular JSON input required")
        body = stream.read(MAX_FILE_BYTES + 1)
    if len(body) > MAX_FILE_BYTES:
        raise ValueError("Input too large")
    return strict_json(body)


def require_private(path: Path) -> None:
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Live evaluation files must be private owned regular files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--authoritative-ledger", type=Path)
    parser.add_argument("--output", type=Path, help="New aggregate-only report; refuses overwrite")
    args = parser.parse_args()
    dataset = Dataset.model_validate(read_json(args.dataset))
    observations = ObservationFile.model_validate(read_json(args.observations))
    live = any(item.mode == "meta_live" for item in observations.observations)
    verifier = None
    if live or any(case.source == "private_owned_input" for case in dataset.cases):
        require_private(args.dataset)
        require_private(args.observations)
    if live:
        if args.authoritative_ledger is None or not args.authoritative_ledger.is_absolute():
            raise ValueError("Explicit absolute authoritative ledger path required")
        from ai.evaluation.evidence import ledger_verifier
        verifier = ledger_verifier(args.authoritative_ledger)
    report = evaluate(dataset, observations, verifier)
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Evaluation refused: check input schema, private-file permissions and authoritative evidence. No provider request was sent.") from None
