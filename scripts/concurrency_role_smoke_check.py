import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
IMAGE_PATH = Path(os.getenv("SMOKE_IMAGE", "Reciept_01.png"))
PASSWORD = os.getenv("SMOKE_PASSWORD", "password123")
TIMEOUT = float(os.getenv("SMOKE_TIMEOUT", "90"))

WORKERS = ["TIW-V48XE", "TIW-XX6E4", "TIW-FZ3CL", "TIW-2OIPF"]
ADMINS = ["TIW-3E08W", "TIW-BNZRL"]
HQ = "TIW-OQFOW"


def login(login_id: str):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": login_id, "password": PASSWORD},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return None, {"step": "login", "status": r.status_code, "body": r.text[:300]}
    token = r.json().get("access_token")
    return token, None


def worker_flow(login_id: str):
    result = {"actor": login_id, "role": "WORKER", "ok": False, "steps": []}

    token, err = login(login_id)
    if err:
        result["steps"].append(err)
        return result

    if not IMAGE_PATH.exists():
        result["steps"].append({"step": "analyze", "status": "error", "body": f"Image missing: {IMAGE_PATH}"})
        return result

    with IMAGE_PATH.open("rb") as f:
        files = {"file": (IMAGE_PATH.name, f, "image/png")}
        data = {"processing_mode": "sync", "engine": "standard"}
        analyze = requests.post(
            f"{BASE_URL}/api/mobile/analyze",
            files=files,
            data=data,
            timeout=TIMEOUT,
        )

    result["steps"].append({"step": "analyze", "status": analyze.status_code})
    if analyze.status_code != 200:
        result["steps"].append({"step": "analyze_error", "body": analyze.text[:400]})
        return result

    payload = analyze.json()
    queue_id = payload.get("queue_id")
    fields = payload.get("fields", {})
    if not queue_id:
        result["steps"].append({"step": "analyze_error", "body": "missing queue_id"})
        return result

    submit_payload = {
        "queue_id": queue_id,
        "fields": fields,
        "user": {
            "full_name": login_id,
            "email": f"{login_id.lower()}@example.com",
            "employee_id": login_id,
        },
    }
    submit = requests.post(
        f"{BASE_URL}/api/mobile/submit",
        json=submit_payload,
        timeout=TIMEOUT,
    )
    result["steps"].append({"step": "submit", "status": submit.status_code})
    if submit.status_code != 200:
        result["steps"].append({"step": "submit_error", "body": submit.text[:400]})
        return result

    result["ok"] = True
    return result


def admin_filter_flow(login_id: str):
    result = {"actor": login_id, "role": "ADMIN", "ok": False, "steps": []}
    token, err = login(login_id)
    if err:
        result["steps"].append(err)
        return result

    headers = {"Authorization": f"Bearer {token}"}
    r1 = requests.get(f"{BASE_URL}/api/drafts", params={"status_filter": "DRAFT", "limit": 20}, headers=headers, timeout=TIMEOUT)
    r2 = requests.get(f"{BASE_URL}/api/drafts", params={"status_filter": "SENT", "limit": 20}, headers=headers, timeout=TIMEOUT)

    result["steps"].append({"step": "draft_filter_draft", "status": r1.status_code})
    result["steps"].append({"step": "draft_filter_sent", "status": r2.status_code})

    if r1.status_code == 200 and r2.status_code == 200:
        result["ok"] = True
    else:
        result["steps"].append({"step": "admin_error", "body": f"DRAFT={r1.text[:250]} SENT={r2.text[:250]}"})
    return result


def hq_filter_flow(login_id: str):
    result = {"actor": login_id, "role": "HQ", "ok": False, "steps": []}
    token, err = login(login_id)
    if err:
        result["steps"].append(err)
        return result

    headers = {"Authorization": f"Bearer {token}"}
    offices = requests.get(f"{BASE_URL}/api/hq-view/offices", headers=headers, timeout=TIMEOUT)
    months = requests.get(f"{BASE_URL}/api/hq-view/months", headers=headers, timeout=TIMEOUT)

    result["steps"].append({"step": "offices", "status": offices.status_code})
    result["steps"].append({"step": "months", "status": months.status_code})

    if offices.status_code != 200 or months.status_code != 200:
        result["steps"].append({"step": "hq_error", "body": f"offices={offices.text[:250]} months={months.text[:250]}"})
        return result

    office_list = offices.json() if offices.text else []
    month_list = months.json() if months.text else []

    params = {}
    if office_list:
        params["office"] = office_list[0]
    if month_list:
        params["month"] = month_list[0]

    batches = requests.get(f"{BASE_URL}/api/hq-view/batches", headers=headers, params=params, timeout=TIMEOUT)
    result["steps"].append({"step": "batches", "status": batches.status_code, "params": params})

    if batches.status_code == 200:
        result["ok"] = True
    else:
        result["steps"].append({"step": "batches_error", "body": batches.text[:300]})
    return result


def main():
    started = time.time()

    health = requests.get(f"{BASE_URL}/health", timeout=15)
    if health.status_code != 200:
        print(json.dumps({"fatal": "server_not_healthy", "status": health.status_code, "body": health.text[:300]}, indent=2))
        raise SystemExit(1)

    tasks = []
    for w in WORKERS:
        tasks.append(("worker", w))
    for a in ADMINS:
        tasks.append(("admin", a))
    tasks.append(("hq", HQ))

    results = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        future_map = {}
        for typ, login_id in tasks:
            if typ == "worker":
                fut = ex.submit(worker_flow, login_id)
            elif typ == "admin":
                fut = ex.submit(admin_filter_flow, login_id)
            else:
                fut = ex.submit(hq_filter_flow, login_id)
            future_map[fut] = (typ, login_id)

        for fut in as_completed(future_map):
            typ, login_id = future_map[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append({"actor": login_id, "role": typ.upper(), "ok": False, "steps": [{"step": "exception", "body": str(exc)}]})

    elapsed = round(time.time() - started, 2)
    ok_count = sum(1 for r in results if r.get("ok"))

    output = {
        "base_url": BASE_URL,
        "image": str(IMAGE_PATH),
        "elapsed_sec": elapsed,
        "total_flows": len(tasks),
        "ok_flows": ok_count,
        "failed_flows": len(tasks) - ok_count,
        "all_ok": ok_count == len(tasks),
        "results": sorted(results, key=lambda r: (r.get("role", ""), r.get("actor", ""))),
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
