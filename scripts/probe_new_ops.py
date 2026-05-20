"""Quick accessibility probe for untried operators on this account tier."""
from __future__ import annotations
import importlib.util, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
sys.path.insert(0, str(REPO))
from mining_pipeline.wq_pipeline import submit as wq_submit  # noqa: E402

FIXED = {
    "instrumentType":"EQUITY","region":"USA","language":"FASTEXPR","unitHandling":"VERIFY",
    "nanHandling":"OFF","visualization":False,"maxTrade":"OFF","testPeriod":"P0Y0M",
    "delay":0,"pasteurization":"ON","universe":"TOP3000","decay":10,
    "truncation":0.08,"neutralization":"INDUSTRY",
}

PROBES = {
    "group_rank":      "group_rank(rank(-1 * ts_zscore(returns, 10)), subindustry)",
    "group_zscore":    "group_zscore(returns, industry)",
    "group_neutralize":"group_neutralize(rank(snt_value), industry)",
    "vector_neut":     "vector_neut(rank(snt_value), rank(implied_volatility_call_60 - implied_volatility_put_60))",
    "regression_neut": "regression_neut(rank(snt_value), rank(returns))",
    "ts_regression":   "ts_regression(returns, vwap, 20)",
    "ts_partial_corr": "ts_partial_corr(close, volume, vwap, 20)",
    "hump":            "hump(rank(snt_value), 0.01)",
    "ts_co_skewness":  "ts_co_skewness(returns, vwap, 60)",
}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    cm_mod = _load(VENDOR/"core"/"credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    print(f"auth ok: {cm.credentials.username}", flush=True)
    session = cm.session

    def run(item):
        name, expr = item
        res = wq_submit(session, expr, FIXED)
        if res.ok:
            return f"{name:18s} OK   SH={res.sharpe:+.2f} TO={res.turnover:.3f} chk={res.checks_passed}/{res.checks_total}"
        return f"{name:18s} FAIL [{(res.error or '')[:90]}]"

    with ThreadPoolExecutor(max_workers=3) as ex:
        for line in ex.map(run, PROBES.items()):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
