"""Independent teacher-student check (Muslimscholars lists) on sandwiched conflict slots.  Read-only.
Chain order is collector first: x narrates from y, y from z  =>  y is a teacher of x (y in T[x] / x in S[y]) and z is a teacher of y.
rel(y) = [x-y edge confirmed] + [y-z edge confirmed], using ms ids for x,y,z (links from our narrator ids; ism+father[+death], also all name forms).
Calibrates on slots decided by the mention's own written name, then reports decisions for the rest.  python pipeline/fix_63_ms_relations.py"""
from paths import *
import sqlite3, json, csv, re, collections, numpy as np
csv.field_size_limit(10**9); EXT = ROOT + 'external/zenodo_21019693/zenodo/'
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def tk(s):
    s = re.split(r'[(（]', s or '')[0]; t = re.sub('[^ء-ي ]', ' ', DIAC.sub('', s).translate(TR)).split()
    t = [x[1:] if x.startswith('و') and len(x) > 3 else x for x in t]
    return [(x[2:] if x.startswith('ال') and len(x) > 4 else x).rstrip('ا') if len(x) > 3 else x for x in t]
ms = {}
for r in csv.DictReader(open(EXT + 'muslimscholars_scholars.csv', encoding='utf-8', newline='')):
    try: d = float(r['death_year_h']) if r['death_year_h'] else None
    except Exception: d = None
    ms[int(r['id'])] = {'t': tk(r['name_ar']), 'd': d, 'T': set(json.loads(r['teacher_ids'] or '[]')), 'S': set(json.loads(r['student_ids'] or '[]'))}
idx = collections.defaultdict(list)
for i, v in ms.items():
    t = v['t']
    if len(t) >= 3 and t[1] in ('بن', 'ابن'): idx[(t[0], t[2])].append(i)
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
names = dict(c.execute('select id,std_name from narrator')); death = dict(c.execute('select id,death_year from narrator where death_year is not null'))
keys = collections.defaultdict(set)
for nid, nm in names.items():
    t = tk(nm)
    if len(t) >= 3 and t[1] in ('بن', 'ابن'): keys[nid].add((t[0], t[2]))
for nid, f in c.execute('select narrator_id,form from narrator_name'):
    t = tk(f)
    if len(t) >= 3 and t[1] in ('بن', 'ابن') and nid in names: keys[nid].add((t[0], t[2]))
link = {}
for nid, ks in keys.items():
    cs = set()
    for k in ks: cs |= set(idx.get(k, []))
    if death.get(nid): cs = {i for i in cs if ms[i]['d'] and abs(ms[i]['d'] - death[nid]) <= 2} or (cs if len(cs) == 1 else set())
    if len(cs) == 1: link[nid] = next(iter(cs))
print('linked narrators', len(link), flush=True)
def edge(a, b):  # a (student) from b (teacher): confirmed?  None if either unlinked
    ia, ib = link.get(a), link.get(b)
    if ia is None or ib is None: return None
    return int(ib in ms[ia]['T'] or ia in ms[ib]['S'])
def rel(x, y, z):
    e1, e2 = edge(x, y), edge(y, z)
    return None if e1 is None and e2 is None else (e1 or 0) + (e2 or 0)
P = np.load('labels/parallels.npz'); M = np.load('labels/par_meta.npz'); ids = M['ids']; PA = P['a']; PB = P['b']
hix = {h: i for i, h in enumerate(ids)}; CH = [[] for _ in ids]
for rid, h, nid, pos, sf in c.execute('select rowid,hadith_id,narrator_id,pos,surface from chain_mention where start is not null and coalesce(chain_no,1)=1'):
    i = hix.get(h)
    if i is not None: CH[i].append((pos, rid, nid, sf))
CH = [[(r, n, s) for _, r, n, s in sorted(x)] for x in CH]
def parts(s):
    t = tk(s); return (t[0] if t else None), (t[2] if len(t) >= 3 and t[1] in ('بن', 'ابن') else None)
def namefit(sf, nid):
    t = tk(sf)
    if not t or t[0] in ('ابو', 'ام', 'ابي', 'ابيه', 'جده', 'عمه', 'امه', 'عم'): return None
    a, b = parts(sf); x, y = parts(names.get(nid)); return int(a == x and not (b and y and b != y))
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
S = {}
for a, b in zip(PA, PB):
    A, B = CH[a], CH[b]
    if len(A) < 3 or len(B) < 3: continue
    an = anchors(A, B)
    for (i1, j1), (i2, j2) in zip(an, an[1:]):
        if i2 - i1 == 2 and j2 - j1 == 2:
            ma, mb = A[i1 + 1], B[j1 + 1]
            if not (ma[1] and mb[1]): continue
            for m, o, h, X, Z in ((ma, mb, a, A[i1][1], A[i2][1]), (mb, ma, b, B[j1][1], B[j2][1])):
                d = S.setdefault(m[0], {'x': X, 'z': Z, 'sf': m[2], 'h': str(ids[h]), 'own': m[1], 'v': collections.Counter()}); d['v'][o[1]] += 1
conf = {r: d for r, d in S.items() if any(k != d['own'] for k in d['v'])}
cal = collections.Counter(); out = {}; res = collections.Counter()
for r, d in conf.items():
    cands = [d['own']] + [k for k in d['v'] if k != d['own']]
    rl = {y: rel(d['x'], y, d['z']) for y in cands}; fits = {y: namefit(d['sf'], y) for y in cands}
    truth = [y for y in cands if fits[y] == 1]
    known = {y: v for y, v in rl.items() if v is not None}
    best = None
    if len(known) >= 2:
        mx = max(known.values()); top = [y for y, v in known.items() if v == mx]
        if len(top) == 1 and mx > min(known.values()): best = top[0]
    if len(truth) == 1 and all(fits[y] == 0 for y in cands if y != truth[0]):
        cal['name_decided'] += 1
        if len(known) >= 2: cal['both_scored'] += 1
        if best: cal['decided'] += 1; cal['ok'] += int(best == truth[0])
        out[r] = {'kind': 'name_decides', 'truth': truth[0], 'own': d['own'], 'h': d['h'], 'best': best}
    else:
        res['undecided_by_name'] += 1
        if len(known) >= 2: res['relation_scored'] += 1
        if best: res['relation_decides'] += 1; res['decides_own'] += int(best == d['own'])
        out[r] = {'kind': 'undecided_by_name', 'own': d['own'], 'h': d['h'], 'best': best, 'rel': {k: v for k, v in rl.items()}}
print('CALIBRATION on name-decided slots:', dict(cal), '| accuracy %.1f%%' % (100 * cal['ok'] / max(1, cal['decided'])))
print('UNDECIDED-BY-NAME slots:', dict(res))
json.dump(out, open('labels/conflict_ms.json', 'w'))
