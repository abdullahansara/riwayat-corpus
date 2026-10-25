import sys, csv, ast, sqlite3, re, collections, time
sys.path.insert(0, '<WORKDIR>')
from link_lib import norm2
csv.field_size_limit(10**9)
S = '<ROOT>/Sanadset/'
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
def key(n):
    k = norm2(n).replace('ابن', 'بن'); t = k.split()
    if t and len(t[0]) > 2 and t[0][0] == 'و' and t[0] not in ('وهب', 'وكيع', 'وراق'): t[0] = t[0][1:]
    return ' '.join(t)
def compat(a, b):
    ta, tb = set(a.split()), set(b.split())
    return bool(ta) and bool(tb) and (ta <= tb or tb <= ta)
# --- alignment (clean matches only)
al = {}
with open(S + 'align_sanadset_kg.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[2] and x[4] in ('full', 'head+tail') and x[5] == '1': al[int(x[0])] = int(x[2])
log('clean aligned rows', len(al))
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True); cur = con.cursor()
def kg_names(batch):
    ids = sorted(set(batch)); out = {}
    q = ','.join('?' * len(ids))
    nass = dict(cur.execute(f'select id, nass from hadiths where id in ({q})', ids))
    ms = collections.defaultdict(list)
    for hid, seq, a, b in cur.execute(f'select hadith_id, seq, start, end from hadith_rawis where hadith_id in ({q}) order by hadith_id, seq', ids):
        ms[hid].append((a, b))
    for hid in ids:
        t = nass.get(hid) or ''; out[hid] = [t[a:b] for a, b in ms.get(hid, [])]
    return out
cat = collections.defaultdict(collections.Counter); out_rows = []; samples = collections.defaultdict(list)
batch = []
def process(batch):
    kn = kg_names([b[2] for b in batch])
    for rid, san, kid, src, book in batch:
        kg = kn[kid]; sk = [key(n) for n in san]; kk = [key(n) for n in kg]
        if not sk and not kk: c = 'both_empty'
        elif not kk: c = 'kg_empty'
        elif not sk: c = 'sanadset_empty'
        elif sk == kk: c = 'identical'
        elif len(sk) == len(kk) and all(a == b or compat(a, b) for a, b in zip(sk, kk)): c = 'same_chain_name_variants'
        elif len(sk) == len(kk): c = 'same_length_different_names'
        elif len(sk) > len(kk): c = 'sanadset_longer'
        else: c = 'kg_longer'
        cat[src][c] += 1; out_rows.append((rid, kid, c, len(sk), len(kk)))
        if len(samples[c]) < 6 and c not in ('identical', 'both_empty'): samples[c].append((rid, book, san, kg))
n = 0
with open(S + 'hadith_unified.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        rid = int(x[0])
        if rid not in al: continue
        try: san = ast.literal_eval(x[4]) if x[4] else []
        except Exception: san = []
        batch.append((rid, san, al[rid], x[9], x[1]))
        if len(batch) >= 4000: process(batch); n += len(batch); batch = []; log('compared', n)
if batch: process(batch); n += len(batch)
log('DONE', n)
with open(S + 'chain_agreement.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['sanadset_row', 'kg_hadith_id', 'category', 'n_sanadset', 'n_kg']); w.writerows(out_rows)
tot = collections.Counter()
for s in cat: tot.update(cat[s])
T = sum(tot.values()); print('\nOVERALL chain agreement on', T, 'aligned hadith:')
for c, v in tot.most_common(): print(f'  {c:30s} {v:8d} {v/T:6.1%}')
print('\nBY SANADSET CHAIN SOURCE:')
for s in cat:
    t = sum(cat[s].values()); print(f' {s} ({t}):', {c: f'{v/t:.1%}' for c, v in cat[s].most_common()})
print('\nSAMPLE DISAGREEMENTS:')
for c, L in samples.items():
    print('====', c)
    for rid, book, san, kg in L[:3]: print(f'  #{rid} [{book[:20]}]\n     SANADSET: {" ; ".join(san)[:170]}\n     HADITH-KG: {" ; ".join(kg)[:170]}')
