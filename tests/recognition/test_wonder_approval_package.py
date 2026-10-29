"""The checked-in approval package must match the payloads the code would send."""
from pathlib import Path
import re

from backend.wonder_assistant import assistant_payload
from backend.wonder_hydration import input_bound, payload_sha256, wonder_payload, worst_case_micro_usd

PACKAGE = Path(__file__).resolve().parents[2] / "docs" / "WONDER_DEMO_APPROVAL.md"


def test_documented_hashes_and_bounds_match_current_payloads():
    text = PACKAGE.read_text()
    for label, payload in (("scenario `complete`", wonder_payload("complete")),
                           ("question `hot_weather`", assistant_payload("hot_weather"))):
        row = re.search(r"\| " + re.escape(label) + r" \| `([0-9a-f]{64})` \| ([\d,]+) \| 512 \| \$([\d.]+) \|", text)
        assert row, label
        bound = input_bound(payload)
        assert row.group(1) == payload_sha256(payload), f"{label}: regenerate the approval package"
        assert int(row.group(2).replace(",", "")) == bound
        assert row.group(3) == f"{worst_case_micro_usd(bound) / 1e6:.6f}"
