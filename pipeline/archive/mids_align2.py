import openpyxl, sqlite3, re, json, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
D = '<ROOT>/MIDS_SahihMuslim/'
DIAC = set('\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0670\u0640\u0653\u0654\u0655\u200f\u200e')
TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nk_map(s):
    """normalised text + for each normalised char its index in the original string"""
    s = s.replace('ﷺ', ' صلى الله عليه وسلم ')   # NB: changes length; handled by mapping the replacement to the symbol position
    out = []; idx = []; prev_space = True
    for i, ch in enumerate(s):
        if ch in DIAC: continue
        ch = ch.translate(TR) if ch in 'أإآٱىةؤئ' else ch
        if '\u0621' <= ch <= '\u064A': out.append(ch); idx.append(i); prev_space = False
        elif not prev_space: out.append(' '); idx.append(i); prev_space = True
    while out and out[-1] == ' ': out.pop(); idx.pop()
    return ''.join(out), idx
def nk(s): return nk_map(str(s))[0]
def rows(fn):
    ws = openpyxl.load_workbook(D + fn, read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); h = next(it)
    for r in it:
        if r and r[0] is not None: yield dict(zip(h, r))
mids = {}
for r in rows('1_Hadith_SahihMuslim_HadithContent.xlsx'): mids[int(r['HadithNo'])] = nk(r['HadithText_GhairMushakkal'] or '')
edges = collections.defaultdict(list)
for r in rows('3_Hadith_SahihMuslim_Isnad=Edges for Graph.xlsx'):
    m = re.search(r'-i(\d+)$', str(r['intractionLabel'])); edges[(int(r['HadithNo']), int(r['SanadNo']))].append((int(m.group(1)) if m else 0, str(r['sourceNarratorID']), str(r['targetNarratorID'])))
sanads = collections.defaultdict(list)
for (h, s), L in sorted(edges.items()):
    L.sort(); sanads[h].append([L[0][1]] + [t for _, _, t in L])
log('MIDS', len(mids))
# ---- hadith-kg Muslim text (original offsets must be preserved -> map)
import sqlite3
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True); cur = con.cursor()
kg = {}      # id -> (nass, norm, idx, spans, matn_start)
M = collections.defaultdict(list)
for hid, a, b in cur.execute('select hadith_id, start, end from hadith_rawis where hadith_id in (select id from hadiths where book_id=2) order by hadith_id, seq'): M[hid].append((a, b))
for hid, nass, ms in cur.execute('select id, nass, matn_start from hadiths where book_id=2 and nass is not null'):
    n, ix = nk_map(nass); kg[hid] = (nass, n, ix, M.get(hid, []), ms)
log('kg Muslim', len(kg))
# index: every 12-gram start? simpler: for each MIDS unit search head (50 chars) via 'in' over kg texts
result = {}; stat = collections.Counter(); order = sorted(kg)
for h, t in mids.items():
    if len(t) < 25: stat['too_short'] += 1; continue
    head = t[:min(50, len(t))]; found = None
    for kid in order:
        n = kg[kid][1]; p = n.find(head)
        if p >= 0:
            found = (kid, p); break
    if found:
        kid, p = found; nass, n, ix, sp, ms = kg[kid]
        end_n = p + len(t); inside = n[p:end_n] == t
        if not inside:                          # MIDS unit longer than the kg text or differs after the head
            ok = n[p:p + len(t)] ; stat['head_found_but_differs'] += 1
        a0 = ix[p]; a1 = ix[min(end_n, len(ix)) - 1] + 1
        sps = [(a, b) for a, b in sp if a >= a0 and b <= a1]
        result[h] = {'kg': kid, 'a0': a0, 'a1': a1, 'spans': sps, 'matn_start': ms, 'exact_region': bool(inside)}
        stat['aligned_exact_region' if inside else 'aligned_head_only'] += 1
    else: stat['not_found'] += 1
log('alignment by containment:', dict(stat), '| aligned', len(result), 'of', len(mids))
# compare narrator counts: unique MIDS narrators vs kg spans in region
cmp = collections.Counter(); ex = []
for h, r in result.items():
    u = len({i for s in sanads[h] for i in s}); k = len(r['spans'])
    c = 'equal' if u == k else ('kg_fewer' if k < u else 'kg_more'); cmp[c] += 1
    if c != 'equal' and len(ex) < 6: ex.append((h, u, k, [len(s) for s in sanads[h]]))
log('unique-narrator count MIDS vs kg spans:', dict(cmp)); print('examples (hadith, mids_unique, kg_spans, sanad lengths):', ex)
nf = [h for h in mids if h not in result][:12]; print('first not-found MIDS ids:', nf, 'e.g. text:', mids[nf[0]][:90] if nf else '')
json.dump({str(h): {**r, 'mids_sanads': sanads[h]} for h, r in result.items()}, open(D + 'mids_to_kg_v2.json', 'w'))
json.dump([h for h in mids if h not in result], open(D + 'mids_unaligned.json', 'w'))
