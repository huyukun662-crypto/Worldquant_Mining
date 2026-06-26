"""Score submitted alphas against the WQ competition's 4 judge criteria
(innovation / depth / operator-dataset mastery / overall impact), not raw metrics.
"""
import json, re
from collections import Counter

rows = json.load(open('scratch_submitted.json'))

# Operator taxonomy --------------------------------------------------------
BASIC = {  # common / beginner operators -> low score on criterion 3
    'add', 'subtract', 'multiply', 'divide', 'rank', 'zscore', 'log', 'abs',
    'ts_mean', 'ts_std_dev', 'ts_delay', 'ts_delta', 'ts_sum', 'ts_corr',
    'less', 'greater', 'power', 'scale', 'reverse', 'sign', 'min', 'max',
    'if_else', 'is_nan', 'std',
}
ADVANCED = {  # rarer / sophisticated operators -> reward on criterion 3
    'trade_when', 'signed_power', 'quantile', 'vector_neut', 'hump',
    'ts_arg_min', 'ts_arg_max', 'ts_av_diff', 'ts_backfill', 'group_neutralize',
    'winsorize', 'group_zscore', 'ts_zscore', 'ts_rank', 'ts_decay_linear',
    'group_rank', 'group_mean', 'kth_element', 'ts_co_kurtosis', 'ts_co_skewness',
    'ts_regression', 'ts_scale', 'ts_quantile', 'normalize', 'pasteurize',
    'ts_backfill', 'ts_min', 'ts_max', 'ts_product', 'ts_rank',
}

# Dataset families ---------------------------------------------------------
DATASETS = {
    'options_iv': r'implied_volatility',
    'options_pcr': r'pcr_oi|put_call|pcr_',
    'news': r'news_',
    'analyst_model': r'mdl\d+_|est_|analyst',
    'short_interest': r'short|lend_supply|days_to_cover',
    'sentiment': r'snt_|social',
    'relationship': r'rel_ret',
    'fundamental': r'\b(sales|cap|fcf|inventory|book|ebit|netprofit|assets|epsr|revenue|earnings)\b',
    'price_volume': r'\b(close|open|high|low|volume|vwap|adv\d+|returns)\b',
    'volatility_field': r'historical_volatility|parkinson|garman',
}

OP_RE = re.compile(r'([a-z_][a-z0-9_]*)\s*\(')

def analyze(a):
    r = a.get('regular')
    code = r['code'] if isinstance(r, dict) else (r or '')
    ops = [o for o in OP_RE.findall(code)]
    opset = set(ops)
    adv = sorted(opset & ADVANCED)
    n_adv = len(adv)
    n_basic = len(opset & BASIC)
    ds = sorted(k for k, pat in DATASETS.items() if re.search(pat, code))
    # exclude price_volume from "alt-data" novelty count
    alt_ds = [d for d in ds if d != 'price_volume']
    return code, sorted(opset), adv, n_adv, n_basic, ds, alt_ds

def sc(v, lo, hi):  # clamp-scale to 1..5
    if v <= lo: return 1.0
    if v >= hi: return 5.0
    return 1 + 4 * (v - lo) / (hi - lo)

GRADE = {'SPECTACULAR': 5, 'EXCELLENT': 4, 'GOOD': 3, 'AVERAGE': 2, 'INFERIOR': 1, 'UNKNOWN': 1}

out = []
for a in rows:
    iz = a.get('is') or {}
    s = a.get('settings') or {}
    code, opset, adv, n_adv, n_basic, ds, alt_ds = analyze(a)
    # criterion 3: operator+dataset mastery
    c3 = round(min(5.0, 0.6*sc(n_adv,0,5) + 0.4*sc(len(alt_ds),0,3) + 0.0), 2)
    c3 = round(0.55*sc(n_adv,0,5) + 0.45*sc(len(alt_ds),0,3), 2)
    # criterion 1: innovation ~ alt-dataset breadth + advanced ops + low self-corr
    selfc = iz.get('selfCorrelation') or 0
    c1 = round(0.45*sc(len(alt_ds),0,3) + 0.30*sc(n_adv,1,5) + 0.25*sc(1-selfc,0.2,0.9), 2)
    # criterion 2: depth/explainability ~ has clear multi-term structured logic
    # proxy: uses gating/economic transforms & multiple named fields, not 1-liner
    n_fields = len(set(re.findall(r'[a-z_][a-z0-9_]{3,}', code)) - set(opset))
    has_gate = any(o in opset for o in ('trade_when','if_else','quantile','group_neutralize','vector_neut'))
    c2 = round(min(5.0, 0.5*sc(n_adv,0,5) + 0.3*sc(len(alt_ds),0,3) + (0.8 if has_gate else 0) + 0.4*sc(len(opset),2,10)),2)
    # criterion 4: overall impact ~ metrics quality (grade + sharpe + fitness)
    c4 = round(0.4*GRADE.get(a.get('grade'),1) + 0.35*sc(iz.get('sharpe') or 0,1.0,2.8) + 0.25*sc(iz.get('fitness') or 0,1.0,3.6),2)
    total = round(c1+c2+c3+c4,2)
    out.append(dict(id=a['id'], delay=s.get('delay'), grade=a.get('grade'),
                    sh=iz.get('sharpe'), fit=iz.get('fitness'), to=iz.get('turnover'),
                    dd=iz.get('drawdown'), selfc=selfc, n_adv=n_adv, adv=adv,
                    alt_ds=alt_ds, n_fields=n_fields,
                    C1_innov=round(c1,1), C2_depth=round(c2,1), C3_ops=round(c3,1),
                    C4_impact=round(c4,1), JUDGE=round(total,1), expr=code))

for delay in [1, 0]:
    g = sorted([r for r in out if r['delay']==delay], key=lambda r:r['JUDGE'], reverse=True)
    print(f"\n===== DELAY {delay} — ranked by JUDGE total (4 criteria, max 20) =====")
    print(f"{'id':<10}{'JUDGE':>6}{'C1':>4}{'C2':>4}{'C3':>4}{'C4':>4} {'grade':<12}{'SH':>5}{'FIT':>5} {'#adv':>4} datasets")
    for r in g[:8]:
        print(f"{r['id']:<10}{r['JUDGE']:>6}{r['C1_innov']:>4}{r['C2_depth']:>4}{r['C3_ops']:>4}{r['C4_impact']:>4} "
              f"{r['grade']:<12}{r['sh']!s:>5}{r['fit']!s:>5} {r['n_adv']:>4} {','.join(r['alt_ds'])}")
json.dump(out, open('scratch_judge.json','w'), indent=1)
