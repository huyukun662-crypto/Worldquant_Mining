"""Tune the user's third factor to pass submission.

Expression:
  -group_neutralize(
    signed_power(ts_zscore(ts_delay(news_mins_20_chg, 1), 60), 0.5),
    subindustry)

User's current settings (per screenshot):
  USA, TOP3000, delay=0, Industry neut, decay=0, truncation=0.08,
  pasteurization=ON, NaN handling=Off

Note this uses delay=0 which most prior factors didn't.

Optuna TPE search over the full setting space + a few variant
expressions (with/without negation, different signed_power exponent,
different ts_zscore window).
"""

from __future__ import annotations
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import optuna

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("user-tune-3")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
}

# Setting space includes BOTH delay=0 and delay=1 since the field
# may be available at both (user's form is delay=0).
SETTING_SPACE = {
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "delay":          [0, 1],
    "decay":          [0, 4, 8, 12, 20],
    "truncation":     [0.02, 0.05, 0.08, 0.10],
    "neutralization": ["NONE", "MARKET", "INDUSTRY", "SUBINDUSTRY", "SECTOR"],
    "pasteurization": ["ON", "OFF"],
}

# Variant expressions to try.  The original is variant E1.
EXPRESSIONS = {
    "E1_original":
        "-group_neutralize(signed_power(ts_zscore(ts_delay(news_mins_20_chg, 1), 60), 0.5), subindustry)",
    "E2_neg_only":
        "-signed_power(ts_zscore(ts_delay(news_mins_20_chg, 1), 60), 0.5)",
    "E3_positive":
        "group_neutralize(signed_power(ts_zscore(ts_delay(news_mins_20_chg, 1), 60), 0.5), subindustry)",
    "E4_exponent_1":
        "-group_neutralize(ts_zscore(ts_delay(news_mins_20_chg, 1), 60), subindustry)",
    "E5_industry_group":
        "-group_neutralize(signed_power(ts_zscore(ts_delay(news_mins_20_chg, 1), 60), 0.5), industry)",
    "E6_zwin_120":
        "-group_neutralize(signed_power(ts_zscore(ts_delay(news_mins_20_chg, 1), 120), 0.5), subindustry)",
    "E7_quantile":
        "-group_neutralize(signed_power(quantile(ts_delay(news_mins_20_chg, 1)) - 0.5, 3), subindustry)",
    "E8_rank":
        "-group_neutralize(rank(ts_delay(news_mins_20_chg, 1)) - 0.5, subindustry)",
}

POLL_TIMEOUT_S = 600
POLL_INTERVAL_S = 5


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


@dataclass
class TrialResult:
    ok: bool
    expr_label: str
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    self_corr: float | None = None
    alpha_id: str = ""
    error: str = ""
    checks: list = field(default_factory=list)


def submit(session, expr_label: str, expression: str, settings: dict) -> TrialResult:
    full = dict(FIXED_SETTINGS); full.update(settings)
    body = {"type": "REGULAR", "settings": full, "regular": expression}
    for attempt in range(6):
        r = session.post("https://api.worldquantbrain.com/simulations",
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After") or 30)
            log.info(f"   429 on POST; sleep {wait:.0f}s")
            time.sleep(wait); continue
        break
    if r.status_code != 201:
        return TrialResult(ok=False, expr_label=expr_label, expression=expression,
                            settings=full,
                            error=f"submit-{r.status_code}: {r.text[:300]}")
    progress_url = r.headers.get("Location")
    if not progress_url:
        return TrialResult(ok=False, expr_label=expr_label, expression=expression,
                            settings=full, error="no Location header")
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        data = rp.json()
        st = data.get("status", "")
        if st == "COMPLETE":
            alpha_id = data.get("alpha", "")
            ra = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                timeout=30)
            if ra.status_code != 200:
                return TrialResult(ok=False, expr_label=expr_label,
                                    expression=expression, settings=full,
                                    alpha_id=alpha_id,
                                    error=f"alpha-get-{ra.status_code}")
            isb = (ra.json().get("is") or {})
            checks = isb.get("checks") or []
            return TrialResult(
                ok=True, expr_label=expr_label, expression=expression,
                settings=full,
                sharpe=float(isb.get("sharpe") or 0.0),
                turnover=float(isb.get("turnover") or 0.0),
                fitness=float(isb.get("fitness") or 0.0),
                returns=float(isb.get("returns") or 0.0),
                drawdown=float(isb.get("drawdown") or 0.0),
                margin=float(isb.get("margin") or 0.0),
                longCount=int(isb.get("longCount") or 0),
                shortCount=int(isb.get("shortCount") or 0),
                checks_passed=sum(1 for c in checks if c.get("result")=="PASS"),
                checks_total=len(checks),
                checks=checks,
                alpha_id=alpha_id,
            )
        if st in ("ERROR", "FAILED", "WARNING"):
            return TrialResult(ok=False, expr_label=expr_label,
                                expression=expression, settings=full,
                                error=f"sim-{st}: {data.get('message','')[:300]}")
    return TrialResult(ok=False, expr_label=expr_label, expression=expression,
                        settings=full, error="poll-timeout")


def fetch_self_corr(session, alpha_id: str, timeout_s: int = 90):
    t0 = time.time()
    while True:
        try:
            r = session.get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self",
                timeout=30)
        except Exception as e:
            return None, f"ERROR:{e}"
        if r.status_code in (202, 204) or not r.text.strip():
            if time.time() - t0 > timeout_s: return None, "PENDING"
            time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code != 200:
            return None, f"ERROR:{r.status_code}"
        try:
            data = r.json()
        except Exception:
            if time.time() - t0 > timeout_s: return None, "PENDING"
            time.sleep(5); continue
        v = data.get("max")
        if isinstance(v, (int, float)):
            return float(v), "DONE"
        sprops = (data.get("schema") or {}).get("properties") or []
        col = {p["name"]: i for i, p in enumerate(sprops)
                if isinstance(p, dict) and "name" in p}
        recs = data.get("records") or []
        vals = []
        for row in recs:
            if isinstance(row, list) and "correlation" in col:
                c = row[col["correlation"]]
                if isinstance(c, (int, float)): vals.append(c)
        if vals:
            return float(max(abs(x) for x in vals)), "DONE"
        if time.time() - t0 > timeout_s: return None, "PENDING"
        time.sleep(5)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials-per-expr", type=int, default=8,
                     help="Optuna trials per expression variant")
    ap.add_argument("--seed", type=int, default=99)
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_USER_FACTOR_3_TUNE.json"
    all_trials: list[TrialResult] = []

    # First submit each variant with the user's default settings to
    # see which expression has the strongest baseline signal.
    user_default = {"universe": "TOP3000", "delay": 0, "decay": 0,
                     "truncation": 0.08, "neutralization": "INDUSTRY",
                     "pasteurization": "ON"}
    log.info("=== Phase A: baseline submission for each expression variant ===")
    for label, expr in EXPRESSIONS.items():
        log.info(f"--- baseline {label} -- expr: {expr}")
        res = submit(cm.session, label, expr, user_default)
        all_trials.append(res)
        if res.ok:
            log.info(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} chk={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        else:
            log.warning(f"    FAILED: {res.error[:160]}")
        with open(out_path, "w") as f:
            json.dump([asdict(t) for t in all_trials], f, indent=2)

    # Phase B: tune settings for the BEST baseline expression
    ok_baselines = [t for t in all_trials if t.ok]
    if not ok_baselines:
        log.error("no baseline OK; aborting Phase B")
        return 1
    ok_baselines.sort(key=lambda t: t.sharpe, reverse=True)
    best = ok_baselines[0]
    log.info(f"=== Phase B: tune settings for best baseline = "
              f"{best.expr_label} (SH={best.sharpe:+.3f}) ===")

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=args.seed),
    )
    expr = best.expression
    label = best.expr_label

    def objective(trial):
        settings = {k: trial.suggest_categorical(k, v)
                     for k, v in SETTING_SPACE.items()}
        log.info(f"   trial {trial.number+1}: settings={settings}")
        res = submit(cm.session, f"{label}_tune", expr, settings)
        all_trials.append(res)
        with open(out_path, "w") as f:
            json.dump([asdict(t) for t in all_trials], f, indent=2)
        if not res.ok:
            log.info(f"      [{res.error[:80]}]")
            return -10.0
        log.info(f"      SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                  f"FIT={res.fitness:+.3f} chk={res.checks_passed}/{res.checks_total} "
                  f"alpha={res.alpha_id}")
        penalty = 5.0 if res.turnover >= 0.25 else 0.0
        return res.sharpe - penalty

    study.optimize(objective, n_trials=args.trials_per_expr * 2,
                   show_progress_bar=False)

    # Pass 2: self-correlation
    log.info("=== pass 2: self-correlation ===")
    for r in all_trials:
        if not r.ok or not r.alpha_id: continue
        sc, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=60)
        r.self_corr = sc
        log.info(f"   {r.alpha_id} self_corr={sc} ({st})")
    with open(out_path, "w") as f:
        json.dump([asdict(t) for t in all_trials], f, indent=2)

    # Final report
    ok = [t for t in all_trials if t.ok]
    ok.sort(key=lambda t: t.sharpe, reverse=True)
    pass_bar = [t for t in ok if t.sharpe > 1.25 and t.turnover < 0.25
                 and t.fitness >= 1.0]
    print()
    print("=" * 130)
    print(f"### user_factor_3 ({len(ok)}/{len(all_trials)} OK, "
           f"{len(pass_bar)} pass SH>1.25 + TO<0.25 + FIT>=1.0)")
    print(f"{'#':<3}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7}  "
           f"{'expr':<14} {'univ':<8} {'d':>2} {'dcy':>3} {'trunc':>6} "
           f"{'neut':<12} {'pst':<4}  alpha_id")
    for j, t in enumerate(ok[:15], 1):
        s = t.settings
        sc = f"{t.self_corr:+.3f}" if t.self_corr is not None else "  -  "
        marker = "★" if (t in pass_bar) else " "
        print(f"{marker}{j:<2}{t.sharpe:7.3f}{t.turnover:7.3f}{t.fitness:7.3f}"
               f"{t.checks_passed:>3}/{t.checks_total:<2}{sc:>7}  "
               f"{t.expr_label[:14]:<14} {s.get('universe','?'):<8} "
               f"{s.get('delay','?'):>2} {s.get('decay','?'):>3} "
               f"{s.get('truncation','?'):>6} {s.get('neutralization','?'):<12} "
               f"{s.get('pasteurization','?'):<4}  {t.alpha_id}")
    print("=" * 130)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
