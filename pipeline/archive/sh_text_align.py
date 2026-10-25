import re, csv, json, sqlite3, hashlib, collections, time, openpyxl
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
BS = chr(92)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nk(s):
    s = str(s).replace('ﷺ', ' صلى الله عليه وسلم ')
    s = DIAC.sub('', s).translate(TR); s = KEEP.sub(' ', s); return re.sub(r'\s+', ' ', s).strip()
def h8(s): return hashlib.md5(s.encode()).digest()[:8]
# ---------- 1. SemanticHadith: Arabic text per hadith
def lits(seg):
    out = []; i = 0; n = len(seg)
    while i < n:
        if seg[i] == '"':
            j = i + 1; buf = []
            while j < n and seg[j] != '"':
                if seg[j] == chr(92) and j + 1 < n: buf.append(seg[j + 1]); j += 2
                else: buf.append(seg[j]); j += 1
            out.append(''.join(buf)); i = j + 1
        else: i += 1
    return out
sh = {}
blk = []
def flush(b):
    if not b: return
    txt = ''.join(b); m = re.match(r'\s*:([A-Za-z]+)-HD(\d+)\s+rdf:type\s+owl:NamedIndividual\s*,\s*:Hadith\s*;', txt)
    if not m: return
    i = txt.find(':fullHadithText'); j = txt.find(' ;', i) if i >= 0 else -1
    seg = txt[i:] if i >= 0 else ''
    cands = [t for t in lits(seg) if len(re.findall('[\u064B-\u0652]', t)) > 5]
    if cands: sh[(m.group(1), int(m.group(2)))] = cands[0]
with open('<ROOT>/SemanticHadithV2/ttl/SemanticHadithKGV2.ttl', encoding='utf-8') as f:
    for line in f:
        if line.startswith('###'): flush(blk); blk = []
        else: blk.append(line)
flush(blk)
log('SH hadith with Arabic text:', len(sh), collections.Counter(k[0] for k in sh))
with open('<ROOT>/SemanticHadithV2/sh_arabic_text.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['collection', 'number', 'arabic_text'])
    for (c, n), t in sorted(sh.items()): w.writerow([c, n, t])
# ---------- 2. MIDS texts
D = '<ROOT>/MIDS_SahihMuslim/'
ws = openpyxl.load_workbook(D + '1_Hadith_SahihMuslim_HadithContent.xlsx', read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); hdr = next(it)
mids = {}
for r in it:
    d = dict(zip(hdr, r))
    if d['HadithNo'] is not None: mids[int(d['HadithNo'])] = nk(d['HadithText_GhairMushakkal'] or '')
mfull = collections.defaultdict(list); mhead = collections.defaultdict(list); mtail = collections.defaultdict(list)
for h, s in mids.items():
    if len(s) < 40: continue
    mfull[h8(s)].append(h); mhead[h8(s[:70])].append(h); mtail[h8(s[-70:])].append(h)
log('MIDS keyed', len(mids))
# ---------- 3. SM  <->  MIDS by text
stat = collections.Counter(); pairs = {}
for (c, n), t in sh.items():
    if c != 'SM': continue
    s = nk(t)
    if len(s) < 40: stat['short'] += 1; continue
    m = mfull.get(h8(s)); how = 'full'
    if not m:
        m = [x for x in mhead.get(h8(s[:70]), []) if x in set(mtail.get(h8(s[-70:]), []))]; how = 'head+tail'
    if not m: m = mhead.get(h8(s[:70])); how = 'head_only'
    if not m: stat['no_match'] += 1; continue
    stat[how + ('_unique' if len(m) == 1 else '_ambiguous')] += 1; pairs[n] = (m[0], how, len(m))
tot = sum(stat.values()); log(f'SemanticHadith Muslim ({tot}) -> MIDS by text:')
for k, v in stat.most_common(): print(f'   {v:5d} {v/tot:6.1%} {k}')
off = collections.Counter(pairs[n][0] - n for n in pairs if pairs[n][2] == 1)
log('number difference (MIDS no. minus SH no.) for unique matches, most common:', off.most_common(8))
json.dump({str(n): v for n, v in pairs.items()}, open('<ROOT>/SemanticHadithV2/sh_muslim_to_mids.json', 'w'))
# ---------- 4. all six books  <->  hadith-kg by text
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True)
kgid = {'SB': 1, 'SM': 2, 'SD': 4, 'SN': 5, 'IM': 6, 'JT': 3}
for col, bid in kgid.items():
    kf = collections.defaultdict(list); kh = collections.defaultdict(list)
    for hid, nass in con.execute('select id, nass from hadiths where book_id=? and nass is not null', (bid,)):
        s = nk(nass)
        if len(s) >= 40: kf[h8(s)].append(hid); kh[h8(s[:70])].append(hid)
    n = full_ = head_ = none = 0
    for (c, num), t in sh.items():
        if c != col: continue
        s = nk(t)
        if len(s) < 40: continue
        n += 1
        if kf.get(h8(s)): full_ += 1
        elif kh.get(h8(s[:70])): head_ += 1
        else: none += 1
    log(f'{col}: SH hadith {n} | kg full-text match {full_} ({full_/n:.1%}) | head-only {head_} ({head_/n:.1%}) | none {none} ({none/n:.1%})')
