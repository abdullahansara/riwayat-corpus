"""All sandwiched conflict slots (zero tokens, read-only): parallel chains share anchors x and z, one mention between them in each chain, both resolved, DIFFERENT ids.
For every mention involved: its own id, the opposing ids seen in parallels, chronology fit of each against the anchors, name similarity (duplicate record vs different person), id_method.
  python pipeline/fix_60_conflict_slots.py -> labels/conflict_slots.json"""
from paths import *
import sqlite3, json, collections, re, numpy as np, time
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
P = np.load('labels/parallels.npz'); M = np.load('labels/par_meta.npz'); ids = M['ids']; PA = P['a']; PB = P['b']
hix = {h: i for i, h in enumerate(ids)}; CH = [None] * len(ids)
for rid, h, nid, meth, pos in c.execute('select rowid,hadith_id,narrator_id,id_method,pos from chain_mention where start is not null and coalesce(chain_no,1)=1'):
    i = hix.get(h)
    if i is None: continue
    if CH[i] is None: CH[i] = []
    CH[i].append((pos, rid, nid, meth))
CH = [[(r, n, m) for _, r, n, m in sorted(x)] if x else [] for x in CH]
death = dict(c.execute('select id,death_year from narrator where death_year is not null')); names = dict(c.execute('select id,std_name from narrator'))
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
def tk(s): return {t for t in re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '')).split() if t not in ('بن', 'ابن')}
def sim(a, b):
    x, y = tk(names.get(a)), tk(names.get(b)); return len(x & y) / max(1, min(len(x), len(y)))
def fits(y, prev, nxt):
    dc = death.get(y)
    if not dc: return None
    return not ((prev and (dc > prev + 15 or dc < prev - 80)) or (nxt and (dc < nxt - 5 or dc > nxt + 100)))
def anchors(A, B):
    ia = collections.defaultdict(list); ib = collections.defaultdict(list)
    for i, x in enumerate(A):
        if x[1]: ia[x[1]].append(i)
    for j, x in enumerate(B):
        if x[1]: ib[x[1]].append(j)
    pr = sorted((ia[n][0], ib[n][0]) for n in ia if n in ib and len(ia[n]) == 1 and len(ib[n]) == 1); out = []; lj = -1
    for i, j in pr:
        if j > lj: out.append((i, j)); lj = j
    return out
M_ = {}   # rowid -> dict
for a, b in zip(PA, PB):
    A, B = CH[a], CH[b]
    if len(A) < 3 or len(B) < 3: continue
    an = anchors(A, B)
    for (i1, j1), (i2, j2) in zip(an, an[1:]):
        if i2 - i1 == 2 and j2 - j1 == 2:
            ma, mb = A[i1 + 1], B[j1 + 1]
            if ma[1] and mb[1] and ma[1] != mb[1]:
                pv, nx = death.get(A[i1][1]), death.get(A[i2][1])
                for m, o, h in ((ma, mb, a), (mb, ma, b)):
                    d = M_.setdefault(m[0], {'h': str(ids[h]), 'id': m[1], 'meth': m[2], 'prev': pv, 'next': nx, 'opp': collections.Counter()}); d['opp'][o[1]] += 1
out = {}; stat = collections.Counter()
for rid, d in M_.items():
    own = fits(d['id'], d['prev'], d['next']); top = d['opp'].most_common(1)[0]; of = fits(top[0], d['prev'], d['next'])
    kind = 'same_person_variant' if sim(d['id'], top[0]) >= 0.8 else 'different_person'
    if kind == 'different_person':
        if own is False and of is not False: v = 'own_wrong'
        elif own is not False and of is False: v = 'own_ok'
        elif own is False and of is False: v = 'both_conflict'
        else: v = 'undetermined'
    else: v = 'variant'
    stat[(kind, v)] += 1
    out[rid] = {'hadith': d['h'], 'own': d['id'], 'meth': d['meth'], 'opp': dict(d['opp']), 'kind': kind, 'verdict': v}
json.dump(out, open('labels/conflict_slots.json', 'w'))
print('mentions in conflict slots', len(out)); [print(k, v) for k, v in sorted(stat.items())]
print('by id_method of own (different_person, own_wrong):', collections.Counter(x['meth'] for x in out.values() if x['verdict'] == 'own_wrong').most_common(6))
