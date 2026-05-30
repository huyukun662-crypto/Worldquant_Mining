"""D0 sentiment factors -- GENUINELY NEW signal source (news18 Ravenpack +
socialmedia12). Event-driven sentiment has documented short-horizon (D0)
predictive power where pv/fundamental cap out. Mirrors the IV-winner
structure: directional sentiment score + relevance/buzz gate.
NO option/IV fields. delay=0. Bar: WQ checks (no FAIL) -> submittable."""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# VECTOR fields aggregated to scalar via vec_avg/vec_sum; MATRIX used directly
SSC="vec_avg(nws18_ssc)"          # granular sentiment [-1,1]
SSE="vec_avg(nws18_sse)"          # continuous sentiment
QEP="vec_avg(nws18_qep)"          # equities polarity
BEE="vec_avg(nws18_bee)"          # earnings evaluation
NIP="vec_avg(nws18_nip)"          # narrative impact
QCM="vec_avg(nws18_qcm)"          # high-confidence sentiment
REL="vec_avg(nws18_relevance)"    # relevance 0-100 (for gating)
SCL="scl12_sentiment"             # social sentiment MATRIX
BUZZ="scl12_buzz"                 # social buzz MATRIX
SNT="snt_value"; SNTR="snt_buzz_ret"
def rk(x,g="subindustry"): return f"group_rank({x},{g})"
C=[
 # --- direct sentiment (momentum: positive sentiment -> up) ---
 ("s_1_ssc_mom",  f"{rk(f'ts_backfill({SSC},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("s_2_qep_mom",  f"{rk(f'ts_backfill({QEP},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("s_3_nip_mom",  f"{rk(f'ts_backfill({NIP},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- sentiment reversal (overreaction fades) ---
 ("s_4_ssc_rev",  f"-{rk(f'ts_backfill({SSC},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("s_5_scl_mom",  f"{rk(f'ts_backfill({SCL},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("s_6_scl_rev",  f"-{rk(f'ts_backfill({SCL},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- social sentiment change (delta) ---
 ("s_7_scl_delta",f"{rk(f'ts_delta(ts_backfill({SCL},20),5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("s_8_snt_rev",  f"-{rk(f'ts_backfill({SNT},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- earnings sentiment (bee) ---
 ("s_9_bee_mom",  f"{rk(f'ts_backfill({BEE},5)')}", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- GATED (IV-winner structure): sentiment score gated on high relevance/buzz ---
 ("s_10_ssc_relgate", f"score=quantile(ts_backfill({SSC},5));\ngate=(ts_backfill({REL},5)>50);\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), 0)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 ("s_11_scl_buzzgate", f"score=quantile(ts_backfill({SCL},5));\ngate=(ts_rank(ts_backfill({BUZZ},5),20)>0.80);\ntrade_when(gate, ts_decay_linear(signed_power(score-0.5,3),5), 0)", {"decay":4,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
 # --- sentiment + relevance weighting MARKET neut ---
 ("s_12_ssc_mkt", f"{rk(f'ts_backfill({SSC},5)','market')}", {"decay":6,"truncation":0.08,"neutralization":"MARKET"}),
]
def wname(r): return [c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"]
def main():
    cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  D0 SENTIMENT (news18 Ravenpack + socialmedia12)")
    out=REPO/"WQ_D0_SENTIMENT.json"; res=[]
    for i,(fam,expr,st) in enumerate(C,1):
        s=dict(st); s["delay"]=0; s.setdefault("universe","TOP3000")
        log.info(f"=== sent [{i}/{len(C)}] {fam} ===")
        r=None
        for attempt in range(3):
            try: r=submit(cm.session,fam,expr,s); break
            except Exception as e: log.warning(f"   net-err {attempt+1}/3: {str(e)[:60]}"); import time;time.sleep(20)
        if r is None: log.warning("   skipped (net)"); continue
        if r.ok:
            try: sc,_,_=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
            except Exception: r.self_corr=None
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} chk={r.checks_passed}/{r.checks_total} sc={r.self_corr} FAIL={wname(r)}")
        else: log.warning(f"   FAILED: {str(r.error)[:120]}")
        res.append(r)
        json.dump([asdict(x) for x in res],open(out,"w"),indent=2)
    def ok_(r): return (r.ok and not wname(r) and (r.self_corr is None or abs(r.self_corr)<0.7) and r.sharpe>1.25)
    oks=sorted([r for r in res if r.ok],key=lambda r:r.sharpe,reverse=True)
    print("\n"+"="*110)
    print(f"D0 SENTIMENT: {sum(1 for r in oks if ok_(r))} submittable / {len(oks)} ok")
    for r in oks:
        sc=f"{r.self_corr:+.2f}" if r.self_corr is not None else "  - "
        print(f"  {r.family:<20} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={sc} FAIL={wname(r)} {'*** SUBMIT ***' if ok_(r) else ''} {r.alpha_id}")
    for r in [r for r in res if not r.ok]: print(f"  FAIL {r.family}: {str(r.error)[:70]}")
    print("="*110); log.info(f"wrote {out}")
    return 0
if __name__=="__main__": sys.exit(main() or 0)
