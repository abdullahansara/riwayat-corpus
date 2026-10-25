"""Phase 4 - sample narrator pairs with the same normalised name for Claude labelling (same person / different / unsure).  Read-only.
  python pipeline/fix_28_pair_sampler.py N CHUNK SEED OUTDIR
Each pair carries: names, death years, tradition, source ids, hadith counts, top teachers / students (by narrator_edge) and a few chain contexts."""
from paths import *
from id_lib import norm
import sqlite3, sys, json, random, collections, os
N, CH, SEED, OUTD = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True); random.seed(SEED)
info = {i: (n, d, t) for i, n, d, t in c.execute('select id,std_name,death_year,tradition from narrator')}
cnt = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
groups = collections.defaultdict(list)
for i, (n, d, t) in info.items():
    k = norm(n)
    if k and i != 'N0003708' and len(k.split()) >= 2: groups[k].append(i)
groups = {k: v for k, v in groups.items() if 1 < len(v) <= 25}
print('same-name groups', len(groups), 'pairs', sum(len(v) * (len(v) - 1) // 2 for v in groups.values()))
src = collections.defaultdict(list)
for i, s, sid in c.execute('select narrator_id,source,source_id from narrator_source_id'): src[i].append(f'{s}:{sid}')
teach = collections.defaultdict(list); stud = collections.defaultdict(list)
for s, t, n in c.execute('select student,teacher,n_hadith from narrator_edge order by n_hadith desc'):
    if len(teach[s]) < 4: teach[s].append((t, n))
    if len(stud[t]) < 4: stud[t].append((s, n))
def card(i):
    n, d, t = info[i]
    return {'id': i, 'name': n[:90], 'died': d, 'tradition': t, 'n_hadith': cnt.get(i, 0), 'sources': src[i][:4],
            'teachers': [(info[x][0][:40], k) for x, k in teach[i] if x in info], 'students': [(info[x][0][:40], k) for x, k in stud[i] if x in info]}
pairs = []
keys = list(groups); random.shuffle(keys)
for k in keys:
    v = groups[k]; a, b = random.sample(v, 2)
    pairs.append((a, b))
    if len(pairs) >= N: break
os.makedirs(OUTD, exist_ok=True)
items = [{'pair_id': f'P{j:05d}', 'a': card(a), 'b': card(b)} for j, (a, b) in enumerate(pairs)]
for k in range(0, len(items), CH): json.dump(items[k:k + CH], open(os.path.join(OUTD, f'chunk_{k // CH:03d}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
print(len(items), 'pairs in', (len(items) + CH - 1) // CH, 'chunks ->', OUTD)
