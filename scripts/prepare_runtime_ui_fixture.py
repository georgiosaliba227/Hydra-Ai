#!/usr/bin/env python3
"""Seed the opt-in runtime UI test in an empty synthetic Simulator history.

Run CalibrationHistoryUITests first with its documented synthetic connection.
Pin the profile UUID captured from that successful synthetic setup. The helper
does not infer a backend connection from a random UUID or inspect Keychain.
This helper never reads Keychain, uses a physical device, starts a provider, or
changes production startup. It refuses nonempty or ambiguous saved histories.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
from uuid import UUID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True)
    parser.add_argument("--expected-profile", required=True, type=UUID,
                        help="Profile UUID captured from the successful synthetic CalibrationHistoryUITest setup")
    parser.add_argument("--confirm-synthetic-fixture", action="store_true")
    args = parser.parse_args()
    if not args.confirm_synthetic_fixture:
        parser.error("Explicit synthetic-fixture confirmation is required")
    root = Path(__file__).resolve().parents[1]
    fixture = root / "ios/HydraAITests/Fixtures/RuntimeV3/runtime-v3-selected-request.json"
    records = json.loads(fixture.read_text())["samples"]
    if (len(records) != 6 or {UUID(row["event_id"]) for row in records} != {UUID(int=i) for i in range(1, 7)}
            or any(row["measurement"]["provenance"] != ["user_entered_manual_weighing"]
                   or row["errors"]["provenance"] != ["user_reported_instrument_error_bounds"] for row in records)):
        raise SystemExit("Unexpected synthetic fixture; nothing written")
    bundle = "com.georgiosaliba.hydraai"
    container = Path(subprocess.check_output(
        ["xcrun", "simctl", "get_app_container", args.simulator, bundle, "data"], text=True).strip())
    directory = container / "Library/Application Support/HydraAI/manual-calibration-v1"
    if directory.is_symlink():
        raise SystemExit("Unexpected history directory; nothing written")
    files = list(directory.glob("*.json")) if directory.is_dir() else []
    if len(files) != 1:
        raise SystemExit("Run the synthetic CalibrationHistoryUITest first; exactly one empty profile is required")
    target = files[0]
    if UUID(target.stem) != args.expected_profile:
        raise SystemExit("The empty profile does not match the pinned synthetic setup; nothing written")
    # Finish any app-side save before deciding that this profile is empty.
    stopped = subprocess.run(["xcrun", "simctl", "terminate", args.simulator, bundle], capture_output=True)
    if stopped.returncode != 0:
        raise SystemExit("Test app termination was not confirmed; launch the test app and retry. Nothing written")
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 262144:
        raise SystemExit("Unexpected history file; nothing written")
    saved = json.loads(target.read_text())
    if (set(saved) != {"version", "profile", "records"} or saved["version"] != 1 or saved["records"] != []
            or UUID(saved["profile"]) != args.expected_profile):
        raise SystemExit("History is not the empty synthetic profile; nothing written")
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    latest = max(parse(row["observed_at"]) for row in records)
    shift = datetime.now(timezone.utc) - timedelta(days=1) - latest
    for row in records:
        row["observed_at"] = (parse(row["observed_at"]) + shift).isoformat().replace("+00:00", "Z")
    saved["records"] = records
    # In-place writing retains protection and backup attributes. The test app
    # is already stopped and cannot add records after the empty-history check.
    descriptor = os.open(target, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(saved, handle, separators=(",", ":"), allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps({"status": "prepared", "origin": "invented_manual_ui_fixture",
                      "records": 6, "processing_consent_saved": False, "meta_consent_saved": False}))


if __name__ == "__main__":
    main()
