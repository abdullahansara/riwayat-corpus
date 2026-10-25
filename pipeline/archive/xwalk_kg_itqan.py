import csv, ast, json, sqlite3, collections, time
csv.field_size_limit(10**9)
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
S = '<ROOT>/Sanadset/'
GOOD = {'unique', 'context', 'relative_father', 'alias_patch', 'unique+backoff', 'context+backoff'}
# hadith whose Sanadset and hadith-kg chains agree position by position
agree = {}
with open(S + 'chain_agreement.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[2] == 'identical': agree[int(x[0])] = int(x[1])
log('identical-chain hadith:', len(agree))
itq = {}                      # sanadset row -> list of confident Itqan ids (None where not confident)
with open(S + 'sanadset_linked_final.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[0] != 'orig': continue
        i = int(x[1])
        if i not in agree: continue
        ids = ast.literal_eval(x[5]); cf = ast.literal_eval(x[6]); mt = ast.literal_eval(x[7])
        itq[i] = [a if (a is not None and m in GOOD and c >= 0.8) else None for a, c, m in zip(ids, cf, mt)]
log('rows with Itqan ids loaded:', len(itq))
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True)
rawi_name = dict(con.execute('select id, name from rawis').fetchall())
items = sorted(itq.items()); C = collections.Counter(); nk = collections.Counter(); ni = collections.Counter(); npairs = 0
for i in range(0, len(items), 4000):
    ch = items[i:i + 4000]; kids = [agree[r] for r, _ in ch]; q = ','.join('?' * len(kids))
    M = collections.defaultdict(list)
    for h, seq, rid in con.execute(f'select hadith_id, seq, rawi_id from hadith_rawis where hadith_id in ({q}) order by hadith_id, seq', kids): M[h].append(rid)
    for r_, ids in ch:
        km = M.get(agree[r_], [])
        if len(km) != len(ids): continue
        for k, t in zip(km, ids):
            if k is None or t is None or k not in rawi_name: continue
            C[(k, t)] += 1; nk[k] += 1; ni[t] += 1; npairs += 1
log('aligned mention pairs:', npairs, '| distinct (kg,itqan) pairs:', len(C))
bk = {}; bi = {}
for (k, t), c in C.items():
    j = c / (nk[k] + ni[t] - c)
    if k not in bk or j > bk[k][1]: bk[k] = (t, j, c)
    if t not in bi or j > bi[t][1]: bi[t] = (k, j, c)
xw = {}
for k, (t, j, c) in bk.items():
    if bi.get(t, (None,))[0] == k and j >= 0.6 and c >= 3: xw[k] = {'itqan': t, 'jaccard': round(j, 3), 'n': c}
cov = sum(nk[k] for k in xw) / sum(nk.values())
log(f'kg narrators seen: {len(nk)} | mutual-best confident links to Itqan: {len(xw)} | share of kg mention occurrences covered: {cov:.1%}')
conf = [(k, t, c) for (k, t), c in C.items() if k in xw and xw[k]['itqan'] != t and c >= 20]
log('kg narrators that ALSO co-occur strongly (>=20) with a different Itqan id (possible duplicates/merges):', len({k for k, _, _ in conf}))
import random; random.seed(1)
top = sorted(xw.items(), key=lambda kv: -kv[1]['n'])[:10] + random.sample(list(xw.items()), 6)
print('SAMPLE kg <-> Itqan links (kg name | Itqan id | Jaccard | n):')
for k, v in top: print(f"   {rawi_name[k][:44]:46s} itqan {v['itqan']:6d}  J={v['jaccard']:.2f} n={v['n']}")
json.dump({str(k): v for k, v in xw.items()}, open('<ROOT>/HadithKG/crosswalk_kg_to_itqan.json', 'w'))
