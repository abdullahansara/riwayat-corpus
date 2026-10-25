from paths import *
import csv, json, re, sqlite3, collections, hashlib, openpyxl, time, sys
csv.field_size_limit(10**9)
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
HM = OUT + ''; D = SRC + 'MIDS_SahihMuslim/'
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nk(s):
    s = str(s).replace('ﷺ', ' صلى الله عليه وسلم '); return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', s).translate(TR))).strip()
def h8(s): return hashlib.md5(s.encode()).digest()[:8]
db = sqlite3.connect(HM + 'hadith_master.db'); c = db.cursor()
con = sqlite3.connect('file:' + SRC + 'HadithKG/hadith-kg.db?mode=ro', uri=True)
# ---------- clean triples: SemanticHadith number <-> MIDS unit (unique text match) <-> hadith-kg hadith (unique text match)
sh_text = {}
with open(SRC + 'SemanticHadithV2/sh_arabic_text.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[0] == 'SM': sh_text[int(x[1])] = nk(x[2])
s2m = json.load(open(SRC + 'SemanticHadithV2/sh_muslim_to_mids.json'))
kf = collections.defaultdict(list); kt = collections.defaultdict(list); kh = collections.defaultdict(list)
for hid, nass in con.execute('select id, nass from hadiths where book_id=2 and nass is not null'):
    s = nk(nass)
    if len(s) >= 40: kf[h8(s)].append(hid); kh[h8(s[:70])].append(hid); kt[h8(s[-70:])].append(hid)
triples = []
for num, s in sh_text.items():
    v = s2m.get(str(num))
    if not v or v[2] != 1 or v[1] not in ('full', 'head+tail'): continue
    m = kf.get(h8(s))
    if not m:
        ts = set(kt.get(h8(s[-70:]), [])); m = [x for x in kh.get(h8(s[:70]), []) if x in ts]
    if len(set(m)) == 1: triples.append((num, v[0], m[0]))
log('clean three-way triples (SemanticHadith / MIDS / hadith-kg):', len(triples))
# ---------- MIDS persons per unit
def rows(fn):
    ws = openpyxl.load_workbook(D + fn, read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); h = next(it)
    for r in it:
        if r and r[0] is not None: yield dict(zip(h, r))
mp = collections.defaultdict(set)
for r in rows('3_Hadith_SahihMuslim_Isnad=Edges for Graph.xlsx'):
    h = int(r['HadithNo']); mp[h].add(str(r['sourceNarratorID'])); mp[h].add(str(r['targetNarratorID']))
kg2h = {}
for hid, src in c.execute("select id, source_ids from hadith where tradition='sunni'"):
    k = json.loads(src).get('kg')
    if k: kg2h[k] = hid
def src_map(source): return dict(c.execute('select source_id, narrator_id from narrator_source_id where source=?', (source,)).fetchall())
def validate(label):
    mm = src_map('mids'); cat = collections.Counter(); pn = pd = rn = rd = tot = 0
    for num, unit, kid in triples:
        hid = kg2h.get(kid)
        if not hid: continue
        O = {r[0] for r in c.execute('select narrator_id from chain_mention where hadith_id=? and narrator_id is not null', (hid,))}
        M = {mm.get(i) for i in mp.get(unit, set())}; M.discard(None)
        if not O or not M: continue
        tot += 1; I = O & M; pn += len(I); pd += len(O); rn += len(I); rd += len(M)
        cat['exact same set' if O == M else 'ours subset of MIDS (MIDS expands referential isnads)' if O < M else 'ours has extra' if M < O else 'both differ'] += 1
    log(f'[{label}] clean units compared: {tot} | narrator-id precision {pn/pd:.3f} | recall {rn/rd:.3f}')
    for k, n in cat.most_common(): print(f'      {n:5d} {n/tot:6.1%}  {k}')
validate('BEFORE merging duplicates')
# ---------- propose merges: MIDS-side id vs hadith-side id that co-occur on the same clean hadith
mm = src_map('mids'); C = collections.Counter(); nm = collections.Counter(); nh = collections.Counter()
for num, unit, kid in triples:
    hid = kg2h.get(kid)
    if not hid: continue
    O = {r[0] for r in c.execute('select narrator_id from chain_mention where hadith_id=? and narrator_id is not null', (hid,))}
    M = {mm.get(i) for i in mp.get(unit, set())}; M.discard(None)
    for a in M: nm[a] += 1
    for b in O: nh[b] += 1
    for a in M:
        for b in O: C[(a, b)] += 1
bm = {}; bh = {}
for (a, b), n in C.items():
    j = n / (nm[a] + nh[b] - n)
    if a not in bm or j > bm[a][1]: bm[a] = (b, j, n)
    if b not in bh or j > bh[b][1]: bh[b] = (a, j, n)
srcs = collections.defaultdict(set)
for nid, s in c.execute('select narrator_id, source from narrator_source_id'): srcs[nid].add(s)
merges = {}
for a, (b, j, n) in bm.items():
    if a == b or bh.get(b, (None,))[0] != a or j < 0.5 or n < 2: continue
    if srcs[a] & srcs[b]: continue                                   # never merge two ids that share a source (they are different people there)
    merges[a] = (b, j, n)
log('proposed duplicate merges (MIDS-only id -> id used in the chains):', len(merges), '| examples:', [(a, b, round(j, 2), n) for a, (b, j, n) in list(merges.items())[:4]])
# ---------- apply merges with an audit table
c.executescript('CREATE TABLE IF NOT EXISTS narrator_merge(old_id TEXT PRIMARY KEY, new_id TEXT, reason TEXT, jaccard REAL, n_hadith INT);')
for a, (b, j, n) in merges.items():
    c.execute('INSERT OR REPLACE INTO narrator_merge VALUES(?,?,?,?,?)', (a, b, 'same position set on clean 3-way aligned Muslim hadith (MIDS vs chains)', j, n))
    c.execute('UPDATE chain_mention SET narrator_id=? WHERE narrator_id=?', (b, a))
    c.execute('UPDATE narrator_name SET narrator_id=? WHERE narrator_id=?', (b, a))
    c.execute('UPDATE narrator_source_id SET narrator_id=? WHERE narrator_id=?', (b, a))
    old = c.execute('select death_year, birth_year, tabaqa, city from narrator where id=?', (a,)).fetchone()
    if old:
        for col, val in zip(('death_year', 'birth_year', 'tabaqa', 'city'), old):
            if val is not None: c.execute(f'UPDATE narrator SET {col}=? WHERE id=? AND {col} IS NULL', (val, b))
    c.execute('UPDATE narrator SET n_sources=(select count(distinct source) from narrator_source_id where narrator_id=?) WHERE id=?', (b, b))
    c.execute('DELETE FROM narrator WHERE id=?', (a,))
db.commit()
# reference_chain stores id lists as JSON
rm = {a: b for a, (b, j, n) in merges.items()}; fixed = 0
for rid, ids in c.execute('select rowid, narrator_ids from reference_chain').fetchall():
    L = json.loads(ids)
    if any(x in rm for x in L): c.execute('UPDATE reference_chain SET narrator_ids=? WHERE rowid=?', (json.dumps([rm.get(x, x) for x in L]), rid)); fixed += 1
db.commit(); log('reference chains updated:', fixed)
validate('AFTER merging duplicates')
log('narrators now:', c.execute('select count(*) from narrator').fetchone()[0])
