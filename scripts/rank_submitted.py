import json
d = json.load(open('scratch_all_alphas.json'))
sub = [a for a in d if a.get('status') == 'ACTIVE' or a.get('dateSubmitted')]

def row(a):
    s = a.get('settings') or {}
    iz = a.get('is') or {}
    checks = iz.get('checks') or []
    npass = sum(1 for c in checks if c.get('result') == 'PASS')
    nfail = sum(1 for c in checks if c.get('result') == 'FAIL')
    expr = a.get('regular')
    if not isinstance(expr, str):
        expr = json.dumps(expr)
    return dict(id=a.get('id'), delay=s.get('delay'), sharpe=iz.get('sharpe'),
                turnover=iz.get('turnover'), fitness=iz.get('fitness'),
                returns=iz.get('returns'), drawdown=iz.get('drawdown'),
                margin=iz.get('margin'), selfcorr=iz.get('selfCorrelation'),
                prodcorr=iz.get('prodCorrelation'), grade=a.get('grade'),
                checks=f'{npass}P/{nfail}F/{len(checks)}', uni=s.get('universe'),
                neut=s.get('neutralization'), decay=s.get('decay'),
                trunc=s.get('truncation'), region=s.get('region'),
                dateSub=a.get('dateSubmitted'), expr=expr)

rows = [row(a) for a in sub]
rows.sort(key=lambda r: (r['sharpe'] is not None, r['sharpe'] or -9), reverse=True)
json.dump(rows, open('scratch_submitted_ranked.json', 'w'), indent=1, default=str)

for delay in [1, 0]:
    print(f"\n===== DELAY {delay} =====")
    drs = [r for r in rows if r['delay'] == delay]
    for r in drs:
        print(f"{r['id']} grade={r['grade']:<11} SH={r['sharpe']!s:>7} TO={r['turnover']!s:>7} "
              f"FIT={r['fitness']!s:>6} RET={r['returns']!s:>7} DD={r['drawdown']!s:>7} "
              f"MGN={r['margin']!s:>8} selfC={r['selfcorr']!s:>6} prodC={r['prodcorr']!s:>7} "
              f"chk={r['checks']} {r['neut']}/dec{r['decay']}/tr{r['trunc']}")
        print(f"     {r['expr']}")
