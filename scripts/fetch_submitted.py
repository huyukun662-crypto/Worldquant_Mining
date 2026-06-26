"""Fetch all SUBMITTED alphas from the user's WQ Brain pool and dump to JSON."""
from __future__ import annotations
import json, time
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth

REPO = Path(__file__).resolve().parent.parent
CRED = json.loads((REPO / "credential.txt").read_text())


def session():
    s = requests.Session()
    s.auth = HTTPBasicAuth(CRED[0], CRED[1])
    r = s.post("https://api.worldquantbrain.com/authentication", timeout=20)
    assert r.status_code == 201, (r.status_code, r.text[:300])
    print("authenticated user", r.json().get("user", {}).get("id"))
    return s


def fetch_all(s, params):
    base = "https://api.worldquantbrain.com/users/self/alphas"
    out = []
    offset = 0
    count = None
    while True:
        url = f"{base}?limit=100&offset={offset}&{params}"
        r = s.get(url, timeout=40)
        if r.status_code == 429:
            time.sleep(10); continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {params}: {r.text[:200]}")
            break
        data = r.json()
        count = data.get("count")
        res = data.get("results", [])
        out.extend(res)
        offset += len(res)
        if not res or offset >= (count or 0):
            break
        time.sleep(0.3)
    print(f"  params[{params}] count={count} fetched={len(out)}")
    return out


def main():
    s = session()
    all_alphas = []
    # submitted pool: stage=IS with status filters; also pull OS stage
    for params in ["stage=IS", "stage=OS", "status=ACTIVE", "status=UNSUBMITTED"]:
        all_alphas.extend(fetch_all(s, params))
    by_id = {a["id"]: a for a in all_alphas if a.get("id")}
    out = list(by_id.values())
    print("total unique:", len(out))
    (REPO / "scratch_all_alphas.json").write_text(json.dumps(out, indent=2))
    # quick schema peek
    if out:
        print("sample keys:", sorted(out[0].keys()))


if __name__ == "__main__":
    main()
