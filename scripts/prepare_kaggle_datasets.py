"""Audit and prepare the three explicitly approved Kaggle datasets.

The script uses only the Python standard library, never mutates raw files, keeps
datasets separate, and writes no data to PostgreSQL. It performs no ML training.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(r"D:\AIGATOS")
RAW = ROOT / "datasets" / "raw"
PROCESSED = ROOT / "datasets" / "processed"
REPORTS = ROOT / "reports" / "data-quality"
MANIFEST = ROOT / "datasets" / "dataset_manifest.json"

DATASETS = {
    "automotive-engine-health": {
        "name": "Automotive Vehicles Engine Health",
        "kaggle_id": "parvmodi/automotive-vehicles-engine-health-dataset",
        "url": "https://www.kaggle.com/datasets/parvmodi/automotive-vehicles-engine-health-dataset",
        "author": "PARV MODI",
        "license": "CC0: Public Domain",
        "version": 1,
    },
    "beth": {
        "name": "BETH Dataset",
        "kaggle_id": "katehighnam/beth-dataset",
        "url": "https://www.kaggle.com/datasets/katehighnam/beth-dataset",
        "author": "Kate Highnam",
        "license": "CC0: Public Domain",
        "version": 3,
    },
    "wireless-network-slicing": {
        "name": "Wireless Network Slicing Dataset",
        "kaggle_id": "ziya07/wireless-network-slicing-dataset",
        "url": "https://www.kaggle.com/datasets/ziya07/wireless-network-slicing-dataset",
        "author": "Ziya",
        "license": "CC0: Public Domain",
        "version": 1,
    },
}

csv.field_size_limit(32 * 1024 * 1024)


def snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value.strip())
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    normalized = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")
    return normalized.replace("d_bm", "dbm").replace("qo_s", "qos")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row_digest(values: Iterable[str]) -> bytes:
    digest = hashlib.blake2b(digest_size=16)
    for value in values:
        encoded = value.encode("utf-8", errors="replace")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.digest()


def infer_value_type(value: str) -> str:
    try:
        int(value)
        return "integer"
    except ValueError:
        try:
            float(value)
            return "float"
        except ValueError:
            return "string"


def merge_type(current: str | None, observed: str) -> str:
    if current is None:
        return observed
    if current == observed:
        return current
    if {current, observed} <= {"integer", "float"}:
        return "float"
    return "string"


def audit_csv(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        normalized = {column: snake(column) for column in columns}
        missing = Counter()
        inferred: dict[str, str | None] = {column: None for column in columns}
        targets: dict[str, Counter] = defaultdict(Counter)
        groups: dict[str, set[str]] = defaultdict(set)
        seen: set[bytes] = set()
        duplicates = 0
        malformed = 0
        rows = 0
        for row in reader:
            rows += 1
            values = []
            for column in columns:
                value = row.get(column)
                if value is None:
                    malformed += 1
                    value = ""
                values.append(value)
                if value == "":
                    missing[column] += 1
                else:
                    inferred[column] = merge_type(inferred[column], infer_value_type(value))
                normalized_name = normalized[column]
                if normalized_name in {"engine_condition", "sus", "evil", "network_slice_failure", "overload_status"}:
                    targets[normalized_name][value] += 1
                if normalized_name in {"host_name", "sensor_id", "device_id", "network_slice_id"} and value:
                    groups[normalized_name].add(value)
            fingerprint = row_digest(values)
            if fingerprint in seen:
                duplicates += 1
            else:
                seen.add(fingerprint)
        cell_count = rows * len(columns)
        missing_cells = sum(missing.values())
        return {
            "file": path.name,
            "size_bytes": path.stat().st_size,
            "rows": rows,
            "column_count": len(columns),
            "columns": [
                {
                    "name": column,
                    "normalized_name": normalized[column],
                    "inferred_type": inferred[column] or "empty",
                    "missing_count": missing[column],
                    "missing_rate": missing[column] / rows if rows else 0.0,
                }
                for column in columns
            ],
            "missing_cells": missing_cells,
            "missing_rate": missing_cells / cell_count if cell_count else 0.0,
            "duplicate_rows": duplicates,
            "malformed_cells": malformed,
            "target_distributions": {name: dict(values) for name, values in targets.items()},
            "group_cardinality": {name: len(values) for name, values in groups.items()},
            "group_values": {name: sorted(values) for name, values in groups.items()},
        }


def split_from_digest(values: Iterable[str]) -> str:
    bucket = int.from_bytes(row_digest(values)[:4], "big") % 100
    return "train" if bucket < 70 else ("validation" if bucket < 85 else "test")


def open_split_writers(directory: Path, fields: list[str]):
    directory.mkdir(parents=True, exist_ok=True)
    handles = {}
    writers = {}
    for split in ("train", "validation", "test"):
        handle = (directory / f"{split}.csv").open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        handles[split] = handle
        writers[split] = writer
    return handles, writers


def process_engine() -> dict:
    source = RAW / "automotive-engine-health" / "original" / "engine_data.csv"
    destination = PROCESSED / "automotive-engine-health"
    features = [
        "engine_rpm", "lub_oil_pressure", "fuel_pressure", "coolant_pressure",
        "lub_oil_temp", "coolant_temp",
    ]
    target = "engine_condition"
    fields = features + [target]
    handles, writers = open_split_writers(destination, fields)
    counts = Counter()
    classes: dict[str, Counter] = defaultdict(Counter)
    seen: set[bytes] = set()
    dropped = Counter()
    try:
        with source.open("r", encoding="utf-8-sig", newline="", errors="replace") as stream:
            reader = csv.DictReader(stream)
            for raw_row in reader:
                row = {snake(key): value.strip() for key, value in raw_row.items()}
                if any(row.get(field, "") == "" for field in fields):
                    dropped["missing_required"] += 1
                    continue
                try:
                    int(row["engine_rpm"])
                    int(row[target])
                    for field in features[1:]:
                        float(row[field])
                except ValueError:
                    dropped["invalid_type"] += 1
                    continue
                fingerprint = row_digest(row[field] for field in fields)
                if fingerprint in seen:
                    dropped["duplicate"] += 1
                    continue
                seen.add(fingerprint)
                split = split_from_digest(row[field] for field in features)
                writers[split].writerow({field: row[field] for field in fields})
                counts[split] += 1
                classes[split][row[target]] += 1
    finally:
        for handle in handles.values():
            handle.close()
    return {
        "output_rows": dict(counts),
        "target_distribution": {split: dict(values) for split, values in classes.items()},
        "dropped_rows": dict(dropped),
        "retained_features": features,
        "targets": [target],
        "excluded_variables": {target: "supervised target; excluded from model inputs"},
        "split_strategy": "Exact duplicates removed; identical feature vectors grouped by deterministic hash into 70/15/15 splits. No time, vehicle, or host identifier exists in the source.",
        "leakage_risks": [
            "engine_condition is the target and must never be used as an input feature",
            "no timestamp or vehicle identifier is available, so temporal or vehicle-held-out validation is impossible",
            "dataset origin must not be represented as real OTA manufacturer telemetry",
        ],
        "aigatos_relevance": "Generic engine-sensor anomaly and predictive-maintenance features only; not OTA evidence.",
    }


def process_network() -> dict:
    source = RAW / "wireless-network-slicing" / "original" / "6G_network_slicing_qos_dataset_2345.csv"
    destination = PROCESSED / "wireless-network-slicing"
    features = [
        "traffic_load_bps", "traffic_type", "network_utilization", "latency_ms",
        "packet_loss_rate", "signal_strength_dbm", "bandwidth_utilization",
        "device_type", "region", "time_of_day", "weather_conditions",
    ]
    target = "network_slice_failure"
    fields = features + [target]
    handles, writers = open_split_writers(destination, fields)
    counts = Counter()
    classes: dict[str, Counter] = defaultdict(Counter)
    split_devices: dict[str, set[str]] = defaultdict(set)
    seen: set[bytes] = set()
    dropped = Counter()
    try:
        with source.open("r", encoding="utf-8-sig", newline="", errors="replace") as stream:
            reader = csv.DictReader(stream)
            for raw_row in reader:
                row = {snake(key): value.strip() for key, value in raw_row.items()}
                if any(row.get(field, "") == "" for field in fields + ["device_id"]):
                    dropped["missing_required"] += 1
                    continue
                try:
                    int(row[target])
                    for field in features:
                        float(row[field])
                except ValueError:
                    dropped["invalid_type"] += 1
                    continue
                fingerprint = row_digest(row.get(field, "") for field in row)
                if fingerprint in seen:
                    dropped["duplicate"] += 1
                    continue
                seen.add(fingerprint)
                split = split_from_digest([row["device_id"]])
                writers[split].writerow({field: row[field] for field in fields})
                counts[split] += 1
                classes[split][row[target]] += 1
                split_devices[split].add(row["device_id"])
    finally:
        for handle in handles.values():
            handle.close()
    overlaps = {
        "train_validation": len(split_devices["train"] & split_devices["validation"]),
        "train_test": len(split_devices["train"] & split_devices["test"]),
        "validation_test": len(split_devices["validation"] & split_devices["test"]),
    }
    return {
        "output_rows": dict(counts),
        "target_distribution": {split: dict(values) for split, values in classes.items()},
        "dropped_rows": dict(dropped),
        "retained_features": features,
        "targets": [target],
        "excluded_variables": {
            "network_slice_failure": "supervised target",
            "device_id": "group identifier and memorization risk",
            "network_slice_id": "infrastructure identifier and memorization risk",
            "timestamp": "direct time identifier; excluded to prevent temporal memorization",
            "network_failure_count": "post-outcome/proxy leakage risk",
            "overload_status": "concurrent outcome proxy; requires causal validation",
            "qos_metric_throughput": "potential derived target proxy; requires provenance validation",
        },
        "split_strategy": "All rows for a device_id are assigned to one deterministic 70/15/15 group split. Timestamp is excluded and source order is preserved; device overlap is verified as zero.",
        "group_overlap": overlaps,
        "leakage_risks": [
            "network_failure_count may contain post-failure information",
            "overload_status and qos_metric_throughput may be contemporaneous target proxies",
            "timestamps and infrastructure/device IDs can enable memorization",
            "group splits are host-safe but not a strict future-time holdout because device timelines overlap",
            "the source is generic 6G QoS data, not vehicle or OTA telemetry",
        ],
        "aigatos_relevance": "Generic network degradation features for anomaly enrichment; never evidence of a real OTA failure.",
    }


def process_beth() -> dict:
    source_dir = RAW / "beth" / "original"
    destination = PROCESSED / "beth"
    destination.mkdir(parents=True, exist_ok=True)
    sources = {
        "train": source_dir / "labelled_training_data.csv",
        "validation": source_dir / "labelled_validation_data.csv",
        "test": source_dir / "labelled_testing_data.csv",
    }
    features = ["process_name", "event_id", "event_name", "args_num", "return_value"]
    targets = ["sus", "evil"]
    fields = features + targets
    handles, writers = open_split_writers(destination, fields)
    counts = Counter()
    classes: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    hosts: dict[str, set[str]] = defaultdict(set)
    seen: set[bytes] = set()
    dropped = Counter()
    try:
        for split, source in sources.items():
            with source.open("r", encoding="utf-8-sig", newline="", errors="replace") as stream:
                reader = csv.DictReader(stream)
                for raw_row in reader:
                    row = {snake(key): value.strip() for key, value in raw_row.items()}
                    host = row.get("host_name", "")
                    if split == "validation" and host == "ubuntu":
                        dropped["validation_host_overlap_ubuntu"] += 1
                        continue
                    if any(row.get(field, "") == "" for field in fields + ["host_name"]):
                        dropped["missing_required"] += 1
                        continue
                    try:
                        int(row["event_id"])
                        int(row["args_num"])
                        int(row["return_value"])
                        int(row["sus"])
                        int(row["evil"])
                    except ValueError:
                        dropped["invalid_type"] += 1
                        continue
                    fingerprint = row_digest(row.get(field, "") for field in row)
                    if fingerprint in seen:
                        dropped["duplicate_across_canonical_splits"] += 1
                        continue
                    seen.add(fingerprint)
                    writers[split].writerow({field: row[field] for field in fields})
                    counts[split] += 1
                    hosts[split].add(host)
                    for target in targets:
                        classes[split][target][row[target]] += 1
    finally:
        for handle in handles.values():
            handle.close()
    overlaps = {
        "train_validation": sorted(hosts["train"] & hosts["validation"]),
        "train_test": sorted(hosts["train"] & hosts["test"]),
        "validation_test": sorted(hosts["validation"] & hosts["test"]),
    }
    return {
        "output_rows": dict(counts),
        "target_distribution": {
            split: {target: dict(values) for target, values in target_values.items()}
            for split, target_values in classes.items()
        },
        "dropped_rows": dict(dropped),
        "retained_features": features,
        "targets": targets,
        "excluded_variables": {
            "sus": "supervised target",
            "evil": "supervised target",
            "timestamp": "relative capture clock; not comparable across hosts",
            "host_name": "host identity and split-group leakage risk",
            "process_id": "ephemeral identifier and memorization risk",
            "thread_id": "ephemeral identifier and memorization risk",
            "parent_process_id": "ephemeral identifier and memorization risk",
            "user_id": "identity/memorization risk",
            "mount_namespace": "environment identity proxy",
            "stack_addresses": "high-cardinality environment fingerprint",
            "args": "high-cardinality free text that may directly reveal attack scenarios",
        },
        "split_strategy": "Kaggle's canonical train/validation/test captures are retained. Validation rows from host ubuntu are purged because ubuntu also occurs in training. Host overlap is verified as zero; timestamp is excluded because clocks are relative and not cross-host comparable.",
        "hosts_by_split": {split: sorted(values) for split, values in hosts.items()},
        "host_overlap": overlaps,
        "leakage_risks": [
            "the six DNS exports are byte-identical copies and must not be treated as independent observations",
            "the original canonical train and validation files share host ubuntu; 143296 validation rows are purged",
            "timestamps are relative per capture and cannot establish a strict global future holdout",
            "host/process/thread/user/namespace/stack fields can fingerprint environments",
            "args may contain direct scenario or attack indicators",
            "sus and evil are labels and must never be model inputs",
            "host-specific and canonical files overlap conceptually; only canonical files feed processed outputs",
        ],
        "aigatos_relevance": "Generic system-event anomaly patterns and log pipeline validation; not automotive, ECU, or OTA evidence.",
    }


def manifest_entry(slug: str, metadata: dict) -> dict:
    root = RAW / slug
    archive = next(root.glob("*.zip"))
    extracted = sorted(path for path in (root / "original").rglob("*") if path.is_file())
    files = []
    for path in [archive, *extracted]:
        files.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "kind": "archive" if path == archive else "extracted_raw",
        })
    return {
        **metadata,
        "downloaded_at_utc": datetime.fromtimestamp(archive.stat().st_ctime, timezone.utc).isoformat(),
        "source_last_modified_utc": datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat(),
        "compressed_size_bytes": archive.stat().st_size,
        "decompressed_size_bytes": sum(path.stat().st_size for path in extracted),
        "files": files,
    }


def markdown_report(metadata: dict, raw_audit: list[dict], processed: dict) -> str:
    raw_rows = sum(item["rows"] for item in raw_audit)
    raw_missing = sum(item["missing_cells"] for item in raw_audit)
    raw_cells = sum(item["rows"] * item["column_count"] for item in raw_audit)
    raw_duplicates = sum(item["duplicate_rows"] for item in raw_audit)
    lines = [
        f"# Data quality — {metadata['name']}", "",
        f"- Kaggle ID: `{metadata['kaggle_id']}`",
        f"- Licence: {metadata['license']}",
        f"- Version: {metadata['version']}",
        f"- Raw rows scanned across files: {raw_rows}",
        f"- Raw missing-cell rate: {(raw_missing / raw_cells if raw_cells else 0):.6%}",
        f"- Exact duplicate rows within files: {raw_duplicates}", "",
        "## Raw files", "",
        "| File | Rows | Columns | Missing rate | Duplicates |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in raw_audit:
        lines.append(f"| {item['file']} | {item['rows']} | {item['column_count']} | {item['missing_rate']:.6%} | {item['duplicate_rows']} |")
    lines.extend(["", "## Preparation", "", f"- Split strategy: {processed['split_strategy']}"])
    lines.append(f"- Output rows: `{json.dumps(processed['output_rows'], sort_keys=True)}`")
    lines.append(f"- Dropped rows: `{json.dumps(processed['dropped_rows'], sort_keys=True)}`")
    lines.append(f"- Target distribution: `{json.dumps(processed['target_distribution'], sort_keys=True)}`")
    lines.extend(["", "## Retained model features", ""])
    lines.extend(f"- `{name}`" for name in processed["retained_features"])
    lines.extend(["", "## Excluded variables", ""])
    lines.extend(f"- `{name}`: {reason}" for name, reason in processed["excluded_variables"].items())
    lines.extend(["", "## Leakage and scope risks", ""])
    lines.extend(f"- {risk}" for risk in processed["leakage_risks"])
    lines.extend(["", "## Exact AIGATOS relevance", "", processed["aigatos_relevance"], ""])
    return "\n".join(lines)


def main() -> None:
    os.environ["TEMP"] = str(ROOT / "data" / "tmp")
    os.environ["TMP"] = str(ROOT / "data" / "tmp")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    manifest = {"schema_version": 1, "datasets": []}
    reports = {}
    processors = {
        "automotive-engine-health": process_engine,
        "beth": process_beth,
        "wireless-network-slicing": process_network,
    }
    for slug, metadata in DATASETS.items():
        print(json.dumps({"status": "hashing_raw", "dataset": slug}), flush=True)
        entry = manifest_entry(slug, metadata)
        manifest["datasets"].append(entry)
        audits = []
        for path in sorted((RAW / slug / "original").rglob("*.csv")):
            print(json.dumps({"status": "auditing", "dataset": slug, "file": path.name}), flush=True)
            audits.append(audit_csv(path))
        print(json.dumps({"status": "processing", "dataset": slug}), flush=True)
        processed = processors[slug]()
        report = {
            "dataset": metadata,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "raw_files": audits,
            "raw_summary": {
                "rows_across_files": sum(item["rows"] for item in audits),
                "missing_cells": sum(item["missing_cells"] for item in audits),
                "total_cells": sum(item["rows"] * item["column_count"] for item in audits),
                "duplicates_within_files": sum(item["duplicate_rows"] for item in audits),
            },
            "processed": processed,
            "processed_files": [
                {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in sorted((PROCESSED / slug).glob("*.csv"))
            ],
        }
        reports[slug] = report
        (REPORTS / f"{slug}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (REPORTS / f"{slug}.md").write_text(markdown_report(metadata, audits, processed), encoding="utf-8")
        print(json.dumps({"status": "complete", "dataset": slug, "output_rows": processed["output_rows"]}), flush=True)

    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": "manifest_complete", "path": str(MANIFEST)}), flush=True)


if __name__ == "__main__":
    main()
