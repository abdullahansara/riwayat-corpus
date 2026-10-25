import openpyxl, sqlite3, re, hashlib, json, collections, time, csv
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
D = '<ROOT>/MIDS_SahihMuslim/'
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile(r'[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nk(s):
    s = str(s).replace('ﷺ', ' صلى الله عليه وسلم ')
    s = DIAC.sub('', s).translate(TR); s = KEEP.sub(' ', s); return re.sub(r'\s+', ' ', s).strip()
def h8(s): return hashlib.md5(s.encode()).digest()[:8]
def rows(fn):
    ws = openpyxl.load_workbook(D + fn, read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); h = next(it)
    for r in it:
        if r and r[0] is not None: yield dict(zip(h, r))
# ---- MIDS content, narrators, edges
mids = {}
for r in rows('1_Hadith_SahihMuslim_HadithContent.xlsx'):
    mids[int(r['HadithNo'])] = {'text': nk(r['HadithText_GhairMushakkal'] or ''), 'sanads': int(r['SanadCount'] or 0), 'ar': r['HadithText_GhairMushakkal']}
nodes = {}
for r in rows('2_Hadith_SahihMuslim_Narrators=Nodes for Graph.xlsx'):
    nodes[str(r['NarratorID_Mapped'])] = (r['NarratorNameAr-Mapped'] or r['NarratorNameAr'], r['NarratorGeneration'])
edges = collections.defaultdict(list)
for r in rows('3_Hadith_SahihMuslim_Isnad=Edges for Graph.xlsx'):
    m = re.search(r'-i(\d+)$', str(r['intractionLabel'])); step = int(m.group(1)) if m else 0
    edges[(int(r['HadithNo']), int(r['SanadNo']))].append((step, str(r['sourceNarratorID']), str(r['targetNarratorID'])))
sanad_lists = collections.defaultdict(list)       # hadith -> [ [ids...] per sanad ]
for (h, s), L in sorted(edges.items()):
    L.sort(); ids = [L[0][1]] + [t for _, _, t in L]
    sanad_lists[h].append(ids)
log('MIDS hadith', len(mids), 'nodes', len(nodes), 'hadith with edges', len(sanad_lists))
# ---- hadith-kg Muslim (book 2) keys
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True); cur = con.cursor()
kfull = collections.defaultdict(list); khead = collections.defaultdict(list); ktext = {}
for hid, nass in cur.execute('select id, nass from hadiths where book_id=2 and nass is not null'):
    s = nk(nass); ktext[hid] = s; kfull[h8(s)].append(hid); khead[h8(s[:70])].append(hid)
log('kg Muslim hadith', len(ktext))
al = {}; stat = collections.Counter()
for h, d in mids.items():
    s = d['text']
    if len(s) < 30: stat['too_short'] += 1; continue
    c = kfull.get(h8(s))
    if c: al[h] = (c[0], 'full'); stat['full'] += 1; continue
    c = khead.get(h8(s[:70]))
    if c and len(c) == 1: al[h] = (c[0], 'head'); stat['head'] += 1; continue
    stat['none'] += 1
log('alignment MIDS->kg Muslim', dict(stat), 'aligned', len(al), 'of', len(mids))
# how many MIDS hadith map to the same kg hadith (kg unit larger?)
inv = collections.Counter(k for k, _ in al.values()); log('distinct kg hadith matched', len(inv), '| kg hadith matched by >1 MIDS hadith:', sum(1 for v in inv.values() if v > 1))
# compare chain structure
cmp = collections.Counter(); ex = []
for h, (kid, mt) in al.items():
    sp = cur.execute('select count(*) from hadith_rawis where hadith_id=?', (kid,)).fetchone()[0]
    sl = [len(x) for x in sanad_lists.get(h, [])]
    if not sl: cmp['mids_no_sanads'] += 1; continue
    if sp == sum(sl): cmp['kg_mentions == sum of MIDS narrators over all sanads'] += 1
    elif sp == max(sl): cmp['kg_mentions == longest MIDS sanad'] += 1
    elif sp == sl[0]: cmp['kg_mentions == first MIDS sanad'] += 1
    else:
        cmp['other'] += 1
        if len(ex) < 5: ex.append((h, kid, sp, sl))
log('chain-count comparison:', dict(cmp)); print('examples of other:', ex)
print('MIDS sanads per hadith:', sorted(collections.Counter(min(len(v), 8) for v in sanad_lists.values()).items()))
json.dump({str(h): {'kg': k, 'type': t, 'sanads': sanad_lists.get(h, [])} for h, (k, t) in al.items()}, open(D + 'mids_to_kg.json', 'w'))
json.dump({k: v for k, v in nodes.items()}, open(D + 'mids_nodes.json', 'w'), ensure_ascii=False)
