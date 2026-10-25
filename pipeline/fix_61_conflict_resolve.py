"""Resolve sandwiched conflict slots with (a) votes from ALL parallels of the slot, (b) teacher-student adjacency counts from the whole corpus (x->y and y->z adjacent asserted pairs).
Calibrates on slots where the mention's own written name decides (ism+father match for exactly one candidate), then reports decisions on the rest.  Read-only.
  python pipeline/fix_61_conflict_resolve.py -> labels/conflict_resolved.json"""
from paths import *
import sqlite3, json, collections, re, math, numpy as np
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
P = np.load('labels/parallels.npz'); M = np.load('labels/par_meta.npz'); ids = M['ids']; PA = P['a']; PB = P['b']
hix = {h: i for i, h in enumerate(ids)}; CH = [[] for _ in ids]
for rid, h, nid, pos, sf in c.execute('select rowid,hadith_id,narrator_id,pos,surface from chain_mention where start is not null and coalesce(chain_no,1)=1'):
    i = hix.get(h)
    if i is not None: CH[i].append((pos, rid, nid, sf))
CH = [[(r, n, s) for _, r, n, s in sorted(x)] for x in CH]
names = dict(c.execute('select id,std_name from narrator')); death = dict(c.execute('select id,death_year from narrator where death_year is not null'))
adj = collections.Counter()
for ch in CH:
    for a, b in zip(ch, ch[1:]):
        if a[1] and b[1]: adj[(a[1], b[1])] += 1
print('adjacent pairs', len(adj), flush=True)
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def tk(s):
    t = re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR)).split()
    t = [x[1:] if x.startswith('و') and len(x) > 3 else x for x in t]
    return [(x[2:] if x.startswith('ال') and len(x) > 4 else x).rstrip('ا') if len(x) > 3 else x for x in t]
def parts(s):
    t = tk(s)
    if not t: return None, None
    return t[0], (t[2] if len(t) >= 3 and t[1] in ('بن', 'ابن') else None)
def namefit(sf, nid):  # 1 fits, 0 contradicts, None unknown (kunya/relative/empty)
    t = tk(sf)
    if not t or t[0] in ('ابو', 'ام', 'ابي', 'ابيه', 'جده', 'عمه', 'امه', 'عم'): return None
    a, b = parts(sf); x, y = parts(names.get(nid))
    return int(a == x and not (b and y and b != y))
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
S = {}   # rowid -> dict(x,z,votes Counter, surface, hadith)
for a, b in zip(PA, PB):
    A, B = CH[a], CH[b]
    if len(A) < 3 or len(B) < 3: continue
    an = anchors(A, B)
    for (i1, j1), (i2, j2) in zip(an, an[1:]):
        if i2 - i1 == 2 and j2 - j1 == 2:
            ma, mb = A[i1 + 1], B[j1 + 1]
            if not (ma[1] and mb[1]): continue
            for m, o, h in ((ma, mb, a), (mb, ma, b)):
                d = S.setdefault(m[0], {'x': A[i1][1] if h == a else B[j1][1], 'z': A[i2][1] if h == a else B[j2][1], 'sf': m[2], 'h': str(ids[h]), 'own': m[1], 'v': collections.Counter()})
                d['v'][o[1]] += 1
conf = {r: d for r, d in S.items() if any(k != d['own'] for k in d['v'])}
print('mentions in slots', len(S), '| with a conflict', len(conf), flush=True)
def score(d, y, nvotes_by):
    return math.log1p(adj[(d['x'], y)]) + math.log1p(adj[(y, d['z'])]) + 0.5 * math.log1p(nvotes_by.get(y, 0))
def decide(d):
    votes = dict(d['v']); votes[d['own']] = votes.get(d['own'], 0)
    cands = list(votes)
    sc = {y: score(d, y, votes) for y in cands}; best = max(sc, key=sc.get); srt = sorted(sc.values(), reverse=True)
    margin = srt[0] - (srt[1] if len(srt) > 1 else 0)
    return best, margin, sc
# calibration: slots whose own surface decides
cal = collections.Counter(); out = {}
for r, d in conf.items():
    cands = [d['own']] + [k for k in d['v'] if k != d['own']]; fits = {y: namefit(d['sf'], y) for y in cands}
    truth = [y for y in cands if fits[y] == 1]
    best, margin, sc = decide(d)
    if len(truth) == 1 and all(fits[y] == 0 for y in cands if y != truth[0]):
        for mg in (0, 1, 2):
            if margin > mg: cal[(mg, 'n')] += 1; cal[(mg, 'ok')] += int(best == truth[0])
        cal['truth_cases'] += 1; out[r] = {'kind': 'name_decides', 'truth': truth[0], 'own': d['own'], 'h': d['h']}
    else:
        out[r] = {'kind': 'undecided_by_name', 'best': best, 'margin': round(margin, 2), 'own': d['own'], 'h': d['h'], 'cands': {k: round(v, 2) for k, v in sc.items()}}
print('name-decided cases', cal['truth_cases'])
for mg in (0, 1, 2): print(f'  relations+votes accuracy where margin>{mg}: {cal[(mg, "ok")]}/{cal[(mg, "n")]} = {cal[(mg, "ok")] / max(1, cal[(mg, "n")]):.1%}')
und = [x for x in out.values() if x['kind'] == 'undecided_by_name']
print('undecided by name:', len(und)); [print(f'  margin>{mg}: {sum(1 for x in und if x["margin"] > mg)} (best==own: {sum(1 for x in und if x["margin"] > mg and x["best"] == x["own"])})') for mg in (0, 1, 2, 3)]
json.dump(out, open('labels/conflict_resolved.json', 'w'))
