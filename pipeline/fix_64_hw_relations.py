"""Hawramani biography teacher/student lists as an independent relation check on sandwiched conflict slots.  Read-only.
Parse: teacher segments after 'روى عن|يروي عن|سمع من|حدث عن', student segments after 'روى عنه|حدث عنه|سمع منه'.  Link our narrator to Hawramani entries by (ism, father) [+death within 3y].
Tests for candidate y between x (student side) and z (teacher side):  x in y.students, z in y.teachers, y in x.teachers, y in z.students  (names by ism+father token pairs).
Combined with the Muslimscholars check (fix_63).  python pipeline/fix_64_hw_relations.py"""
from paths import *
import sqlite3, json, csv, re, collections, numpy as np
csv.field_size_limit(10**9); EXT = ROOT + 'external/zenodo_21019693/zenodo/'
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def tk(s):
    s = re.split(r'[(（]', s or '')[0]; t = re.sub('[^ء-ي ]', ' ', DIAC.sub('', s).translate(TR)).split()
    t = [x[1:] if x.startswith('و') and len(x) > 3 else x for x in t]
    return [(x[2:] if x.startswith('ال') and len(x) > 4 else x).rstrip('ا') if len(x) > 3 else x for x in t]
def key(t): return (t[0], t[2]) if len(t) >= 3 and t[1] in ('بن', 'ابن') else None
def pairs(s):  # all (ism,father) pairs occurring in a text, as a set of strings 'ism|father'
    t = tk(s); return {t[i] + '|' + t[i + 2] for i in range(len(t) - 2) if t[i + 1] in ('بن', 'ابن')}
TEA = re.compile(r'(?:روى عن|روي عن|يروي عن|سمع من|حدث عن|روايته عن)\s*[:：]?'); STU = re.compile(r'(?:روى عنه|روي عنه|حدث عنه|سمع منه|يروي عنه)\s*[:：]?'); END = re.compile(r'(?:وقال|قال |سمعت|أخبرنا|حدثنا|ذكره|وثقه|روى عنه|روى عن|توفي|مات)')
def seg(t, rx, mx):
    out = []
    for m in rx.finditer(t):
        s = t[m.end():m.end() + mx]; e = END.search(s, 5); out.append(s[:e.start()] if e else s)
    return ' . '.join(out)
HW = collections.defaultdict(lambda: [set(), set(), []])   # key -> [teacher pairs, student pairs, deaths]
n = 0
for r in csv.DictReader(open(EXT + 'hawramani_narrators.csv', encoding='utf-8', newline='')):
    k = key(tk(r['name_ar']))
    if not k: continue
    t = r['text_ar']; d = None
    try: d = float(r['death_year_ah']) if r['death_year_ah'] else None
    except Exception: pass
    e = HW[k]; e[0] |= pairs(seg(t, TEA, 700)); e[1] |= pairs(seg(t, STU, 900)); e[2].append(d); n += 1
print('hawramani entries', n, 'name keys', len(HW), flush=True)
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
names = dict(c.execute('select id,std_name from narrator'))
def pk(nid): k = key(tk(names.get(nid))); return k[0] + '|' + k[1] if k else None
def pool(y):
    k = key(tk(names.get(y)))
    return HW.get(k) if k else None
def rel(x, y, z):
    py = pool(y); px = pool(x); pz = pool(z); kx, kz, ky = pk(x), pk(z), pk(y); sc = 0; seen = 0
    if py and kx: seen += 1; sc += kx in py[1]
    if py and kz: seen += 1; sc += kz in py[0]
    if px and ky: seen += 1; sc += ky in px[0]
    if pz and ky: seen += 1; sc += ky in pz[1]
    return (sc, seen) if seen else None
P = np.load('labels/parallels.npz'); M = np.load('labels/par_meta.npz'); ids = M['ids']; PA = P['a']; PB = P['b']
hix = {h: i for i, h in enumerate(ids)}; CH = [[] for _ in ids]
for rid, h, nid, pos, sf in c.execute('select rowid,hadith_id,narrator_id,pos,surface from chain_mention where start is not null and coalesce(chain_no,1)=1'):
    i = hix.get(h)
    if i is not None: CH[i].append((pos, rid, nid, sf))
CH = [[(r, n_, s) for _, r, n_, s in sorted(x)] for x in CH]
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
    pr = sorted((ia[n_][0], ib[n_][0]) for n_ in ia if n_ in ib and len(ia[n_]) == 1 and len(ib[n_]) == 1); out = []; lj = -1
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
ms = {int(k): v for k, v in json.load(open('labels/conflict_ms.json')).items()}
cal = collections.Counter(); res = collections.Counter(); out = {}
for r, d in conf.items():
    cands = [d['own']] + [k for k in d['v'] if k != d['own']]
    rl = {y: rel(d['x'], y, d['z']) for y in cands}; fits = {y: namefit(d['sf'], y) for y in cands}
    known = {y: v for y, v in rl.items() if v and v[1] >= 1}
    best = None
    if len(known) >= 2:
        sc = {y: v[0] for y, v in known.items()}; mx = max(sc.values()); top = [y for y, v in sc.items() if v == mx]
        if len(top) == 1 and mx > min(sc.values()): best = top[0]
    truth = [y for y in cands if fits[y] == 1]
    if len(truth) == 1 and all(fits[y] == 0 for y in cands if y != truth[0]):
        cal['name_decided'] += 1; cal['scored'] += int(len(known) >= 2)
        if best: cal['decided'] += 1; cal['ok'] += int(best == truth[0])
        out[r] = {'kind': 'name_decides', 'truth': truth[0], 'own': d['own'], 'h': d['h'], 'best': best, 'sc': {y: v[0] for y, v in known.items()}}
    else:
        res['undecided_by_name'] += 1; res['scored'] += int(len(known) >= 2)
        if best: res['decides'] += 1; res['decides_own_loses'] += int(best != d['own'])
        out[r] = {'kind': 'undecided_by_name', 'own': d['own'], 'h': d['h'], 'best': best, 'sc': {y: v[0] for y, v in known.items()}}
print('CALIBRATION (name-decided slots):', dict(cal), '| accuracy %.1f%%' % (100 * cal['ok'] / max(1, cal['decided'])))
print('UNDECIDED-BY-NAME:', dict(res))
json.dump(out, open('labels/conflict_hw.json', 'w'))
