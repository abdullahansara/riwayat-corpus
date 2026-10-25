"""Phase 4 - merge duplicate narrator records using models/pair_model.pkl (fix_29).
Same-name groups (normalised std_name, 2..25 records, >= 2 words).  A pair is a merge candidate when P(same) >= MERGE_P and there is no hard conflict
(the two appear together in one chain, or death years differ by more than 25).  Candidates are grouped with union-find; the target of each group is
the record with the most source ids, then the most mentions (same rule as fix_08).  Machinery = fix_08's apply (narrator_merge, surgery_log, name/source rows moved).
  python pipeline/fix_30_pair_merge.py pilot [N] [seed]      # score + list N random proposed merges for an eye check (read-only)
  python pipeline/fix_30_pair_merge.py apply                 # score + write"""
from paths import *
from id_lib import norm
from fix_29_pair_model import PairCtx, pair_feats
import sqlite3, sys, json, pickle, random, collections, itertools, time
import numpy as np
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
MERGE_P = 0.8
DBP = OUT + 'hadith_master.db'
c = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply'))
x = PairCtx(c); m, dv = pickle.load(open('models/pair_model.pkl', 'rb'))
groups = collections.defaultdict(list)
for i, (n, d, t) in x.info.items():
    k = norm(n)
    if k and i != 'N0003708' and len(k.split()) >= 2: groups[k].append(i)
groups = {k: v for k, v in groups.items() if 1 < len(v) <= 25}
print('groups', len(groups), flush=True)
parent = {}
def find(a):
    while parent.setdefault(a, a) != a: parent[a] = parent[parent[a]]; a = parent[a]
    return a
t0 = time.time(); npairs = nconf = ncand = 0; probs = {}
for gi, (k, v) in enumerate(groups.items()):
    feats = []; prs = []
    for a, b in itertools.combinations(v, 2):
        f = pair_feats(x, a, b); npairs += 1
        if f['cooccur'] > 0 or f['death_diff_gt25']: nconf += 1; continue
        feats.append(f); prs.append((a, b))
    if not feats: continue
    P = m.predict_proba(dv.transform(feats))[:, 1]
    for (a, b), p in zip(prs, P):
        if p >= MERGE_P: probs[(a, b)] = float(p); ncand += 1; parent[find(a)] = find(b)
    if gi % 2000 == 0: print(f'  {gi}/{len(groups)} groups {time.time() - t0:.0f}s', flush=True)
comp = collections.defaultdict(set)
for a, b in probs: comp[find(a)].update((a, b))
srcs = {i: n for i, n in c.execute('select narrator_id,count(distinct source) from narrator_source_id group by 1')}
merges = {}
for r, ms in comp.items():
    # a component is only accepted when every member pair is conflict-free (transitive closure may join pairs that were not scored as same)
    ms = sorted(ms, key=lambda i: (-srcs.get(i, 0), -x.cnt.get(i, 0), i)); tgt = ms[0]; ok = []
    for o in ms[1:]:
        f = pair_feats(x, tgt, o)
        if f['cooccur'] > 0 or f['death_diff_gt25']: continue
        # short (common) names need independent evidence: shared neighbours or death years that agree within 10; long genealogical names pass on name alone
        if f['n_words'] <= 3 and not (f['sh_teach'] + f['sh_stud'] > 0 or (f['both_dead'] and f['death_diff'] <= 10)): continue
        ok.append(o)
    for o in ok: merges[o] = tgt
print(f'pairs {npairs:,} | hard conflicts {nconf:,} | candidate pairs {ncand:,} | components {len(comp):,} | records to merge {len(merges):,}')
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for o, t in random.sample(list(merges.items()), min(ARG or 30, len(merges))):
        a, b = x.info[o], x.info[t]
        print(o, a[0][:42], a[1], x.cnt.get(o, 0), sorted(x.src[o]), '->', t, b[1], x.cnt.get(t, 0), sorted(x.src[t]), '| shared nbrs', len((x.teach[o] | x.stud[o]) & (x.teach[t] | x.stud[t])))
else:
    c.executescript('CREATE TABLE IF NOT EXISTS narrator_merge(old_id TEXT PRIMARY KEY, new_id TEXT, reason TEXT, jaccard REAL, n_hadith INT);')
    pairs = list(merges.items())
    c.executemany('INSERT OR REPLACE INTO narrator_merge VALUES(?,?,?,?,?)', [(o, n, 'fix_30 pair model P(same)>=0.8, no conflict', None, x.cnt.get(o, 0)) for o, n in pairs])
    for k, (o, n) in enumerate(pairs):
        c.execute("INSERT INTO surgery_log(step,kind,key,old,new) SELECT 'fix_30','mention_narrator_id',rowid,?,? FROM chain_mention WHERE narrator_id=?", (o, n, o))
        c.execute("INSERT INTO surgery_log(step,kind,key,old,new) SELECT 'fix_30','mention_guess_id',rowid,?,? FROM chain_mention WHERE guess_narrator_id=?", (o, n, o))
        for t in ('removed_mention', 'narrator_flag', 'purged_name_form', 'narrator_name', 'narrator_source_id'): c.execute(f'UPDATE OR IGNORE {t} SET narrator_id=? WHERE narrator_id=?', (n, o))
        c.execute('UPDATE chain_mention SET narrator_id=? WHERE narrator_id=?', (n, o)); c.execute('UPDATE chain_mention SET guess_narrator_id=? WHERE guess_narrator_id=?', (n, o))
        old = c.execute('select death_year,birth_year,tabaqa,city from narrator where id=?', (o,)).fetchone()
        for col, val in zip(('death_year', 'birth_year', 'tabaqa', 'city'), old or ()):
            if val is not None: c.execute(f'UPDATE narrator SET {col}=? WHERE id=? AND {col} IS NULL', (val, n))
        c.execute('DELETE FROM narrator WHERE id=?', (o,))
        if k % 2000 == 0: c.commit(); print(f'  merged {k}/{len(pairs)}', flush=True)
    c.execute('UPDATE narrator SET n_sources=(select count(distinct source) from narrator_source_id s where s.narrator_id=narrator.id)')
    mp = dict(pairs); fixed = 0
    for rid, ids in c.execute('select rowid, narrator_ids from reference_chain').fetchall():
        L = json.loads(ids)
        if any(y in mp for y in L): c.execute('UPDATE reference_chain SET narrator_ids=? WHERE rowid=?', (json.dumps([mp.get(y, y) for y in L]), rid)); fixed += 1
    c.commit(); print('applied;', len(pairs), 'records merged;', fixed, 'reference chains updated')
