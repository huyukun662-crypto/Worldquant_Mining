"""Driver: submit a list of (tag, expr, settings-override) D0 jobs to WQ Brain,
print a ranked table, save JSON. Settings default to D0 TOP3000 SUBINDUSTRY.

Usage: python scripts/mine_d0.py jobs.json out.json [max_workers]
  jobs.json: [{"tag":..., "expr":..., "settings":{...overrides...}}, ...]
"""
import sys, json, time
sys.path.insert(0, "/home/user/Worldquant_Mining/scripts")
import wq_lib

def run(jobs_spec, out_path, max_workers=3):
    s = wq_lib.auth()
    jobs = [(j["expr"], {**wq_lib.D0_DEFAULT, **j.get("settings", {})}) for j in jobs_spec]
    tags = {j["expr"]: j["tag"] for j in jobs_spec}
    t0 = time.time()
    res = wq_lib.simulate_many(s, jobs, max_workers=max_workers)
    bym = {}
    for r in res:  # last write wins is fine; exprs unique per batch ideally
        bym[r["expr"]] = r
    rows = []
    for j in jobs_spec:
        r = bym.get(j["expr"], {})
        row = {"tag": j["tag"], "expr": j["expr"], "settings": j.get("settings", {})}
        if r.get("ok"):
            row.update({k: r.get(k) for k in ("alpha_id","sharpe","turnover","fitness","returns","drawdown")})
        else:
            row["error"] = r.get("error")
        rows.append(row)
    rows_ok = [r for r in rows if "sharpe" in r and r["sharpe"] is not None]
    rows_ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print(f"\n{'tag':<24}{'SH':>7}{'TO':>7}{'FIT':>7}{'RET':>8}  alpha_id   expr")
    for r in rows_ok:
        print(f"{r['tag']:<24}{r['sharpe']:>7.2f}{r['turnover']:>7.3f}{r['fitness']:>7.2f}{r['returns']:>8.3f}  {r['alpha_id']:<10} {r['expr'][:60]}")
    for r in rows:
        if "error" in r:
            print(f"{r['tag']:<24}{'ERR':>7}  {r['error'][:70]} | {r['expr'][:50]}")
    json.dump(rows, open(out_path, "w"), indent=1)
    print(f"\nwrote {out_path}  elapsed {time.time()-t0:.0f}s")
    return rows

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else "_mine_out.json"
    mw = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    run(spec, out, mw)
