import json, csv, re, collections, openpyxl, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
HON = re.compile(r'رضي الله (?:تعالى )?عن[هم]?[هما]?|\(|\)|-|ﷺ|عليه السلام')
KEEPW = {'وهب', 'وكيع', 'وردان', 'وائل', 'وهيب', 'واقد', 'وبره', 'وسيم'}
def ntok(s):
    s = HON.sub(' ', str(s or '')); s = DIAC.sub('', s).translate(TR); s = re.sub(r'[^\u0621-\u064A ]', ' ', s); out = []
    for w in s.split():
        if len(w) > 3 and w[0] == 'و' and w not in KEEPW: w = w[1:]
        if w in ('ابن', 'بنا', 'ابنا'): w = 'بن'
        elif w in ('ابي', 'ابا', 'ابوه'): w = 'ابو'
        if len(w) > 3 and w.endswith('ا') and not w.endswith(('ابا', 'يا')): w = w[:-1]
        out.append(w)
    return out
GEN = {'بن', 'ابو', 'ام', 'عبد', 'الله', 'محمد', 'بنت', 'صاحب', 'بو'}
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
def same(a, b): return len(a) == len(b) and all(compat(x, y) for x, y in zip(a, b))
def match_at(h, k):
    c = sh.get(k)
    if not c or None in c: return None
    return any(same(c, s) for s in mids.get(h, []))
tested = ok = 0; unm = []
for h in sorted(mids):
    m = match_at(h, h)
    if m is None: continue
    tested += 1; ok += m
    if not m: unm.append(h)
log(f'SAME NUMBER: SH chain equals one MIDS isnad for {ok}/{tested} hadith ({ok/tested:.1%})')
# systematic shift?  for unmatched, search nearby numbers
shift = collections.Counter(); notfound = []
for h in unm:
    f = None
    for d in sorted(range(-12, 13), key=abs):
        if d and match_at(h, h + d): f = d; break
    (shift.__setitem__(f, shift[f] + 1) if f is not None else notfound.append(h))
log('unmatched hadith whose chain matches a nearby SH number (shift: count):', dict(shift.most_common(8)), '| no match within ±12:', len(notfound))
# agreement by hadith-number region
bins = collections.defaultdict(lambda: [0, 0])
for h in sorted(mids):
    m = match_at(h, h)
    if m is None: continue
    b = (h // 1000) * 1000; bins[b][1] += 1; bins[b][0] += m
log('agreement by MIDS hadith number block:', {f'{b}-{b+999}': f'{v[0]/v[1]:.0%}' for b, v in sorted(bins.items())})
# how do mismatching chains differ?
cat = collections.Counter(); ex = []
for h in unm:
    c = sh[h]; best = None
    for s in mids[h]:
        if best is None or abs(len(s) - len(c)) < abs(len(best) - len(c)): best = s
    if best is None: cat['no MIDS sanad']+=1; continue
    if len(best) != len(c): cat['different chain length']+=1
    else: cat['same length, some narrator differs']+=1
    if len(ex) < 4: ex.append((h, [x[:18] for x in c], [x[:18] for x in best]))
log('why unmatched (at same number):', dict(cat))
for e in ex: print('  #', e[0], '\n    SH  :', ' ; '.join(e[1]), '\n    MIDS:', ' ; '.join(e[2]))
