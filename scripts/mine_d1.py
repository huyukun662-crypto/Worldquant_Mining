"""Mine fresh submittable D1 factors using the proven structure:
  trade_when(<sentiment/regime gate>, <directional signal>, -1)  +  0.3 * <quality>

The pcr_oi-gated IV-regression + gross-profit dilution hit SH 2.28/FIT 1.39.
Generalize: vary the gate (pcr/news/volume regime), the directional signal
(IV-skew, IV-change, vwap-reversal, price-reversal, residual), and the
quality diluter (gross-profit, capex, value). delay=1, MARKET neut.
Target: SH>1.25, FIT>1.0, no FAIL, sc<0.7.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# ---- directional signal cores (the "what to trade") ----
IV_REG   = "rank(-1 * ts_regression(close, ts_backfill(call_breakeven_20, 30), 10, rettype = 0))"
IV_SKEW  = "rank(-1 * ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5))"
IV_CHG   = "rank(ts_delta(implied_volatility_call_60, 20) > 0)"
VWAP_REV = "rank(-1 * divide(close - vwap, vwap))"
PRICE_REV= "rank(-1 * ts_sum(returns, 5))"
ZREV     = "rank(-1 * ts_zscore(close, 20))"

# ---- regime gates (the "when to trade") ----
G_PCR    = "pcr_oi_20 < 1"                                  # bullish option positioning
G_PCRVOL = "pcr_vol_20 < 1"                                 # bullish option volume
G_HIVOL  = "ts_rank(volume, 20) > 0.7"                      # high-volume days
G_NEWS   = "ts_rank(abs(returns), 60) > 0.7"               # high-vol regime

# ---- quality diluters (the "drawdown/turnover damper") ----
GP   = "group_rank(divide(ts_backfill(sales,250), ts_backfill(assets,250)), market)"
CAPEX= "-group_rank(divide(ts_backfill(capex,250), ts_backfill(assets,250)), market)"
VAL  = "group_rank(divide(ts_backfill(bookvalue_ps,250), close), market)"

def gated(gate, sig): return f"trade_when({gate}, {sig}, -1)"
def blend(core, q, w=0.3): return f"{1-w:g} * ({core}) + {w:g} * ({q})"

def S(dec=2, tr=0.05, nt="MARKET"):
    return {"decay": dec, "truncation": tr, "neutralization": nt}

C = [
    # ===== IV-skew gated + quality (mirror the winner with IV skew) =====
    ("d1_iv_skew_pcr_gp",    blend(gated(G_PCR, IV_SKEW), GP),       S(2, 0.05, "MARKET")),
    ("d1_iv_skew_pcrvol_gp", blend(gated(G_PCRVOL, IV_SKEW), GP),    S(2, 0.05, "MARKET")),
    # ===== IV-change gated + quality =====
    ("d1_iv_chg_pcr_gp",     blend(gated(G_PCR, IV_CHG), GP),        S(2, 0.05, "MARKET")),
    # ===== vwap reversal gated + quality =====
    ("d1_vwap_pcr_gp",       blend(gated(G_PCR, VWAP_REV), GP),      S(2, 0.05, "MARKET")),
    ("d1_vwap_hivol_gp",     blend(gated(G_HIVOL, VWAP_REV), GP),    S(2, 0.05, "MARKET")),
    # ===== price reversal gated + quality =====
    ("d1_prev_pcr_gp",       blend(gated(G_PCR, PRICE_REV), GP),     S(2, 0.05, "MARKET")),
    ("d1_prev_news_gp",      blend(gated(G_NEWS, PRICE_REV), GP),    S(2, 0.05, "MARKET")),
    # ===== z-reversal gated + quality =====
    ("d1_zrev_pcr_gp",       blend(gated(G_PCR, ZREV), GP),          S(2, 0.05, "MARKET")),
    # ===== winner with different diluters =====
    ("d1_ivreg_pcr_capex",   blend(gated(G_PCR, IV_REG), CAPEX),     S(2, 0.05, "MARKET")),
    ("d1_ivreg_pcr_val",     blend(gated(G_PCR, IV_REG), VAL),       S(2, 0.05, "MARKET")),
    # ===== winner with heavier quality (lift FIT further) =====
    ("d1_ivreg_pcr_gp40",    blend(gated(G_PCR, IV_REG), GP, 0.4),   S(2, 0.05, "MARKET")),
    ("d1_ivreg_pcr_gp_val",  f"0.6 * ({gated(G_PCR, IV_REG)}) + 0.2 * ({GP}) + 0.2 * ({VAL})", S(2, 0.05, "MARKET")),
    # ===== IV-skew + IV-reg combo gated =====
    ("d1_iv_combo_pcr_gp",   f"0.5 * ({gated(G_PCR, IV_REG)}) + 0.2 * ({gated(G_PCR, IV_SKEW)}) + 0.3 * ({GP})", S(2, 0.05, "MARKET")),
    # ===== pure IV-skew gated, no dilution (baseline) =====
    ("d1_iv_skew_pcr_only",  gated(G_PCR, IV_SKEW),                  S(2, 0.05, "MARKET")),
]

def wname(r):
    return [c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"]

def robust(sess, fam, expr, s):
    r=None
    for attempt in range(5):
        try:
            r=submit(sess, fam, expr, s)
            if not r.ok and r.error:
                err=str(r.error)
                # retry on concurrent-limit, 429, or 5xx gateway errors
                if "CONCURRENT" in err or "429" in err or "504" in err or "503" in err or "502" in err or "500" in err:
                    log.info(f"   transient err ({err[:40]}), wait 60s ({attempt+1}/5)"); time.sleep(60); continue
            return r
        except Exception as e:
            log.warning(f"   net {attempt+1}/5 {str(e)[:55]}"); time.sleep(25)
    return r

def main():
    cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  D1 MINING (gated + quality structure)")
    out=REPO/"WQ_D1_MINE.json"; res=[]
    for i,(fam,expr,st) in enumerate(C, 1):
        s=dict(st); s["delay"]=1; s.setdefault("universe","TOP3000")
        log.info(f"=== d1 [{i}/{len(C)}] {fam} ===")
        log.info(f"   expr: {expr[:170]}")
        r=robust(cm.session, fam, expr, s)
        if r is None: continue
        if r.ok:
            try: sc,_,_=fetch_self_corr(cm.session, r.alpha_id, timeout_s=60); r.self_corr=sc
            except Exception: r.self_corr=None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else:
            log.warning(f"   FAILED: {str(r.error)[:130]}")
        res.append(r); json.dump([asdict(x) for x in res], open(out,"w"), indent=2)

    def ok_(r):
        return (r.ok and not wname(r)
                and (r.self_corr is None or abs(r.self_corr)<0.7)
                and r.sharpe>1.25 and r.fitness>=1.0)
    oks=sorted([r for r in res if r.ok], key=lambda r: r.fitness, reverse=True)
    print("\n"+"="*110)
    print(f"D1 MINE: submittable={sum(1 for r in oks if ok_(r))}/{len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else " - "
        tag="*** SUBMIT ***" if ok_(r) else ""
        print(f"  {r.family:<24} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {tag} {r.alpha_id}")
    for r in [r for r in res if not r.ok]:
        print(f"  FAIL {r.family}: {str(r.error)[:90]}")
    print("="*110)
    log.info(f"wrote {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
