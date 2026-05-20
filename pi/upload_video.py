#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a wildlife camera video to the Cloudflare Worker API.")
    parser.add_argument("--file", required=True, help="Path to the mp4 file")
    parser.add_argument("--trap-id", required=True, help="Trap identifier, e.g. YMK-001")
    parser.add_argument("--captured-at", required=True, help="ISO 8601 timestamp, e.g. 2026-05-18T02:14:00+09:00")
    parser.add_argument("--note", default=None, help="Optional hunter note")
    parser.add_argument("--api-url", default=os.getenv("WILDLIFE_API_URL"), help="Worker API base URL")
    parser.add_argument("--device-token", default=os.getenv("WILDLIFE_DEVICE_TOKEN"), help="Device API token")
    parser.add_argument("--queue-dir", default=os.getenv("WILDLIFE_QUEUE_DIR", "./upload_queue"), help="Directory for retry queue records")
    args = parser.parse_args()

    api_url = (args.api_url or "").rstrip("/")
    device_token = args.device_token or ""
    file_path = Path(args.file)

    if not api_url:
      print("WILDLIFE_API_URL or --api-url is required", file=sys.stderr)
      return 2
    if not device_token:
      print("WILDLIFE_DEVICE_TOKEN or --device-token is required", file=sys.stderr)
      return 2
    if not file_path.is_file():
      print(f"File not found: {file_path}", file=sys.stderr)
      return 2

    queue_dir = Path(args.queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "file": str(file_path.resolve()),
        "trap_id": args.trap_id,
        "captured_at": args.captured_at,
        "note": args.note,
        "created_at": int(time.time()),
    }

    try:
        upload_one(api_url, device_token, file_path, args.trap_id, args.captured_at, args.note)
        print(f"Uploaded: {file_path}")
        return 0
    except Exception as exc:
        queue_file = queue_dir / f"{int(time.time())}-{file_path.name}.json"
        queue_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Upload failed and queued: {queue_file}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


def upload_one(api_url: str, device_token: str, file_path: Path, trap_id: str, captured_at: str, note: str | None) -> None:
    headers = {"x-device-token": device_token}
    upload_url_resp = requests.post(
        f"{api_url}/upload-url",
        headers=headers,
        json={
            "trap_id": trap_id,
            "captured_at": captured_at,
            "filename": file_path.name,
        },
        timeout=30,
    )
    upload_url_resp.raise_for_status()
    upload_info = upload_url_resp.json()

    with file_path.open("rb") as video:
        put_resp = requests.put(
            upload_info["upload_url"],
            data=video,
            headers={"content-type": "video/mp4"},
            timeout=300,
        )
    put_resp.raise_for_status()

    metadata_resp = requests.post(
        f"{api_url}/videos",
        headers=headers,
        json={
            "trap_id": trap_id,
            "captured_at": captured_at,
            "r2_key": upload_info["r2_key"],
            "hunter_note": note,
        },
        timeout=30,
    )
    metadata_resp.raise_for_status()


if __name__ == "__main__":
    raise SystemExit(main())
