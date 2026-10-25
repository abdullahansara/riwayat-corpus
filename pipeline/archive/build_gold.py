import csv, json, re, sqlite3, collections, hashlib, time, functools
csv.field_size_limit(10**9)
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nk(s):
    s = str(s).replace('ﷺ', ' صلى الله عليه وسلم ')
    s = DIAC.sub('', s).translate(TR); s = KEEP.sub(' ', s); return re.sub(r'\s+', ' ', s).strip()
def h8(s): return hashlib.md5(s.encode()).digest()[:8]
HON = re.compile('رضي الله (?:تعالى )?عن[هم]?[هما]?|ﷺ|عليه السلام'); KEEPW = {'وهب', 'وكيع', 'وردان', 'وائل', 'وهيب', 'واقد', 'وبره', 'وسيم'}
@functools.lru_cache(maxsize=None)
def ntok(s):
    s = HON.sub(' ', str(s or '')); s = DIAC.sub('', s).translate(TR); s = KEEP.sub(' ', s); out = []
    for w in s.split():
        if len(w) > 3 and w[0] == 'و' and w not in KEEPW: w = w[1:]
        if w in ('ابن', 'بنا', 'ابنا'): w = 'بن'
        elif w in ('ابي', 'ابا', 'ابوه'): w = 'ابو'
        if len(w) > 3 and w.endswith('ا') and not w.endswith(('ابا', 'يا')): w = w[:-1]
        out.append(w)
    return tuple(out)
GEN = {'بن', 'ابو', 'ام', 'عبد', 'الله', 'محمد', 'بنت', 'صاحب', 'بو'}
RELW = {'ابيه', 'ابو', 'جده', 'ابوه', 'اباه', 'ابيها'}
@functools.lru_cache(maxsize=None)
def compat(a, b):
    ta, tb = set(ntok(a)), set(ntok(b))
    if not ta or not tb: return False
    if (ta & RELW) and len(ta) == 1 or (tb & RELW) and len(tb) == 1: return True       # relative terms: accept
    inter = ta & tb; dist = inter - GEN
    if dist: return (len(inter) >= 2) or (len(ta) <= 2 and ta <= tb) or (len(tb) <= 2 and tb <= ta)
    return len(inter) >= 3
# ---- SemanticHadith text + narrators
txt = {}; names = {}
with open('<ROOT>/SemanticHadithV2/sh_arabic_text.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r: txt[(x[0], int(x[1]))] = x[2]
with open('<ROOT>/SemanticHadithV2/sh_chains.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r: names[(x[1], int(x[2]))] = json.loads(x[4])
log('SH text', len(txt), 'chains', len(names))
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True)
kgid = {'SB': 1, 'SM': 2, 'SD': 4, 'SN': 5, 'IM': 6, 'JT': 3}
out = open('<ROOT>/HadithKG/gold_sh_validated.jsonl', 'w', encoding='utf-8'); pool = open('<ROOT>/HadithKG/review_pool_sh.jsonl', 'w', encoding='utf-8')
summary = {}
for col, bid in kgid.items():
    kf = collections.defaultdict(list); kh = collections.defaultdict(list); kt = collections.defaultdict(list)
    for hid, nass in con.execute('select id, nass from hadiths where book_id=? and nass is not null', (bid,)).fetchall():
        s = nk(nass)
        if len(s) >= 40: kf[h8(s)].append(hid); kh[h8(s[:70])].append(hid); kt[h8(s[-70:])].append(hid)
    pairs = {}
    for (c, num), t in txt.items():
        if c != col: continue
        s = nk(t)
        if len(s) < 40: continue
        m = kf.get(h8(s)); how = 'full'
        if not m:
            ts = set(kt.get(h8(s[-70:]), [])); m = [x for x in kh.get(h8(s[:70]), []) if x in ts]; how = 'head+tail'
        if m and len(set(m)) == 1: pairs[num] = (m[0], how)
    ids = sorted({k for k, _ in pairs.values()}); H = {}; M = collections.defaultdict(list)
    for i in range(0, len(ids), 3000):
        ch = ids[i:i + 3000]; q = ','.join('?' * len(ch))
        for h, t, ms in con.execute(f'select id, nass, matn_start from hadiths where id in ({q})', ch): H[h] = (t, ms)
        for h, a, b in con.execute(f'select hadith_id, start, end from hadith_rawis where hadith_id in ({q}) order by hadith_id, seq', ch): M[h].append((a, b))
    st = collections.Counter()
    for num, (kid, how) in pairs.items():
        nm = names.get((col, num)); nass, ms = H[kid]; sp = M.get(kid, [])
        if not nm or None in nm: st['sh_chain_incomplete'] += 1; continue
        if not sp or ms is None: st['kg_no_spans'] += 1; continue
        last_end = max(e for _, e in sp)
        if ms < last_end or ms - last_end > 400: st['kg_boundary_odd'] += 1; continue
        agree = sum(compat(a, nass[x:y]) for a, (x, y) in zip(nm, sp)) / len(sp) if len(nm) == len(sp) else 0.0
        rec = {'col': col, 'num': num, 'kid': kid, 'match': how, 'text': nass[:min(len(nass), ms + 80)], 'spans': sp, 'matn_start': ms, 'sh_n': len(nm), 'agree': round(agree, 3)}
        if len(nm) == len(sp) and agree >= 0.6: st['validated'] += 1; out.write(json.dumps(rec, ensure_ascii=False) + '\n')
        elif len(nm) == len(sp): st['count_equal_names_disagree'] += 1; pool.write(json.dumps({**rec, 'sh_names': nm}, ensure_ascii=False) + '\n')
        else: st['count_differs'] += 1; pool.write(json.dumps({**rec, 'sh_names': nm}, ensure_ascii=False) + '\n')
    n = sum(st.values()); summary[col] = dict(st)
    log(f'{col}: SH hadith {sum(1 for (c, _) in txt if c == col)} | aligned to kg {len(pairs)} | ' + ' | '.join(f'{k} {v}' for k, v in st.most_common()))
out.close(); pool.close()
tv = sum(s.get('validated', 0) for s in summary.values()); log('TOTAL validated gold hadith:', tv)
