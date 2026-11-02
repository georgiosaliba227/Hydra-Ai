#!/usr/bin/env python3
"""Apply only Hydra's reviewed patch to the exact official MLX runtime revision."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_state(repository: Path, evidence: dict) -> str:
    states = []
    for name, hashes in evidence["files"].items():
        actual = digest(repository / name)
        if actual == hashes["original_sha256"]:
            states.append("original")
        elif actual == hashes["patched_sha256"]:
            states.append("patched")
        else:
            raise ValueError("runtime source differs from reviewed original/patched bytes")
    if len(set(states)) != 1:
        raise ValueError("runtime patch is only partially applied")
    return states[0]


def validate_source_tree(repository: Path, evidence: dict) -> None:
    changed = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=repository, text=True).splitlines()
    if set(changed) - evidence["files"].keys():
        raise ValueError("runtime has additional unreviewed source modifications")
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=repository, text=True).splitlines()
    if untracked:
        raise ValueError("runtime contains unreviewed untracked files")


def apply(repository: Path) -> str:
    evidence = json.loads((HERE / "Patches/provenance.json").read_text())
    patch = HERE / "Patches/0001-release-frozen-vision.patch"
    if digest(patch) != evidence["patch_sha256"]:
        raise ValueError("reviewed patch fingerprint mismatch")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    if revision != evidence["upstream_revision"]:
        raise ValueError("runtime revision differs from reviewed pin")
    validate_source_tree(repository, evidence)
    state = source_state(repository, evidence)
    if state == "original":
        for name in evidence["files"]:
            path = repository / name
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=repository, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=repository, check=True)
    if source_state(repository, evidence) != "patched":
        raise ValueError("patched runtime byte verification failed")
    marker = (HERE / "Sources/BeverageCore/RuntimePatch.swift").read_text()
    if evidence["patch_sha256"] not in marker:
        raise ValueError("compiled patch provenance constant differs from patch")
    return evidence["patch_sha256"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch", type=Path, default=Path("/private/tmp/hydra-beverage-meta-build"))
    p.add_argument("--repository", type=Path)
    args = p.parse_args()
    repository = args.repository or args.scratch / "checkouts/mlx-swift-lm"
    print(json.dumps({"runtime_patch_sha256": apply(repository), "repository": str(repository)}, sort_keys=True))


if __name__ == "__main__":
    main()
