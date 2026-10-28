"""Pinned public-study ingestion; local numeric allowlists, never identity export.

No spreadsheet dependency: this narrow reader supports only the checksum-pinned
OOXML workbook. It does not execute formulas, macros, or external relationships.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

SOURCES = {
    "spectrophon": {
        "study_id": "spectrophon-v1",
        "url": "https://data.mendeley.com/public-files/datasets/jt22782wjh/files/a6427fc3-3419-482f-a91c-33e3df048ccf/file_downloaded",
        "sha256": "479a34372203db550fa9d8b55c1ba7f0fe9dbaa88cb870072ea477db4a123ea3",
        "license": "CC-BY-4.0", "filename": "spectrophon.xlsx",
    },
    "qde": {
        "study_id": "qde-v1",
        "url": "https://physionet.org/files/qde/1.0.0/dehydration_estimation.csv",
        "sha256": "186f24f567eee623e475f6556217344a9cc3a522d969d76df02ffe5820628074",
        "license": "ODC-By-1.0", "filename": "qde.csv",
    },
}
MAX_BYTES = 2_000_000
_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def checked_bytes(path: Path | str, source: str) -> bytes:
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("source file exceeds limit")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCES[source]["sha256"]:
        raise ValueError("source checksum mismatch; refuse unreviewed data")
    return payload


def download_source(source: str, cache_dir: Path | str) -> Path:
    """Opt-in public download. Cache outside the repository; never send data out."""
    metadata = SOURCES[source]
    directory = Path(cache_dir).resolve()
    repository = Path(__file__).resolve().parents[2]
    if directory == repository or repository in directory.parents:
        raise ValueError("raw study cache must be outside the repository")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / metadata["filename"]
    if destination.exists():
        checked_bytes(destination, source)
        return destination
    request = Request(metadata["url"], headers={"User-Agent": "HydraAI-study-ingestion/1"})
    with urlopen(request, timeout=30) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
        raise ValueError("download size/checksum rejected")
    destination.write_bytes(payload)
    destination.chmod(0o600)
    return destination


def _number(value: Any, lower: float, upper: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("missing or invalid numeric measurement") from None
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError("measurement outside accepted bounds")
    return result


def _record(source: str, subject: int, index: int, duration: float,
            pre_mass: float, age: float, target: float, target_name: str,
            method: str, speed: float | None = None) -> dict[str, Any]:
    study = SOURCES[source]["study_id"]
    return {
        "record_id": f"{study}:{subject:03}:{index:02}",
        "participant_id": f"{study}:{subject:03}", "study_id": study,
        "synthetic": False, "target_name": target_name,
        "target_value_ml": round(_number(target, 0, 10000), 6),
        "duration_minutes": duration, "pre_mass_kg": pre_mass,
        "age_years": age, "temperature_c": None, "humidity_percent": None,
        "running_speed_kmh": speed, "target_method": method,
        "source_sha256": SOURCES[source]["sha256"],
        "source_license": SOURCES[source]["license"],
    }


def _spectrophon_rows(payload: bytes) -> list[dict[str, str]]:
    # Resolve only approved metadata labels and numeric cells. Identity-bearing
    # shared strings are never returned, logged, or included in error messages.
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(info.file_size for info in archive.infolist()) > 10_000_000:
            raise ValueError("expanded workbook exceeds limit")
        strings = ["".join(node.itertext()) for node in ET.fromstring(
            archive.read("xl/sharedStrings.xml")).findall("s:si", _NS)]
        result = []
        identity_groups: dict[str, int] = {}
        for row in ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).findall("s:sheetData/s:row", _NS):
            allowed = {}
            for cell in row:
                column = re.match(r"[A-Z]+", cell.attrib["r"])[0]
                if column not in {"A", "D", "E", "F", "J"}:
                    continue
                value = cell.find("s:v", _NS)
                if value is None or value.text is None:
                    continue
                if cell.attrib.get("t") == "s":
                    label = strings[int(value.text)]
                    if (column == "A" and (label in {"initial", "final", "Gender"} or re.fullmatch(r"Subject no\. \d+", label))) or (column == "F" and label == "total weight loss"):
                        allowed[column] = label
                else:
                    allowed[column] = value.text
            if allowed.get("A") == "Gender":
                # Identity is consulted only locally for conservative repeat
                # grouping. Neither its text nor a reversible/hash encoding is
                # exported. Equal names are grouped; this cannot prove identity.
                identity_cell = next((cell for cell in row if re.match(r"[A-Z]+", cell.attrib["r"])[0] == "G"), None)
                if identity_cell is None or identity_cell.attrib.get("t") != "s":
                    raise ValueError("missing private grouping key")
                identity_value = identity_cell.find("s:v", _NS)
                if identity_value is None:
                    raise ValueError("missing private grouping key")
                key = " ".join(strings[int(identity_value.text)].casefold().split())
                if not key:
                    key = "__missing_identity_group__"
                if key not in identity_groups:
                    identity_groups[key] = len(identity_groups) + 1
                allowed["participant_group"] = str(identity_groups[key])
            result.append(allowed)
    return result


def load_spectrophon(path: Path | str) -> list[dict[str, Any]]:
    """200 90-minute study blocks, 198 conservative participant groups.

The public workbook contains identity fields: never upload or commit it. We
export only numeric fields with newly generated study/block IDs. Missing urine
and non-sweat corrections mean this is not a pure sweat-loss measurement.
"""
    rows = _spectrophon_rows(checked_bytes(path, "spectrophon"))
    blocks: list[list[dict[str, str]]] = []
    subject_labels = set()
    for row in rows:
        if row.get("A", "").startswith("Subject no."):
            if row["A"] in subject_labels:
                raise ValueError("duplicate subject block")
            subject_labels.add(row["A"])
            blocks.append([])
        if blocks:
            blocks[-1].append(row)
    if len(blocks) != 200:
        raise ValueError("unexpected study subject count")
    records = []
    for subject, block in enumerate(blocks, 1):
        try:
            initial = next(row for row in block if row.get("A") == "initial")
            final = next(row for row in block if row.get("A") == "final")
            age_row = next(row for row in block if row.get("A") == "Gender")
            target_index = next(i for i, row in enumerate(block) if row.get("F") == "total weight loss")
            pre = _number(initial.get("E"), 30, 250)
            post = _number(final.get("E"), 30, 250)
            age = _number(age_row.get("D"), 18, 100)
            intake = _number(initial.get("J"), 0, 5000) - _number(final.get("J"), 0, 5000)
            if intake < 0:
                raise ValueError("negative consumed water")
            target = _number(block[target_index + 1].get("F"), 0, 10) * 1000
            reconstructed = (pre - post) * 1000 + intake
            if abs(target - reconstructed) > 1:
                raise ValueError("mass-balance target disagreement")
        except (StopIteration, IndexError):
            raise ValueError("incomplete subject block") from None
        record = _record("spectrophon", subject, 1, 90., pre, age, target,
            "corrected_mass_loss_proxy_ml", "study mass loss plus consumed water; urine and non-sweat losses uncorrected")
        record["participant_id"] = f"spectrophon-v1:{int(age_row['participant_group']):03}"
        records.append(record)
    return records


def load_qde(path: Path | str) -> list[dict[str, Any]]:
    """Cumulative uncorrected mass loss; keep all intervals of a subject together."""
    rows = list(csv.DictReader(io.StringIO(checked_bytes(path, "qde").decode("utf-8-sig"))))
    groups: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        subject = int(_number(row.get("id"), 1, 10))
        groups.setdefault(subject, []).append(row)
    if len(groups) != 10:
        raise ValueError("unexpected QDE subject count")
    records = []
    mass_key = "weight measured using Kern DE 150K2D [kg]"
    for subject, observations in sorted(groups.items()):
        observations.sort(key=lambda row: _number(row.get("running interval"), 0, 8))
        if [row["running interval"] for row in observations] != [str(i) for i in range(9)]:
            raise ValueError("missing or duplicated QDE interval")
        baseline = observations[0]
        pre = _number(baseline.get(mass_key), 30, 250)
        age = _number(baseline.get("age [years]"), 18, 100)
        speed = _number(baseline.get("running speed [km/h]"), 1, 30)
        for interval, row in enumerate(observations[1:], 1):
            target = (pre - _number(row.get(mass_key), 30, 250)) * 1000
            records.append(_record("qde", subject, interval, interval * 15., pre, age, target,
                "body_mass_loss_proxy_ml", "uncorrected cumulative scale mass loss; no intake; includes protocol rest periods", speed))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Download pinned public sources; raw cache must remain outside repo")
    parser.add_argument("--delete-raw", action="store_true", help="Delete downloaded raw sources after successful sanitization")
    args = parser.parse_args()
    records = []
    paths = []
    for source, loader in (("spectrophon", load_spectrophon), ("qde", load_qde)):
        path = download_source(source, args.cache_dir) if args.download else args.cache_dir / SOURCES[source]["filename"]
        records.extend(loader(path))
        paths.append(path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    if args.delete_raw:
        for path in paths:
            path.unlink()
    print(json.dumps({"records": len(records), "studies": 2, "identity_fields_exported": False}))


if __name__ == "__main__":
    main()
