# IV-CAN provenance-first import

The verified source is the Hugging Face dataset `IV-CAN/IV-CAN-v1`, pinned to immutable revision `f38b9b5ec96b487c6c6496e27f482c1f86df0b7f`. Its dataset card identifies the publisher as the IV-CAN team, states that IV-CAN-v1 was produced by that team, declares CC BY 4.0, and documents 134 captures plus the exact `data.csv` column order. The pinned revision contains the dataset card, license, schema, and validator. Attribution is required. Sources: [pinned revision](https://huggingface.co/datasets/IV-CAN/IV-CAN-v1/commit/f38b9b5ec96b487c6c6496e27f482c1f86df0b7f), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

`scripts/import_ivcan_case.py` is a standard-library-only importer. It downloads exactly one selected case file at that immutable revision, checks its header against the pinned schema, preserves every CSV field unchanged in `raw_frame`, records a SHA-256 and UTC retrieval time, writes a per-import provenance manifest, and assigns `source=REAL_DATASET` plus a case-scoped `source_record_id` to every output record. It refuses output outside a new direct child of the OS temp directory and never connects to a database. It does not create VINs, vehicle identities, OTA events, or derived telemetry. The rows are CAN security captures, not OTA maintenance records.

Example (review the chosen case and expected download size before running):

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$importRoot = Join-Path $env:TEMP ('ivcan-import-test-tmp-' + [guid]::NewGuid().ToString('N'))
& 'D:\AIGATOS\.venv\Scripts\python.exe' scripts\import_ivcan_case.py `
  --source-path 'data/Benign/<case-id>/data.csv' `
  --case-id '<case-id>' `
  --output-dir $importRoot `
  --max-bytes 268435456
```

Replace `<case-id>` with an actual ID from the pinned repository manifest; the placeholders are not runnable values. The importer retains the selected raw source file alongside the JSONL. No dataset was downloaded or imported during this work. Before calling any imported record “real,” verify the source case in the pinned manifest and inspect the resulting hashes and provenance manifest. Do not load the output into operational/OTA tables. NASA remains excluded until licensing is clarified; EVIoT/Kaggle remains excluded until provenance is independently validated.

Simulator-generated OTA events are distinct: their existing event metadata carries `source=LIVE_SIMULATION`, `environment=SIMULATED`, and the linked simulation `session_id`/configuration checksum. They are never tagged `REAL_DATASET`.
