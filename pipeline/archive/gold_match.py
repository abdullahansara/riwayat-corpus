import json, sqlite3, re, csv, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
HON = re.compile(r'رضي الله (?:تعالى )?عن[هم]?[هما]?|\(|\)|-|ﷺ|عليه السلام')
def ntok(s):
    s = HON.sub(' ', str(s or '')); s = DIAC.sub('', s).translate(TR); s = re.sub(r'[^\u0621-\u064A ]', ' ', s)
    out = []
    for w in s.split():
        if w in ('ابن', 'بنا', 'ابنا'): w = 'بن'
        elif w in ('ابي', 'ابا', 'ابوه'): w = 'ابو'
        if len(w) > 3 and w[0] == 'و' and w not in ('وهب', 'وكيع', 'وردان', 'وائل', 'وهيب', 'واقد', 'وبره', 'وسيم'): w = w[1:]
        if len(w) > 3 and w.endswith('ا') and not w.endswith(('ابا', 'يا')): w = w[:-1]
        out.append(w)
    return out
GEN = {'بن', 'ابو', 'ابي', 'ام', 'عبد', 'الله', 'محمد', 'بنت', 'ابن', 'صاحب', 'بو', 'ابا'}
def compat(a, b):
    ta, tb = set(ntok(a)), set(ntok(b))
    if not ta or not tb: return False
    inter = ta & tb; dist = inter - GEN
    if dist: return len(dist) >= 1 and len(inter) >= 2 or (len(ta) <= 2 and ta <= tb) or (len(tb) <= 2 and tb <= ta)
    return len(inter) >= 3 or ta <= tb or tb <= ta
REL = re.compile(r'^(?:أبيه|أبي|أبوه|جده|أبيها|أباه|أخيه|عمه)')
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True); cur = con.cursor()
# =============== A. SAHIH MUSLIM: MIDS vs kg (exact-region units)
D = '<ROOT>/MIDS_SahihMuslim/'
al = json.load(open(D + 'mids_to_kg_v2.json', encoding='utf-8')); nodes = json.load(open(D + 'mids_nodes.json', encoding='utf-8'))
res = collections.Counter(); bad = []
for h, r in al.items():
    if not r['exact_region']: res['(skipped: head-only alignment, region unreliable)'] += 1; continue
    nass = cur.execute('select nass from hadiths where id=?', (r['kg'],)).fetchone()[0]
    surf = [nass[a:b] for a, b in r['spans']]; surf_nr = [s for s in surf if not REL.match(s.strip())]
    persons = sorted({i for s in r['mids_sanads'] for i in s}); pn = [nodes.get(i, ['?'])[0] for i in persons]
    missing = [n for n in pn if not any(compat(n, s) for s in surf_nr)]
    extra = [s for s in surf_nr if not any(compat(n, s) for n in pn)]
    if not missing and not extra: res['consistent: every MIDS narrator found, no extra span'] += 1
    elif missing and not extra: res['kg misses a MIDS narrator'] += 1
    elif extra and not missing: res['kg has an extra span not in MIDS'] += 1
    else: res['both missing and extra'] += 1
    if (missing or extra) and len(bad) < 6: bad.append((h, [m[:22] for m in missing][:3], [e[:22] for e in extra][:3]))
n = sum(v for k, v in res.items() if not k.startswith('(skipped'))
log(f'MUSLIM exact-region units compared: {n}')
for k, v in res.most_common(): print(f'   {v:5d}  {k}' + (f'  ({v/n:.1%})' if not k.startswith('(skipped') else ''))
print('   examples (hadith, MIDS narrators not found, kg spans not in MIDS):'); [print('     ', b) for b in bad]
# =============== B. SIX BOOKS: SemanticHadith vs kg chains
sh = []
with open('<ROOT>/SemanticHadithV2/sh_chains.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r: sh.append((x[1], int(x[2]), json.loads(x[4])))
kgid = {'SB': 1, 'SM': 2, 'SD': 4, 'SN': 5, 'IM': 6, 'JT': 3}
def key(names): return tuple((ntok(n) or ['?'])[0] for n in names)
out = {}
for col, bid in kgid.items():
    kgc = collections.defaultdict(list); n_kg = 0
    rowsx = con.execute('select s.id, s.hadith_id from sanads s join hadiths h on h.id=s.hadith_id where h.book_id=?', (bid,)).fetchall()
    allsr = collections.defaultdict(list)
    for sid_, pos, nm in con.execute('select sr.sanad_id, sr.pos, r.name from sanad_rawis sr join rawis r on r.id=sr.rawi_id where sr.sanad_id in (select s.id from sanads s join hadiths h on h.id=s.hadith_id where h.book_id=?) and sr.pos>0', (bid,)).fetchall(): allsr[sid_].append((pos, nm))
    for sid, hid in rowsx:
        names = [nm for _, nm in sorted(allsr.get(sid, []))]
        if names: kgc[key(names)].append((hid, names)); n_kg += 1
    tot = ok = amb = 0
    for c, num, names in sh:
        if c != col or not names or None in names: continue
        tot += 1; cand = [(h, kn) for h, kn in kgc.get(key(names), []) if len(kn) == len(names) and all(compat(a, b) for a, b in zip(names, kn))]
        ok += bool(cand); amb += len(cand) > 1
    out[col] = (tot, ok, amb, n_kg)
    log(f'{col}: SH chains {tot} | with a compatible kg chain {ok} ({ok/max(tot,1):.1%}) | of those ambiguous (>1 kg match) {amb} | kg chains {n_kg}')
