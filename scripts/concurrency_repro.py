#!/usr/bin/env python3
"""Concurrency reproduction harness for OCR freeze diagnosis.

Usage example (PowerShell):
  $env:REPRO_USERS_JSON = '{"workers":[{"email":"w01_sam","password":"password123"},{"email":"w02_mark","password":"password123"},{"email":"w03_lucas","password":"password123"},{"email":"w04_ryo","password":"password123"}],"admins":[{"email":"a01_admin","password":"password123"}]}'
  .venv\Scripts\python.exe scripts\concurrency_repro.py --base-url http://127.0.0.1:8001 --workers 4 --admins 1 --receipts-per-worker 2 --duration-seconds 50

Credentials are loaded from REPRO_USERS_JSON (required). No credentials are hardcoded.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import requests


@dataclass
class UserCred:
    email: str
    password: str


@dataclass
class ApiResult:
    actor: str
    endpoint: str
    status_code: int
    elapsed_ms: float
    ok: bool
    error: str = ""


def _load_users(worker_count: int, admin_count: int) -> Tuple[List[UserCred], List[UserCred]]:
    raw = os.getenv("REPRO_USERS_JSON", "").strip()
    if not raw:
        raise ValueError("REPRO_USERS_JSON is required and must contain workers/admins credentials")

    data = json.loads(raw)
    workers = [UserCred(**item) for item in data.get("workers", [])]
    admins = [UserCred(**item) for item in data.get("admins", [])]

    if len(workers) < worker_count:
        raise ValueError(f"Need at least {worker_count} worker credentials in REPRO_USERS_JSON")
    if len(admins) < admin_count:
        raise ValueError(f"Need at least {admin_count} admin credentials in REPRO_USERS_JSON")

    return workers[:worker_count], admins[:admin_count]


def _login(base_url: str, cred: UserCred) -> str:
    response = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": cred.email, "password": cred.password},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Login failed for {cred.email}: {response.status_code} {response.text[:200]}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"No access token returned for {cred.email}")
    return token


def _pick_receipts(pattern: str, count: int) -> List[Path]:
    files = [Path(p) for p in glob.glob(pattern)]
    files = [p for p in files if p.is_file()]
    if len(files) < count:
        raise ValueError(f"Need at least {count} files for pattern '{pattern}', found {len(files)}")
    random.shuffle(files)
    return files[:count]


def _call_get(actor: str, url: str, headers: Dict[str, str], endpoint: str) -> ApiResult:
    started = time.perf_counter()
    try:
        response = requests.get(url, headers=headers, timeout=30)
        elapsed = (time.perf_counter() - started) * 1000
        return ApiResult(actor=actor, endpoint=endpoint, status_code=response.status_code, elapsed_ms=elapsed, ok=response.ok, error="" if response.ok else response.text[:200])
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return ApiResult(actor=actor, endpoint=endpoint, status_code=0, elapsed_ms=elapsed, ok=False, error=str(exc))


def _worker_upload(actor: str, base_url: str, token: str, files: List[Path], stagger_sec: float) -> ApiResult:
    if stagger_sec > 0:
        time.sleep(stagger_sec)

    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {token}"}
    multipart = []
    opened = []
    try:
        for p in files:
            fh = p.open("rb")
            opened.append(fh)
            multipart.append(("files", (p.name, fh, "application/octet-stream")))

        data = {"ocr_engine": "auto"}
        response = requests.post(
            f"{base_url}/api/drafts/batch-upload",
            headers=headers,
            files=multipart,
            data=data,
            timeout=180,
        )
        elapsed = (time.perf_counter() - started) * 1000
        return ApiResult(actor=actor, endpoint="POST /api/drafts/batch-upload", status_code=response.status_code, elapsed_ms=elapsed, ok=response.ok, error="" if response.ok else response.text[:240])
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return ApiResult(actor=actor, endpoint="POST /api/drafts/batch-upload", status_code=0, elapsed_ms=elapsed, ok=False, error=str(exc))
    finally:
        for fh in opened:
            try:
                fh.close()
            except Exception:
                pass


def _admin_poll_loop(actor: str, base_url: str, token: str, stop_event: threading.Event, interval_sec: float, output: List[ApiResult], lock: threading.Lock) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    endpoints = [
        ("GET /api/drafts", f"{base_url}/api/drafts"),
        ("GET /api/drafts/sent-records/all", f"{base_url}/api/drafts/sent-records/all"),
    ]

    while not stop_event.is_set():
        for name, url in endpoints:
            result = _call_get(actor, url, headers, name)
            with lock:
                output.append(result)
        time.sleep(interval_sec)


def _summarize(results: List[ApiResult]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    grouped: Dict[str, List[ApiResult]] = {}
    for item in results:
        grouped.setdefault(item.endpoint, []).append(item)

    for endpoint, items in grouped.items():
        latencies = [x.elapsed_ms for x in items]
        ok_count = sum(1 for x in items if x.ok)
        summary[endpoint] = {
            "count": len(items),
            "ok": ok_count,
            "errors": len(items) - ok_count,
            "avg_ms": round(statistics.mean(latencies), 2),
            "p95_ms": round(sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)], 2),
            "max_ms": round(max(latencies), 2),
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce OCR concurrency freeze and collect timings")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--admins", type=int, default=1)
    parser.add_argument("--receipts-per-worker", type=int, default=2)
    parser.add_argument("--receipt-glob", default="Sample reciepts/*")
    parser.add_argument("--stagger-seconds", type=float, default=1.5)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--output", default="artifacts/concurrency_repro_results.json")
    args = parser.parse_args()

    workers, admins = _load_users(args.workers, args.admins)

    print(f"[1/5] Logging in {len(workers)} workers + {len(admins)} admins...")
    worker_tokens = [_login(args.base_url, cred) for cred in workers]
    admin_tokens = [_login(args.base_url, cred) for cred in admins]

    print("[2/5] Selecting receipt files...")
    worker_file_sets: List[List[Path]] = []
    for _ in range(args.workers):
        worker_file_sets.append(_pick_receipts(args.receipt_glob, args.receipts_per_worker))

    all_results: List[ApiResult] = []
    result_lock = threading.Lock()
    stop_event = threading.Event()

    print("[3/5] Starting admin polling threads...")
    admin_threads = []
    for idx, token in enumerate(admin_tokens, start=1):
        actor = f"admin_{idx}"
        t = threading.Thread(
            target=_admin_poll_loop,
            args=(actor, args.base_url, token, stop_event, args.poll_interval, all_results, result_lock),
            daemon=True,
        )
        t.start()
        admin_threads.append(t)

    print("[4/5] Starting worker batch OCR uploads in parallel...")
    started_wall = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for idx, token in enumerate(worker_tokens, start=1):
            actor = f"worker_{idx}"
            stagger = (idx - 1) * args.stagger_seconds
            futures.append(
                pool.submit(
                    _worker_upload,
                    actor,
                    args.base_url,
                    token,
                    worker_file_sets[idx - 1],
                    stagger,
                )
            )

        for future in as_completed(futures):
            result = future.result()
            with result_lock:
                all_results.append(result)
            print(f"  {result.actor}: {result.status_code} in {result.elapsed_ms:.1f}ms ({result.endpoint})")

    # Continue polling during trailing window if requested
    trailing = max(0, args.duration_seconds - int(time.perf_counter() - started_wall))
    if trailing > 0:
        print(f"[5/5] Continuing admin polling for {trailing}s...")
        time.sleep(trailing)

    stop_event.set()
    for t in admin_threads:
        t.join(timeout=3)

    summary = _summarize(all_results)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": {
            "base_url": args.base_url,
            "workers": args.workers,
            "admins": args.admins,
            "receipts_per_worker": args.receipts_per_worker,
            "receipt_glob": args.receipt_glob,
            "stagger_seconds": args.stagger_seconds,
            "poll_interval": args.poll_interval,
            "duration_seconds": args.duration_seconds,
        },
        "summary": summary,
        "results": [r.__dict__ for r in all_results],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    for endpoint, stats in summary.items():
        print(
            f"{endpoint}: count={int(stats['count'])} ok={int(stats['ok'])} errors={int(stats['errors'])} "
            f"avg={stats['avg_ms']}ms p95={stats['p95_ms']}ms max={stats['max_ms']}ms"
        )

    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
