"""Batch D0 simulation runner. Reads candidate list, submits each to WQ
Brain with delay=0, polls, and writes results to D0_RESULTS.json.

Each candidate: (label, expression, universe, neutralization, decay, trunc).
"""
from __future__ import annotations
import importlib.util, json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import d0_mine  # noqa: E402

OUT = REPO / "D0_RESULTS.json"


def run(candidates):
    sess = d0_mine._session()
    results = []
    for i, c in enumerate(candidates, 1):
        label, expr, uni, neut, decay, trunc = c
        print(f"\n=== [{i}/{len(candidates)}] {label}", flush=True)
        print(f"    {expr}", flush=True)
        print(f"    uni={uni} neut={neut} decay={decay} trunc={trunc}", flush=True)
        res = d0_mine.simulate(sess, expr,
                               d0_mine.settings_d0(uni, neut, decay, trunc))
        s = d0_mine.summarize(res)
        s["label"] = label
        s["setting"] = {"universe": uni, "neut": neut, "decay": decay,
                        "trunc": trunc, "delay": 0}
        if res.get("ok"):
            fails = [c["name"] for c in s["checks"]
                     if c["result"] == "FAIL"]
            print(f"    SH={s['sharpe']} TO={s['turnover']} FIT={s['fitness']} "
                  f"FAILS={fails}", flush=True)
        else:
            msg = res.get('message') or res.get('body', '')
            print(f"    NOT OK: {res.get('stage')} {msg[:120]}", flush=True)
            s = {"label": label, "expression": expr, "sharpe": None,
                 "setting": {"universe": uni, "neut": neut, "decay": decay,
                             "trunc": trunc, "delay": 0},
                 "error": {"stage": res.get("stage"), "status": res.get("status"),
                           "message": msg[:300]}}
        results.append(s)
        with open(OUT, "w") as f:
            json.dump(results, f, indent=2)
    # rank
    ok = [r for r in results if r.get("sharpe") is not None]
    ok.sort(key=lambda r: (r.get("sharpe") or -9), reverse=True)
    print("\n" + "=" * 90)
    print(f"{'SH':>6}{'TO':>7}{'FIT':>6}  label / expr")
    for r in ok:
        print(f"{(r.get('sharpe') or 0):6.2f}{(r.get('turnover') or 0):7.3f}"
              f"{(r.get('fitness') or 0):6.2f}  {r['label']}: {r['expression'][:70]}")
    return results


if __name__ == "__main__":
    cands = json.load(open(sys.argv[1]))
    run([tuple(c) for c in cands])
