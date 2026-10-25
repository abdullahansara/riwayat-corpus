"""Score the database's chains/IDs against gold/gold_chains.jsonl (hand-corrected chains).
Usage: python tools/gold_score.py [path/to/hadith_master.db]
Matching: a database mention matches a gold mention if their character spans overlap by >= 50 % of the shorter span.
Metrics are computed on the database state at the time of scoring, so run it BEFORE writing the gold corrections into the database
(or on a copy / the original database) to measure the pipeline, and after to confirm they were applied."""
import sqlite3, sys, os, json, collections, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
db = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
MERGE = dict(c.execute('select old_id,new_id from narrator_merge'))
gold = [json.loads(l) for l in open(ROOT / 'gold' / 'gold_chains.jsonl', encoding='utf-8')]
def overlap(a, b):
    o = min(a[1], b[1]) - max(a[0], b[0])
    return o > 0 and o >= 0.5 * min(a[1] - a[0], b[1] - b[0])
S = collections.defaultdict(collections.Counter); ID = collections.defaultdict(collections.Counter)
for g in gold:
    key = g['tier'] + ('-shia' if g['tradition'].startswith('shi') else '')
    pred = [dict(start=s, end=e, nid=n, meth=m) for s, e, n, m in c.execute('select start,end,narrator_id,id_method from chain_mention where hadith_id=? order by pos', (g['hadith_id'],))]
    gm = g['mentions']; used = set(); tp = 0
    for p in pred:
        hit = next((i for i, m in enumerate(gm) if i not in used and overlap((p['start'], p['end']), (m['start'], m['end']))), None)
        if hit is None: continue
        used.add(hit); tp += 1; m = gm[hit]
        if m['id_verified']:
            ok = (p['nid'] == MERGE.get(m['narrator_id'], m['narrator_id']))
            ID[key]['n'] += 1; ID[key]['ok'] += ok
            ID['method:' + (p['meth'] or 'none')]['n'] += 1; ID['method:' + (p['meth'] or 'none')]['ok'] += ok
            ID['ALL']['n'] += 1; ID['ALL']['ok'] += ok
    fp = len(pred) - tp; fn = len(gm) - tp
    exact = (fp == 0 and fn == 0)
    for k in (key, 'ALL'):
        S[k]['hadith'] += 1; S[k]['exact_chain'] += exact; S[k]['tp'] += tp; S[k]['fp'] += fp; S[k]['fn'] += fn
        S[k]['chain_ok_ids'] += exact and all(m['id_verified'] and True for m in gm) and False
print(f'{"group":10s} {"hadith":>6s} {"chain exact":>12s} {"mention P":>10s} {"mention R":>10s} {"F1":>6s} | {"ID acc (verified, matched)":>28s}')
for k in sorted(S, key=lambda x: (x == 'ALL', x)):
    s = S[k]; p = s['tp'] / max(1, s['tp'] + s['fp']); r = s['tp'] / max(1, s['tp'] + s['fn']); f = 2 * p * r / max(1e-9, p + r)
    i = ID[k]
    print(f'{k:10s} {s["hadith"]:6d} {s["exact_chain"]/s["hadith"]:12.1%} {p:10.3f} {r:10.3f} {f:6.3f} | {i["ok"]:4d}/{i["n"]:<4d} = {i["ok"]/max(1,i["n"]):6.1%}')
print('\nID accuracy by assignment method (verified, matched mentions):')
for k, v in sorted(ID.items(), key=lambda kv: -kv[1]['n']):
    if k.startswith('method:') and v['n'] >= 3: print(f'  {k[7:]:36s} {v["ok"]:4d}/{v["n"]:<4d} = {v["ok"]/v["n"]:6.1%}')
