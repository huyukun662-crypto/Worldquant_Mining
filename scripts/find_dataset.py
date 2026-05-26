"""Find a dataset by keyword and dump its fields, via authenticated WQ API.
limit<=50, paginated, 429 backoff. Checks delay 0 and 1.
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.wq_lib import auth, BASE


def get(session, url, params, tries=8):
    for i in range(tries):
        r = session.get(url, params=params, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 10)
            print(f"   429; sleep {wait:.0f}s"); time.sleep(wait); continue
        return r
    return r


def list_datasets(session, delay, universe="TOP3000"):
    out = []
    offset = 0
    while True:
        r = get(session, f"{BASE}/data-sets",
                {"region": "USA", "delay": delay, "universe": universe,
                 "limit": 50, "offset": offset})
        if r.status_code != 200:
            print(f"data-sets delay={delay} off={offset} -> {r.status_code} {r.text[:160]}")
            break
        js = r.json()
        res = js.get("results", [])
        out.extend(res)
        cnt = js.get("count", 0)
        offset += 50
        if offset >= cnt or not res:
            break
        time.sleep(0.5)
    return out


def list_fields(session, dataset_id, delay, universe="TOP3000"):
    out = []
    offset = 0
    while True:
        r = get(session, f"{BASE}/data-fields",
                {"region": "USA", "delay": delay, "universe": universe,
                 "dataset.id": dataset_id, "limit": 50, "offset": offset})
        if r.status_code != 200:
            print(f"data-fields {dataset_id} -> {r.status_code} {r.text[:160]}")
            break
        js = r.json()
        res = js.get("results", [])
        out.extend(res)
        cnt = js.get("count", 0)
        offset += 50
        if offset >= cnt or not res:
            break
        time.sleep(0.5)
    return out


if __name__ == "__main__":
    kw = (sys.argv[1] if len(sys.argv) > 1 else "growth").lower()
    s = auth()
    found = {}
    for delay in (0, 1):
        ds = list_datasets(s, delay)
        hits = [d for d in ds
                if kw in (str(d.get("name", "")) + str(d.get("id", "")) +
                          str((d.get("category") or {}).get("name", ""))).lower()]
        print(f"=== delay={delay}: {len(ds)} datasets; '{kw}' hits={len(hits)} ===")
        for d in hits:
            print(f"  id={d.get('id'):<22} fields={d.get('fieldCount')} "
                  f"users={d.get('userCount')} alphas={d.get('alphaCount')} "
                  f":: {d.get('name')}")
            found[(d.get('id'), delay)] = d
    # dump fields for each hit
    allfields = {}
    for (did, delay), d in found.items():
        fs = list_fields(s, did, delay)
        allfields[f"{did}@d{delay}"] = fs
        print(f"\n--- {did} @ delay={delay}: {len(fs)} fields ---")
        for f in fs:
            print(f"  u={f.get('userCount'):>4} a={f.get('alphaCount'):>5} "
                  f"cov={f.get('coverage')} type={f.get('type'):<7} "
                  f"{f.get('id'):<30} :: {str(f.get('description'))[:50]}")
    json.dump(allfields, open(Path(__file__).resolve().parent.parent / f"dataset_{kw}.json", "w"), indent=2)
    print(f"\nwrote dataset_{kw}.json")
