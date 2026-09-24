"""Download one immutable IV-CAN-v1 case into an isolated file-only sandbox."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DATASET_NAME = "IV-CAN-v1"
DATASET_ID = "IV-CAN/IV-CAN-v1"
DATASET_REVISION = "f38b9b5ec96b487c6c6496e27f482c1f86df0b7f"
DATASET_URL = "https://huggingface.co/datasets/IV-CAN/IV-CAN-v1"
LICENSE = "CC BY 4.0"
TRANSFORMATION_VERSION = "ivcan-raw-frame-jsonl-v1"
EXPECTED_COLUMNS = (
    "timestamp", "can_id", "is_extended_id", "dlc", "data", "RX_or_TX", "type",
    "is_fd", "domain", "is_attack", "traced_from", "uuid", "is_traced_attack",
)


def _source_path(relative_path: str, case_id: str) -> tuple[str, str]:
    parts = Path(relative_path).parts
    if Path(relative_path).is_absolute() or ".." in parts or len(parts) not in {4, 5} or parts[-1] != "data.csv":
        raise ValueError("Use a repository-relative case data.csv path")
    if parts[0] != "data":
        raise ValueError("Source path must be inside data/")
    if parts[1] == "Benign" and len(parts) == 4:
        category = "Benign"
        resolved_case = parts[2]
    elif parts[1] == "Attack" and len(parts) == 5:
        category = f"Attack/{parts[2]}"
        resolved_case = parts[3]
    else:
        raise ValueError("Expected data/Benign/<case>/data.csv or data/Attack/<family>/<case>/data.csv")
    if resolved_case != case_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case_id):
        raise ValueError("case_id must exactly match the selected repository path")
    return "/".join(parts), category


def import_case(relative_path: str, case_id: str, output_dir: Path, max_bytes: int) -> Path:
    source_path, category = _source_path(relative_path, case_id)
    temp_root = Path(tempfile.gettempdir()).resolve()
    output_dir = output_dir.resolve()
    if output_dir.parent != temp_root or not output_dir.name.startswith("ivcan-import-test-tmp-"):
        raise ValueError("Output must be a new direct child of the operating-system temp directory")
    if output_dir.exists():
        raise FileExistsError("Refusing to overwrite an existing import directory")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    output_dir.mkdir(parents=False)
    raw_path = output_dir / "source-data.csv"
    output_path = output_dir / "observations.jsonl"
    manifest_path = output_dir / "provenance.json"
    url = f"{DATASET_URL}/resolve/{DATASET_REVISION}/{quote(source_path, safe='/')}?download=true"
    request = Request(url, headers={"User-Agent": "AIGATOS-provenance-import/1.0"})
    source_hash = hashlib.sha256()
    size = 0
    try:
        with urlopen(request, timeout=30) as response, raw_path.open("xb") as raw:
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > max_bytes:
                raise ValueError("Selected case exceeds max_bytes; no dataset content was retained")
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Selected case exceeds max_bytes")
                source_hash.update(chunk)
                raw.write(chunk)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Hugging Face download failed ({type(error).__name__})") from error

    digest = source_hash.hexdigest()
    row_count = 0
    with raw_path.open("r", encoding="utf-8-sig", newline="") as source, output_path.open("x", encoding="utf-8", newline="\n") as target:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise ValueError("Downloaded CSV header does not match the pinned IV-CAN-v1 schema")
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed source CSV row {row_number}")
            source_uuid = (row.get("uuid") or "").strip()
            source_record_id = f"{case_id}:{source_uuid}" if source_uuid else f"{case_id}:row:{row_number}"
            observation = {
                "source": "REAL_DATASET",
                "dataset": DATASET_NAME,
                "dataset_revision": DATASET_REVISION,
                "source_case_id": case_id,
                "source_record_id": source_record_id,
                "source_category": category,
                "source_file_sha256": digest,
                "raw_frame": row,
            }
            target.write(json.dumps(observation, ensure_ascii=False, separators=(",", ":")) + "\n")
            row_count += 1

    manifest = {
        "dataset_name": DATASET_NAME,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "dataset_revision": DATASET_REVISION,
        "publisher": "IV-CAN team",
        "license": LICENSE,
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_path,
        "source_file_sha256": digest,
        "source_file_bytes": size,
        "source_case_id": case_id,
        "source_category": category,
        "imported_rows": row_count,
        "transformation_version": TRANSFORMATION_VERSION,
        "transformations": ["Wrap each source CSV row unchanged under raw_frame", "No VIN, vehicle identity, or derived telemetry is created"],
        "limits": [
            "CAN security frames are not OTA telemetry and are not inserted into vehicle or OTA tables",
            "uuid is scoped to a case; source_record_id therefore includes source_case_id",
            "Rows without source uuid use the 1-based physical CSV line as an explicit locator",
            "Dataset labels describe capture/attack categories, not vehicle failures or maintenance outcomes",
        ],
        "outputs": {"observations": output_path.name, "source_copy": raw_path.name},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-path", required=True, help="Pinned repo-relative data/.../<case>/data.csv path")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory under the OS temp directory")
    parser.add_argument("--max-bytes", type=int, default=256 * 1024 * 1024)
    args = parser.parse_args()
    try:
        manifest = import_case(args.source_path, args.case_id, args.output_dir, args.max_bytes)
    except Exception as error:
        parser.error(f"Import blocked: {type(error).__name__}: {error}")
    print(f"Import archived: {manifest.name} (isolated file-only sandbox)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
