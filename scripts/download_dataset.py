#!/usr/bin/env python3
"""Download the public WM-811K archive and extract its original data file.

Uses only Python's standard library. Does not execute or deserialize pickle data.
"""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from datetime import datetime, timezone
import urllib.request
import zipfile


SOURCE_PAGE = "https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map"
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/qingyi/wm811k-wafer-map"
CHUNK = 1024 * 1024


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    raw = root / "data" / "raw"
    cache = root / "build" / "dataset_download"
    raw.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    target = raw / "LSWMD.pkl"
    if target.exists():
        print("Dataset already exists; preserving it without replacement.", flush=True)
        print(json.dumps({"path": str(target), "bytes": target.stat().st_size,
                          "sha256": sha256_file(target)}), flush=True)
        return

    archive = cache / "wm811k.zip"
    started = time.monotonic()
    if not archive.exists() or not zipfile.is_zipfile(archive):
        part = cache / "wm811k.zip.part"
        request = urllib.request.Request(
            DOWNLOAD_URL,
            headers={"User-Agent": "wafer-riscv-project/1.0", "Accept": "application/zip"},
        )
        print("Downloading the original public WM-811K dataset...", flush=True)
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" in content_type.lower() or "json" in content_type.lower():
                raise RuntimeError("Download returned a webpage/API response instead of a ZIP archive.")
            if response.status != 200:
                raise RuntimeError("Expected a complete download (HTTP 200), got HTTP %s." % response.status)
            expected = response.headers.get("Content-Length")
            expected = int(expected) if expected else None
            received = 0
            next_notice = 16 * CHUNK
            with part.open("wb") as output:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                    if received >= next_notice:
                        print("Downloaded %.1f MiB" % (received / CHUNK), flush=True)
                        next_notice += 16 * CHUNK
            if expected is not None and received != expected:
                raise RuntimeError("Incomplete archive: expected %s bytes, received %s." % (expected, received))
        if not zipfile.is_zipfile(part):
            raise RuntimeError("The downloaded file is not a valid ZIP archive.")
        part.replace(archive)

    print("Validating and extracting LSWMD.pkl without deserializing it...", flush=True)
    temporary = raw / "LSWMD.pkl.part"
    digest = hashlib.sha256()
    with zipfile.ZipFile(archive) as dataset_zip:
        members = [item for item in dataset_zip.infolist()
                   if not item.is_dir() and Path(item.filename).name.lower() == "lswmd.pkl"]
        if len(members) != 1:
            raise RuntimeError("Expected exactly one LSWMD.pkl entry, found %s." % len(members))
        member = members[0]
        if member.file_size <= 0 or member.file_size > 10 * 1024 ** 3:
            raise RuntimeError("Unexpected dataset size: %s bytes." % member.file_size)
        if shutil.disk_usage(raw).free < member.file_size + 128 * CHUNK:
            raise RuntimeError("Insufficient free disk space to extract the dataset.")
        written = 0
        with dataset_zip.open(member) as source, temporary.open("wb") as output:
            while True:
                chunk = source.read(CHUNK)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                written += len(chunk)
        # Reading the ZIP member to EOF also checks its stored CRC.
        if written != member.file_size:
            raise RuntimeError("Extracted dataset length does not match ZIP metadata.")
        temporary.replace(target)
        zip_entry = member.filename
        zip_crc32 = "%08x" % member.CRC

    provenance = {
        "dataset": "WM-811K",
        "source_page": SOURCE_PAGE,
        "download_endpoint": DOWNLOAD_URL,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive": {"name": archive.name, "bytes": archive.stat().st_size,
                    "sha256": sha256_file(archive)},
        "file": {"path": "data/raw/LSWMD.pkl", "bytes": target.stat().st_size,
                 "sha256": digest.hexdigest(), "archive_entry": zip_entry,
                 "zip_crc32": zip_crc32},
        "validation": "ZIP member CRC and length checked; SHA-256 recorded locally; no independently published checksum compared.",
        "processing": "Original pickle extracted only; not deserialized, selected, preprocessed, or used for training.",
    }
    (raw / "dataset_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(provenance, indent=2), flush=True)
    print("Completed in %.1f seconds." % (time.monotonic() - started), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Dataset preparation failed: %s" % error, file=sys.stderr, flush=True)
        sys.exit(1)
