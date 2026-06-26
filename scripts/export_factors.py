"""Export all submitted alphas: full settings + expression + NAV (PnL) curves.

Writes:
  SUBMITTED_FACTORS_<userid>.md   -- settings + expression for every submitted alpha
  scratch_nav.json                -- {id: [[date, cum_pnl], ...]} for every alpha
  nav_picks.png                   -- NAV curves of the 4 presentation picks
  nav_all_grid.png                -- small-multiples NAV grid of all submitted alphas
"""
from __future__ import annotations
import json, time
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
CRED = json.loads((REPO / "credential.txt").read_text())
PICKS = {"WjNe3zmj": "D1 #1", "2rvOwEqw": "D1 #2",
         "akN9pwQw": "D0 #1", "xAxOWnVW": "D0 #2"}


def session():
    s = requests.Session()
    s.auth = HTTPBasicAuth(CRED[0], CRED[1])
    for _ in range(6):
        r = s.post("https://api.worldquantbrain.com/authentication", timeout=20)
        if r.status_code == 201:
            return s, r.json().get("user", {}).get("id")
        time.sleep(20)
    raise SystemExit("auth failed")


def fetch_submitted(s):
    base = "https://api.worldquantbrain.com/users/self/alphas"
    out, off = [], 0
    while True:
        r = s.get(f"{base}?limit=100&offset={off}", timeout=40)
        if r.status_code == 429:
            time.sleep(10); continue
        d = r.json(); res = d.get("results", [])
        out.extend(res); off += len(res)
        if not res or off >= d.get("count", 0):
            break
    return [a for a in out if a.get("dateSubmitted")]


def fetch_pnl(s, aid):
    for _ in range(12):
        r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/recordsets/pnl", timeout=40)
        if r.status_code == 429:
            time.sleep(8); continue
        if r.text.strip():
            recs = r.json().get("records", [])
            if recs:
                return [[row[0], row[1]] for row in recs]
        time.sleep(3)
    return []


def main():
    s, uid = session()
    print("user", uid)
    subs = fetch_submitted(s)
    print("submitted:", len(subs))
    subs.sort(key=lambda a: (-(a.get("settings") or {}).get("delay", 0),
                             -(a.get("is") or {}).get("sharpe", 0)))

    # ---- markdown export: settings + expression ----
    lines = [f"# Submitted factors — account {CRED[0]} (user {uid})",
             f"\nTotal submitted: **{len(subs)}**  "
             f"(D1: {sum(1 for a in subs if (a['settings'] or {}).get('delay')==1)}, "
             f"D0: {sum(1 for a in subs if (a['settings'] or {}).get('delay')==0)})\n"]
    SETTING_KEYS = ["region", "universe", "delay", "decay", "neutralization",
                    "truncation", "pasteurization", "unitHandling", "nanHandling",
                    "instrumentType", "language", "maxTrade", "startDate", "endDate"]
    for a in subs:
        st = a.get("settings") or {}; iz = a.get("is") or {}
        r = a.get("regular"); code = r["code"] if isinstance(r, dict) else r
        tag = PICKS.get(a["id"], "")
        lines.append(f"\n## `{a['id']}`  D{st.get('delay')}  {a.get('grade')}"
                     + (f"  ⭐ **{tag}**" if tag else ""))
        lines.append(f"- IS: Sharpe **{iz.get('sharpe')}** · fitness {iz.get('fitness')} "
                     f"· turnover {iz.get('turnover')} · returns {iz.get('returns')} "
                     f"· drawdown {iz.get('drawdown')} · margin {iz.get('margin')} "
                     f"· selfCorr {iz.get('selfCorrelation')}")
        setstr = "  ".join(f"{k}={st.get(k)}" for k in SETTING_KEYS if st.get(k) is not None)
        lines.append(f"- Settings: `{setstr}`")
        lines.append(f"- Expression:\n```\n{code}\n```")
    md = REPO / f"SUBMITTED_FACTORS_{uid}.md"
    md.write_text("\n".join(lines))
    print("wrote", md)

    # ---- NAV fetch for ALL ----
    navs = {}
    for i, a in enumerate(subs, 1):
        navs[a["id"]] = fetch_pnl(s, a["id"])
        print(f"  nav [{i}/{len(subs)}] {a['id']}: {len(navs[a['id']])} pts")
        time.sleep(0.3)
    (REPO / "scratch_nav.json").write_text(json.dumps(navs))

    # ---- plot 4 picks ----
    BOOK = 2e7
    fig, ax = plt.subplots(figsize=(11, 6))
    for aid, tag in PICKS.items():
        rec = navs.get(aid) or []
        if not rec:
            continue
        dates = [row[0] for row in rec]
        nav = [BOOK + row[1] for row in rec]
        a = next(x for x in subs if x["id"] == aid)
        sh = (a.get("is") or {}).get("sharpe")
        ax.plot(range(len(nav)), nav, label=f"{tag}  {aid}  (SH {sh})", linewidth=1.6)
    ax.set_title("NAV (20M book + cumulative PnL) — presentation picks, IS 2019-2023")
    ax.set_xlabel("trading day index (2019-01 → 2023-12)")
    ax.set_ylabel("NAV (USD)")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(REPO / "nav_picks.png", dpi=130)
    print("wrote nav_picks.png")

    # ---- small-multiples grid for all ----
    n = len(subs); cols = 5; rowsn = (n + cols - 1) // cols
    fig2, axes = plt.subplots(rowsn, cols, figsize=(cols*2.6, rowsn*1.8))
    axes = axes.flatten()
    for ax2, a in zip(axes, subs):
        rec = navs.get(a["id"]) or []
        st = a.get("settings") or {}; sh = (a.get("is") or {}).get("sharpe")
        if rec:
            ax2.plot([BOOK + row[1] for row in rec], linewidth=0.9,
                     color="tab:green" if a["id"] in PICKS else "tab:blue")
        ax2.set_title(f"{a['id']} D{st.get('delay')} SH{sh}", fontsize=7)
        ax2.tick_params(labelsize=5)
        if a["id"] in PICKS:
            for sp in ax2.spines.values():
                sp.set_color("tab:green"); sp.set_linewidth(2)
    for ax2 in axes[n:]:
        ax2.axis("off")
    fig2.suptitle(f"NAV curves — all {n} submitted factors (green = picks)", fontsize=11)
    fig2.tight_layout(); fig2.savefig(REPO / "nav_all_grid.png", dpi=120)
    print("wrote nav_all_grid.png")


if __name__ == "__main__":
    main()
