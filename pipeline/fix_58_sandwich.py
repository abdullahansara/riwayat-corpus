"""Sandwich rule on parallel chains (zero tokens, read-only 'stats').  For a parallel pair (fix_57) align the two chains on identical asserted narrator ids (order preserving).
Between two consecutive anchors x..z, if both chains have exactly ONE mention (y_a, y_b) they are the same person, even if the names differ.
  one side unresolved -> 'transfer' candidate;  both resolved, different ids -> 'conflict' (merge evidence, counted per id pair);  gap sizes (1,0)/(0,1)/(2,1).. -> parse discrepancy.
  python pipeline/fix_58_sandwich.py stats [MAXPAIRS]  -> labels/sandwich.json"""
from paths import *
import sqlite3, sys, json, collections, numpy as np, time
MODE = sys.argv[1]; MAXP = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
P = np.load('labels/parallels.npz'); M = np.load('labels/par_meta.npz'); ids = M['ids']; PA = P['a']; PB = P['b']
hix = {h: i for i, h in enumerate(ids)}
print('loading chains', flush=True); t00 = time.time()
CH = [None] * len(ids)
cur = None
for rid, h, nid, cn, pos in c.execute('select rowid,hadith_id,narrator_id,coalesce(chain_no,1),pos from chain_mention where start is not null and coalesce(chain_no,1)=1'):
    i = hix.get(h)
    if i is None: continue
    if CH[i] is None: CH[i] = []
    CH[i].append((pos, rid, nid))
for i in range(len(CH)):
    if CH[i]: CH[i] = [(r, n) for _, r, n in sorted(CH[i])]
    else: CH[i] = []
print('chains loaded', round(time.time() - t00), 's', flush=True)
def chain(h): return CH[hix[h]]
def anchors(A, B):
    ia = collections.defaultdict(list); ib = collections.defaultdict(list)
    for i, x in enumerate(A):
        if x[1]: ia[x[1]].append(i)
    for j, x in enumerate(B):
        if x[1]: ib[x[1]].append(j)
    pr = sorted((ia[n][0], ib[n][0]) for n in ia if n in ib and len(ia[n]) == 1 and len(ib[n]) == 1)
    out = []; lastj = -1
    for i, j in pr:
        if j > lastj: out.append((i, j)); lastj = j
    return out
tr = {}; conf = collections.Counter(); both_null = 0; gaps = collections.Counter(); npairs = 0; nanch = collections.Counter(); t0 = time.time()
order = np.argsort(PA, kind='stable')
for n, k in enumerate(order[:MAXP]):
    a, b = int(PA[k]), int(PB[k]); A, B = CH[a], CH[b]
    if len(A) < 3 or len(B) < 3: continue
    an = anchors(A, B)
    if len(an) < 2: nanch[len(an)] += 1; continue
    npairs += 1
    for (i1, j1), (i2, j2) in zip(an, an[1:]):
        ga, gb = i2 - i1 - 1, j2 - j1 - 1; gaps[(min(ga, 3), min(gb, 3))] += 1
        if ga == 1 and gb == 1:
            ma, mb = A[i1 + 1], B[j1 + 1]
            if ma[1] and mb[1]:
                if ma[1] != mb[1]: conf[tuple(sorted((ma[1], mb[1])))] += 1
            elif ma[1] and not mb[1]: tr.setdefault(mb[0], collections.Counter())[ma[1]] += 1
            elif mb[1] and not ma[1]: tr.setdefault(ma[0], collections.Counter())[mb[1]] += 1
            else: both_null += 1
    if n % 200000 == 0: print(n, npairs, len(tr), round(time.time() - t0), 's', flush=True)
agree = sum(1 for v in tr.values() if len(v) == 1)
res = {'pairs_with_2plus_anchors': npairs, 'pairs_with_<2_anchors': dict(nanch), 'transfer_mentions': len(tr), 'transfer_unambiguous': agree,
       'conflict_idpairs': len(conf), 'conflict_idpairs_support>=2': sum(1 for v in conf.values() if v >= 2), 'both_null_slots': both_null,
       'gap_shapes(a,b)': {str(k): v for k, v in sorted(gaps.items())}}
print(json.dumps(res, indent=1))
json.dump({'summary': res, 'transfer': {str(k): dict(v) for k, v in tr.items()}, 'conflict': [[a, b, v] for (a, b), v in conf.most_common(2000)]}, open('labels/sandwich.json', 'w'))
