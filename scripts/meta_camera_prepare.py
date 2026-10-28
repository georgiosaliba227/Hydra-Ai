"""Print a redacted, read-only plan for one exact prepared camera JPEG."""
import argparse
import json
from pathlib import Path

from backend.meta_accounts import ACCOUNTS
from backend.meta_camera_preparation import prepare_camera


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--account", choices=ACCOUNTS, default=ACCOUNTS[0])
    args = parser.parse_args()
    try:
        report = prepare_camera(args.env_file, args.database, args.image, args.account)
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    except Exception:
        raise SystemExit("Camera preparation refused: invalid local inputs. No request sent or ledger changed.") from None


if __name__ == "__main__":
    main()
