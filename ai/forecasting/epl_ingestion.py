"""Checksum-pinned EPL study adapter; numeric allowlists, no formula execution.

The two source sessions contain different people. This is a separate supervised
mass-balance proxy task, never a longitudinal personal-calibration dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

SOURCE = {
    "study_id": "epl-v1",
    "url": "https://ndownloader.figshare.com/files/52631492",
    "landing_url": "https://figshare.com/articles/dataset/Fluid_Balance_and_Sweat_Sodium_Study_Data/28498148",
    "paper_url": "https://journals.sagepub.com/doi/full/10.1177/17479541251353603",
    "filename": "epl-fluid-balance.xlsx", "size_bytes": 166216,
    "sha256": "b7c0ca278355ab9c37a4eed4b22d0be4e67964929eaf5914edf24ede9fb396df",
    "license": "CC-BY-4.0",
    "attribution": "Foo, Tester, Markakis, Sabou, Close, McCubbin and Morton (2025), Fluid Balance and Sweat Sodium Study Data, doi:10.6084/m9.figshare.28498148; study doi:10.1177/17479541251353603",
}
MAX_BYTES = 2_000_000
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SESSIONS = (
    {"index": 1, "sheet": 2, "count": 14, "ids": range(1, 15), "duration": 84.,
     "temperature": 19., "humidity": 45., "intake": "I", "target": "L", "rate": "Q", "metadata_row": 20},
    {"index": 2, "sheet": 3, "count": 17, "ids": range(15, 32), "duration": 75.,
     "temperature": 23., "humidity": 67., "intake": "K", "target": "M", "rate": "R", "metadata_row": 23},
)


def _outside_repository(path: Path) -> None:
    path = path.resolve()
    repository = Path(__file__).resolve().parents[2]
    if (path == repository or repository in path.parents
            or any((parent / ".git").exists() for parent in (path, *path.parents))):
        raise ValueError("study files must remain outside the repository")


def _checked(payload: bytes) -> bytes:
    if len(payload) != SOURCE["size_bytes"] or hashlib.sha256(payload).hexdigest() != SOURCE["sha256"]:
        raise ValueError("source_size_or_checksum_mismatch")
    return payload


def download_epl(cache_dir: Path | str) -> Path:
    """Explicit, bounded public download to a private cache outside this checkout."""
    directory = Path(cache_dir).resolve()
    _outside_repository(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("study_cache_must_be_owned_and_private")
    destination = directory / SOURCE["filename"]
    if destination.exists():
        if destination.stat().st_size > MAX_BYTES:
            raise ValueError("source_size_or_checksum_mismatch")
        _checked(destination.read_bytes())
        return destination
    request = Request(SOURCE["url"], headers={"User-Agent": "HydraAI-EPL-study-ingestion/1"})
    with urlopen(request, timeout=30) as response:
        payload = _checked(response.read(MAX_BYTES+1))
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    return destination


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    data = archive.read(name)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("invalid_workbook")
    return ET.fromstring(data)


def _cells(archive: zipfile.ZipFile, sheet: int) -> dict[str, ET.Element]:
    result = {}
    for cell in _xml(archive, f"xl/worksheets/sheet{sheet}.xml").findall(".//s:c", NS):
        address = cell.attrib["r"]
        if address in result:
            raise ValueError("duplicate_workbook_cell")
        result[address] = cell
    return result


def _text(cells: dict, strings: list[str], address: str) -> str:
    try:
        cell = cells[address]
        value = cell.find("s:v", NS)
        if cell.attrib.get("t") != "s" or value is None or value.text is None:
            raise ValueError
        index = int(value.text)
        if not 0 <= index < len(strings):
            raise ValueError
        return strings[index]
    except (KeyError, ValueError, IndexError):
        raise ValueError("invalid_workbook_label") from None


def _number(cells: dict, address: str, lower: float, upper: float) -> float:
    try:
        cell = cells[address]
        value = cell.find("s:v", NS)
        # A cached formula result is permitted, but never evaluated. Missing,
        # string, error or nonfinite caches cannot become measurements.
        if cell.attrib.get("t", "n") != "n" or value is None or value.text is None:
            raise ValueError
        result = float(value.text)
        if not math.isfinite(result) or not lower <= result <= upper:
            raise ValueError
        return result
    except (KeyError, TypeError, ValueError):
        raise ValueError("invalid_cached_numeric_measurement") from None


def load_epl(path: Path | str) -> list[dict]:
    """Validate all 31 target/rate reconstructions, then export pre-work covariates.

    Fluid intake fields are litres, despite shortened source column labels.
    Paper methods document no urination; respiratory/metabolic changes remain
    uncorrected. No individual measurement error bounds are supplied or invented.
    """
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("source_size_or_checksum_mismatch")
    payload = _checked(path.read_bytes())
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if (len(entries) > 128 or len({entry.filename for entry in entries}) != len(entries)
                    or sum(entry.file_size for entry in entries) > 10_000_000):
                raise ValueError("invalid_workbook")
            strings = ["".join(node.itertext()) for node in _xml(archive, "xl/sharedStrings.xml").findall("s:si", NS)]
            records, seen = [], set()
            for session in SESSIONS:
                cells = _cells(archive, session["sheet"])
                labels = {"A1": "Name", "B1": "Age", "D1": "Pre-training weight (kg)", "F1": "Post-training weight (kg)",
                    session["intake"]+"1": "Fluid intake" if session["index"] == 1 else "Fluid Intake",
                    session["target"]+"1": "Sweat Loss (L)" if session["index"] == 1 else "Total Sweat Loss (L)",
                    session["rate"]+"1": "Sweat rate (L/hr)"}
                if any(_text(cells, strings, address) != label for address, label in labels.items()):
                    raise ValueError("unreviewed_workbook_headers")
                for offset, label, expected in (
                    (0, "Training Duration (min)", session["duration"]),
                    (1, "Environmental Temperature (°C)", session["temperature"]),
                    (2, "Relative Humidity (%)", session["humidity"]),
                ):
                    row = session["metadata_row"]+offset
                    if _text(cells, strings, f"A{row}") != label or _number(cells, f"B{row}", -60, 1440) != expected:
                        raise ValueError("unreviewed_session_context")
                session_ids = set()
                for row in range(2, session["count"]+2):
                    match = re.fullmatch(r"Participant ([1-9][0-9]?)", _text(cells, strings, f"A{row}"))
                    if match is None or int(match[1]) not in session["ids"] or int(match[1]) in seen:
                        raise ValueError("invalid_or_duplicate_anonymous_participant")
                    participant = int(match[1]); seen.add(participant); session_ids.add(participant)
                    age = _number(cells, f"B{row}", 18, 100)
                    pre = _number(cells, f"D{row}", 30, 250)
                    post = _number(cells, f"F{row}", 30, 250)
                    consumed_l = _number(cells, f"{session['intake']}{row}", 0, 10)
                    loss_l = _number(cells, f"{session['target']}{row}", 0, 10)
                    rate = _number(cells, f"{session['rate']}{row}", 0, 10)
                    if abs((pre-post+consumed_l)*1000-loss_l*1000) > 1e-6:
                        raise ValueError("mass_balance_target_disagreement")
                    if abs(loss_l*60/session["duration"]-rate) > 1e-8:
                        raise ValueError("duration_rate_disagreement")
                    records.append({
                        "record_id": f"epl-v1:{participant:03}:01", "participant_id": f"epl-v1:{participant:03}",
                        "study_id": SOURCE["study_id"], "session_id": f"epl-v1:session-{session['index']}",
                        "synthetic": False, "target_name": "intake_corrected_mass_loss_proxy_ml",
                        "target_value_ml": round(loss_l*1000, 6), "duration_minutes": session["duration"],
                        "pre_mass_kg": pre, "age_years": age,
                        "temperature_c": session["temperature"], "humidity_percent": session["humidity"],
                        "environment_provenance": "source_shared_session_context_not_independent_environment_samples",
                        "target_method": "towel-dried minimal-clothing mass change plus measured fluid intake; protocol observed no urination; respiratory and metabolic changes uncorrected",
                        "measurement_error_bounds": None, "source_sha256": SOURCE["sha256"],
                        "source_license": SOURCE["license"],
                    })
                if session_ids != set(session["ids"]):
                    raise ValueError("invalid_or_duplicate_anonymous_participant")
    except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, RuntimeError):
        raise ValueError("invalid_workbook") from None
    return sorted(records, key=lambda row: row["record_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="sanitized per-person records; keep outside repository")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--delete-raw", action="store_true")
    args = parser.parse_args()
    _outside_repository(args.output.resolve())
    path = download_epl(args.cache_dir) if args.download else args.cache_dir/SOURCE["filename"]
    rows = load_epl(path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(json.dumps(rows, indent=2, sort_keys=True, allow_nan=False)+"\n")
    if args.delete_raw:
        path.unlink()
    print(json.dumps({"study_id": SOURCE["study_id"], "records": len(rows), "participants": len(rows),
                      "identity_fields_exported": False, "target_and_rate_checks": "passed"}))


if __name__ == "__main__":
    main()
