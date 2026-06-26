"""Exhaustively fetch ALL alphas; identify every submitted one by dateSubmitted."""
from __future__ import annotations
import json, time
from pathlib import Path
from collections import Counter
import requests
from requests.auth import HTTPBasicAuth

REPO = Path(__file__).resolve().parent.parent
CRED = json.loads((REPO / "credential.txt").read_text())


def session():
    s = requests.Session()
    s.auth = HTTPBasicAuth(CRED[0], CRED[1])
    for attempt in range(6):
        r = s.post("https://api.worldquantbrain.com/authentication", timeout=20)
        if r.status_code == 201:
            print("auth user", r.json().get("user", {}).get("id"))
            return s
        print(f"auth {r.status_code} (attempt {attempt}); waiting 20s: {r.text[:120]}")
        time.sleep(20)
    raise SystemExit("auth failed after retries")


def fetch_all(s, params=""):
    base = "https://api.worldquantbrain.com/users/self/alphas"
    out, offset, count = [], 0, None
    while True:
        sep = "&" if params else ""
        url = f"{base}?limit=100&offset={offset}{sep}{params}"
        r = s.get(url, timeout=40)
        if r.status_code == 429:
            time.sleep(10); continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} [{params}]: {r.text[:200]}"); break
        data = r.json()
        count = data.get("count")
        res = data.get("results", [])
        out.extend(res)
        offset += len(res)
        if not res or offset >= (count or 0):
            break
        time.sleep(0.25)
    print(f"  [{params or 'NO FILTER'}] api_count={count} fetched={len(out)}")
    return out, count


def main():
    s = session()
    # 1) the authoritative full sweep: no status filter at all
    alla, total = fetch_all(s, "")
    by_id = {a["id"]: a for a in alla if a.get("id")}
    # 2) belt-and-suspenders: explicit status filters that NO-filter might page-cap
    for st in ["ACTIVE", "DECOMMISSIONED", "IS"]:
        extra, _ = fetch_all(s, f"status={st}")
        for a in extra:
            by_id.setdefault(a["id"], a)
    out = list(by_id.values())
    print("total unique:", len(out), "| api reported total:", total)
    print("status dist:", Counter(a.get("status") for a in out))
    print("stage dist:", Counter(a.get("stage") for a in out))
    submitted = [a for a in out if a.get("dateSubmitted")]
    print("=> dateSubmitted not null:", len(submitted))
    print("   submitted delay dist:",
          Counter((a.get("settings") or {}).get("delay") for a in submitted))
    print("   submitted status dist:", Counter(a.get("status") for a in submitted))
    (REPO / "scratch_all_alphas.json").write_text(json.dumps(out))
    (REPO / "scratch_submitted.json").write_text(json.dumps(submitted, indent=1))


if __name__ == "__main__":
    main()
