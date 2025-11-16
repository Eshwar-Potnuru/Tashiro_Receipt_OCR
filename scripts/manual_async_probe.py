"""Utility script to exercise the async receipt pipeline via HTTP."""

import argparse
import json
import pathlib
import time

import requests


def upload_receipt(base_url: str, receipt_path: pathlib.Path, processing_mode: str) -> dict:
    with receipt_path.open("rb") as handle:
        files = {"file": (receipt_path.name, handle, "image/jpeg")}
        data = {"processing_mode": processing_mode}
        response = requests.post(f"{base_url}/api/mobile/analyze", files=files, data=data, timeout=60)
        response.raise_for_status()
        return response.json()


def poll_status(base_url: str, queue_id: str, timeout: int = 120, interval: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status_response = requests.get(f"{base_url}/api/mobile/analyze/status/{queue_id}", timeout=30)
        status_response.raise_for_status()
        payload = status_response.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(interval)
    raise TimeoutError(f"Polling timed out for queue_id={queue_id}")


def main():
    parser = argparse.ArgumentParser(description="Quick manual receipt upload and polling harness")
    parser.add_argument("receipt", type=pathlib.Path, help="Path to receipt image to upload")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the FastAPI server")
    parser.add_argument("--mode", default="async", choices=["async", "sync"], help="Processing mode to request")
    args = parser.parse_args()

    analysis = upload_receipt(args.base_url, args.receipt, args.mode)
    print("Initial response:")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    if analysis.get("status") == "queued":
        queue_id = analysis["queue_id"]
        final_payload = poll_status(args.base_url, queue_id)
        print("Final status:")
        print(json.dumps(final_payload, indent=2, ensure_ascii=False))
    else:
        print("Processing completed synchronously.")


if __name__ == "__main__":
    main()
