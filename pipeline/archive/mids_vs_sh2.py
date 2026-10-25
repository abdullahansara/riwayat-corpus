import json, csv, re, collections, openpyxl, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
HON = re.compile(r'رضي الله (?:تعالى )?عن[هم]?[هما]?|\(|\)|-|ﷺ|عليه السلام')
KEEPW = {'وهب', 'وكيع', 'وردان', 'وائل', 'وهيب', 'واقد', 'وبره', 'وسيم'}
import functools
@functools.lru_cache(maxsize=None)
def ntok_c(s): return tuple(ntok_raw(s))
def ntok_raw(s):
    s = HON.sub(' ', str(s or '')); s = DIAC.sub('', s).translate(TR); s = re.sub(r'[^\u0621-\u064A ]', ' ', s); out = []
    for w in s.split():
        if len(w) > 3 and w[0] == 'و' and w not in KEEPW: w = w[1:]
        if w in ('ابن', 'بنا', 'ابنا'): w = 'بن'
        elif w in ('ابي', 'ابا', 'ابوه'): w = 'ابو'
        if len(w) > 3 and w.endswith('ا') and not w.endswith(('ابا', 'يا')): w = w[:-1]
        out.append(w)
    return out
GEN = {'بن', 'ابو', 'ام', 'عبد', 'الله', 'محمد', 'بنت', 'صاحب', 'بو'}
def ntok(s): return list(ntok_c(str(s)))
@functools.lru_cache(maxsize=None)
def compat(a, b):
    ta, tb = set(ntok(a)), set(ntok(b))
    if not ta or not tb: return False
    inter = ta & tb; dist = inter - GEN
    if dist: return (len(inter) >= 2) or (len(ta) <= 2 and ta <= tb) or (len(tb) <= 2 and tb <= ta)
    return len(inter) >= 3
D = '<ROOT>/MIDS_SahihMuslim/'
nodes = json.load(open(D + 'mids_nodes.json', encoding='utf-8'))
def rows(fn):
    ws = openpyxl.load_workbook(D + fn, read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); h = next(it)
    for r in it:
        if r and r[0] is not None: yield dict(zip(h, r))
edges = collections.defaultdict(list)
for r in rows('3_Hadith_SahihMuslim_Isnad=Edges for Graph.xlsx'):
    m = re.search(r'-i(\d+)$', str(r['intractionLabel'])); edges[(int(r['HadithNo']), int(r['SanadNo']))].append((int(m.group(1)) if m else 0, str(r['sourceNarratorID']), str(r['targetNarratorID'])))
mids = collections.defaultdict(list)       # hadith -> list of sanads (compiler-first order, names)
for (h, s), L in sorted(edges.items()):
    L.sort(); ids = [L[0][1]] + [t for _, _, t in L]
    mids[h].append([nodes.get(i, ['?'])[0] for i in reversed(ids)])      # MIDS lists Prophet-side first -> reverse
sh = {}
with open('<ROOT>/SemanticHadithV2/sh_chains.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[1] == 'SM': sh[int(x[2])] = json.loads(x[4])
log('MIDS hadith', len(mids), '| SH Muslim hadith', len(sh))

_pc = {}
def persons(h):
    if h in _pc: return _pc[h]
    seen=[]; 
    for s_ in mids.get(h, []):
        for n in s_:
            if not any(compat(n, m) and compat(m, n) for m in seen): seen.append(n)
    return seen
REL = re.compile(r'^(?:أبيه|أبي|أبوه|جده)')
def score(h, k):
    c = sh.get(k)
    if not c or None in c: return None
    P = persons(h)
    if not P: return None
    a = sum(any(compat(x, p) for p in P) for x in c) / len(c)
    b = sum(any(compat(x, p) for x in c) for p in P) / len(P)
    return a, b
res = collections.Counter(); blk = collections.defaultdict(lambda: [0, 0]); low = []
for h in sorted(mids):
    sc_ = score(h, h)
    if sc_ is None: continue
    a, b = sc_; blk[(h // 1000) * 1000][1] += 1
    if a == 1 and b == 1: res['perfect: every SH narrator in MIDS and every MIDS narrator in SH'] += 1; blk[(h // 1000) * 1000][0] += 1
    elif a >= .8 and b >= .8: res['near (both >= 80%)'] += 1
    elif a >= .5 and b >= .5: res['partial (both >= 50%)'] += 1
    else: res['weak (<50% somewhere)'] += 1; low.append(h)
n = sum(res.values()); log(f'SET-LEVEL AGREEMENT at same hadith number ({n} hadith):')
for k, v in res.most_common(): print(f'   {v:5d}  {v/n:5.1%}  {k}')
log('perfect agreement by MIDS number block:', {f'{b//1000}k': f'{v[0]/v[1]:.0%}' for b, v in sorted(blk.items())})
# is the weak group a numbering drift?  try nearby SH numbers
fixed = collections.Counter(); still = 0
for h in low[:400]:
    best = None
    for d in range(-15, 16):
        sc_ = score(h, h + d)
        if sc_ and min(sc_) >= .8: best = d; break
    if best is None: still += 1
    else: fixed[best] += 1
log('weak hadith that DO match a nearby SH number (offset: count):', dict(fixed.most_common(10)), '| still unmatched within +-15 (of the 400 sampled):', still)
