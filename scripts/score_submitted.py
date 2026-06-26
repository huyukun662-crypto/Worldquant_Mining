import json
rows = json.load(open('scratch_submitted_ranked.json'))

GRADE = {'SPECTACULAR': 5, 'EXCELLENT': 4, 'GOOD': 3, 'AVERAGE': 2, 'INFERIOR': 1, 'UNKNOWN': 0}

def norm(vals):
    lo, hi = min(vals), max(vals)
    return lambda x: 0.5 if hi == lo else (x - lo) / (hi - lo)

# weights (higher-is-better unless inverted)
W = dict(sharpe=0.32, fitness=0.24, margin=0.10, turnover=0.10,
         drawdown=0.10, selfcorr=0.08, returns=0.06)

def score_group(group):
    g = [r for r in group if r['sharpe'] is not None]
    ns = norm([r['sharpe'] for r in g])
    nf = norm([r['fitness'] for r in g])
    nm = norm([r['margin'] for r in g])
    nt = norm([r['turnover'] for r in g])
    nd = norm([r['drawdown'] for r in g])
    nc = norm([r['selfcorr'] for r in g])
    nr = norm([r['returns'] for r in g])
    for r in g:
        comp = (W['sharpe']*ns(r['sharpe']) + W['fitness']*nf(r['fitness'])
                + W['margin']*nm(r['margin'])
                + W['turnover']*(1-nt(r['turnover']))
                + W['drawdown']*(1-nd(r['drawdown']))
                + W['selfcorr']*(1-nc(r['selfcorr']))
                + W['returns']*nr(r['returns']))
        r['composite'] = round(100*comp, 1)
    g.sort(key=lambda r: r['composite'], reverse=True)
    return g

for delay in [1, 0]:
    grp = score_group([r for r in rows if r['delay'] == delay])
    print(f"\n===== DELAY {delay}  (n={len(grp)}) — ranked by composite =====")
    print(f"{'rank':<5}{'id':<10}{'comp':>6}{'grade':<13}{'SH':>6}{'FIT':>6}{'TO':>7}{'RET':>7}{'DD':>7}{'MGN':>9}{'selfC':>7}")
    for i, r in enumerate(grp, 1):
        print(f"{i:<5}{r['id']:<10}{r['composite']:>6}{r['grade']:<13}{r['sharpe']:>6}{r['fitness']:>6}"
              f"{r['turnover']:>7}{r['returns']:>7}{r['drawdown']:>7}{r['margin']:>9}{r['selfcorr']:>7}")
