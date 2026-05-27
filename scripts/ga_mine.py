"""Genetic algorithm for delay=0 NON-IV alpha mining on WorldQuant Brain.

Genome = list of 2..4 "leaf" terms (each a unit-safe group_zscore of a
transformed d0 non-option field, with a +/- sign) summed together, plus
chromosome-level settings (neutralization, decay). Fitness = WQ IS Sharpe
minus penalties for failing the CONCENTRATED_WEIGHT / LOW_SUB_UNIVERSE_SHARPE
structural gates (we want a robust SH>=2 that clears the competition bar).

Run:  python scripts/ga_mine.py --pop 8 --gen 4 --seed 7
"""
from __future__ import annotations
import argparse, json, random, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.wq_lib import auth, simulate, is_metrics

CACHE = "constants/data_fields_cache_USA_0_TOP3000.json"
EXCLUDE_CAT = {"option"}              # NON-IV: drop the option/IV category
SCALERS = ["cap", "est_tot_assets", "assets_curr", "sales"]
DENSE_PV = ["close", "volume", "vwap", "returns", "adv20", "high", "low", "cap"]
BFs = [5, 20, 60, 120]
WINs = [10, 20, 60, 252]
NEUTS = ["MARKET", "INDUSTRY", "SUBINDUSTRY"]
DECAYS = [6, 10, 12]


def load_pool():
    d = json.load(open(CACHE))
    fields = {}
    def walk(o):
        if isinstance(o, dict):
            if "id" in o and isinstance(o["id"], str):
                cat = o.get("category", {}).get("id") if isinstance(o.get("category"), dict) else None
                fields[o["id"]] = {"type": o.get("type"), "cov": o.get("coverage"), "cat": cat}
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            [walk(x) for x in o]
    walk(d)
    pool = [f for f, m in fields.items()
            if m["type"] == "MATRIX" and (m["cov"] or 0) >= 0.5
            and (m["cat"] or "") not in EXCLUDE_CAT
            and f not in ("cap",)]
    scalers = [s for s in SCALERS if s in fields]
    return pool, scalers


def z(e):
    return f"group_zscore({e}, market)"


def rand_leaf(rng, pool, scalers):
    """Return a unit-safe, market-zscored leaf term (string)."""
    kind = rng.choices(["plain", "ratio", "corr", "delta", "decay"],
                       weights=[3, 3, 2, 2, 2])[0]
    if kind == "corr":
        w = rng.choice(WINs[:3])
        inner = f"ts_corr(close, volume, {w})"
        return z(inner), kind
    if kind == "ratio":
        num = rng.choice(pool)
        den = rng.choice(scalers)
        bf = rng.choice(BFs)
        return z(f"divide(ts_backfill({num}, {bf}), {den})"), kind
    f = rng.choice(pool)
    bf = rng.choice(BFs)
    base = f"ts_backfill({f}, {bf})"
    if kind == "delta":
        return z(f"ts_delta({base}, {rng.choice(WINs)})"), kind
    if kind == "decay":
        return z(f"ts_decay_linear({base}, {rng.choice(WINs[:3])})"), kind
    return z(base), kind  # plain


def rand_genome(rng, pool, scalers):
    n = rng.choice([2, 3, 4])
    terms = []
    for _ in range(n):
        leaf, kind = rand_leaf(rng, pool, scalers)
        sign = rng.choice([1, -1])
        terms.append({"leaf": leaf, "sign": sign, "kind": kind})
    return {"terms": terms,
            "neut": rng.choice(NEUTS),
            "decay": rng.choice(DECAYS)}


def to_expr(g):
    parts = []
    for t in g["terms"]:
        parts.append(f"multiply({t['leaf']}, -1)" if t["sign"] < 0 else t["leaf"])
    acc = parts[0]
    for p in parts[1:]:
        acc = f"add({acc}, {p})"
    return z(acc)  # re-standardize the sum


def mutate(g, rng, pool, scalers):
    g = json.loads(json.dumps(g))
    r = rng.random()
    if r < 0.30:  # swap a term
        i = rng.randrange(len(g["terms"]))
        leaf, kind = rand_leaf(rng, pool, scalers)
        g["terms"][i] = {"leaf": leaf, "sign": rng.choice([1, -1]), "kind": kind}
    elif r < 0.50 and len(g["terms"]) < 4:  # add term
        leaf, kind = rand_leaf(rng, pool, scalers)
        g["terms"].append({"leaf": leaf, "sign": rng.choice([1, -1]), "kind": kind})
    elif r < 0.65 and len(g["terms"]) > 2:  # drop term
        g["terms"].pop(rng.randrange(len(g["terms"])))
    elif r < 0.80:  # flip a sign
        rng.choice(g["terms"])["sign"] *= -1
    elif r < 0.90:
        g["neut"] = rng.choice(NEUTS)
    else:
        g["decay"] = rng.choice(DECAYS)
    return g


def crossover(a, b, rng):
    ta, tb = a["terms"], b["terms"]
    ca = ta[:len(ta) // 2] + tb[len(tb) // 2:]
    ca = ca[:4] if len(ca) > 4 else (ca if len(ca) >= 2 else ca + [rng.choice(ta + tb)])
    parent = rng.choice([a, b])
    return {"terms": json.loads(json.dumps(ca)), "neut": parent["neut"], "decay": parent["decay"]}


def seeded(pool, scalers):
    """Seed with the known-best non-IV basket (SH 1.34) components."""
    V = z("ts_backfill(divide(est_ebitda, cap), 120)")
    C = z("divide(ts_backfill(cashflow_op, 120), cap)")
    P = z("ts_corr(close, volume, 20)")
    GP = z("divide(ts_backfill(fnd6_gp, 120), ts_backfill(est_tot_assets, 120))")
    return {"terms": [{"leaf": V, "sign": 1, "kind": "ratio"},
                      {"leaf": C, "sign": 1, "kind": "ratio"},
                      {"leaf": P, "sign": -1, "kind": "corr"},
                      {"leaf": GP, "sign": 1, "kind": "ratio"}],
            "neut": "MARKET", "decay": 12}


def fitness(metrics):
    sh = metrics.get("sharpe")
    if sh is None:
        return -9.0
    f = float(sh)
    ch = metrics.get("checks", {})
    if ch.get("CONCENTRATED_WEIGHT") == "FAIL":
        f -= 1.0
    if ch.get("LOW_SUB_UNIVERSE_SHARPE") == "FAIL":
        f -= 0.5
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pop", type=int, default=8)
    ap.add_argument("--gen", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    pool, scalers = load_pool()
    print(f"gene pool: {len(pool)} dense non-IV d0 fields, scalers={scalers}", flush=True)
    session = auth()
    cache = {}  # expr -> (fitness, metrics, alpha_id)

    def evaluate(g):
        expr = to_expr(g)
        key = (expr, g["neut"], g["decay"])
        if key in cache:
            return cache[key]
        settings = {"delay": 0, "decay": g["decay"], "universe": "TOP3000",
                    "neutralization": g["neut"], "truncation": 0.08}
        r = None
        for _try in range(3):
            try:
                r = simulate(session, expr, settings, verbose=False)
                break
            except Exception as e:  # transient network (ReadTimeout etc.) - retry, don't kill GA
                print(f"   sim exception (try {_try}): {type(e).__name__}", flush=True)
        if r is None:
            res = (-9.0, {"err": "net"}, None)
            cache[key] = res
            return res
        if not r.get("ok"):
            res = (-9.0, {"err": r.get("stage") or r.get("status")}, None)
        else:
            m = is_metrics(r.get("alpha"))
            res = (fitness(m), m, r.get("alpha_id"))
        cache[key] = res
        return res

    # initial population: seed + random
    pop = [seeded(pool, scalers)] + [rand_genome(rng, pool, scalers) for _ in range(args.pop - 1)]
    best = None
    for gen in range(args.gen):
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            scored = list(ex.map(lambda g: (g, *evaluate(g)), pop))
        scored.sort(key=lambda x: x[1], reverse=True)
        g0, f0, m0, aid0 = scored[0]
        if best is None or f0 > best[1]:
            best = (g0, f0, m0, aid0)
        print(f"\n=== GEN {gen} best fit={f0:.3f} SH={m0.get('sharpe')} "
              f"FIT={m0.get('fitness')} neut={g0['neut']} d={g0['decay']} id={aid0} ===", flush=True)
        for g, f, m, aid in scored[:4]:
            print(f"  fit={f:>6.3f} SH={str(m.get('sharpe')):>6} "
                  f"checks={ {k:v for k,v in (m.get('checks') or {}).items() if v=='FAIL'} } "
                  f"neut={g['neut']} d={g['decay']}", flush=True)
        # next generation: elitism(2) + offspring
        elites = [s[0] for s in scored[:2]]
        nxt = list(elites)
        survivors = [s[0] for s in scored[:max(3, args.pop // 2)]]
        while len(nxt) < args.pop:
            a, b = rng.sample(survivors, 2) if len(survivors) >= 2 else (survivors[0], survivors[0])
            child = crossover(a, b, rng)
            if rng.random() < 0.6:
                child = mutate(child, rng, pool, scalers)
            nxt.append(child)
        pop = nxt

    g, f, m, aid = best
    out = {"fitness": f, "sharpe": m.get("sharpe"), "fitness_metric": m.get("fitness"),
           "turnover": m.get("turnover"), "checks": m.get("checks"), "alpha_id": aid,
           "neut": g["neut"], "decay": g["decay"], "expression": to_expr(g)}
    Path("GA_BEST.json").write_text(json.dumps(out, indent=2))
    print("\n=== GA BEST ===", flush=True)
    print(json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
