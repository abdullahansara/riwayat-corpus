import csv, json, re, sqlite3, collections, random, openpyxl, time
csv.field_size_limit(10**9)
t0 = time.time(); random.seed(5)
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
H = '<ROOT>/HadithKG/'
# ---- independent exam: Muslim hadith whose narrator set is confirmed EXACTLY by MIDS (via SH crosswalk)
D = '<ROOT>/MIDS_SahihMuslim/'
sh_ids = {}
with open('<ROOT>/SemanticHadithV2/sh_chains_ids.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[1] == 'SM': sh_ids[int(x[2])] = {i for i in json.loads(x[5]) if i}
mp = collections.defaultdict(set)
ws = openpyxl.load_workbook(D + '3_Hadith_SahihMuslim_Isnad=Edges for Graph.xlsx', read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); hdr = next(it)
for r in it:
    d = dict(zip(hdr, r))
    if d['HadithNo'] is not None: h = int(d['HadithNo']); mp[h].add(str(d['sourceNarratorID'])); mp[h].add(str(d['targetNarratorID']))
cw = json.load(open('<ROOT>/SemanticHadithV2/crosswalk_sh_to_mids.json'))
pairs = json.load(open('<ROOT>/SemanticHadithV2/sh_muslim_to_mids.json'))
exact = set()
for n, v in pairs.items():
    if v[2] != 1 or v[1] not in ('full', 'head+tail'): continue
    S = sh_ids.get(int(n), set()); M = mp.get(v[0], set())
    if S and M and all(s in cw for s in S) and {cw[s]['mids_id'] for s in S} == M: exact.add(int(n))
log('Muslim hadith confirmed exactly by MIDS:', len(exact))
exam_ind = []; exam_kids = set()
with open(H + 'gold_sh_validated.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        if d['col'] == 'SM' and d['num'] in exact: exam_ind.append(d); exam_kids.add(d['kid'])
with open(H + 'exam_independent_muslim.jsonl', 'w', encoding='utf-8') as f:
    for d in exam_ind: f.write(json.dumps(d, ensure_ascii=False) + '\n')
log('independent exam hadith (with kg spans):', len(exam_ind))
# ---- all usable hadith-kg hadith
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True)
books = dict(con.execute('select id, name from books').fetchall())
M = collections.defaultdict(list)
for h, a, b in con.execute('select hadith_id, start, end from hadith_rawis order by hadith_id, seq'): M[h].append((a, b))
log('hadith with mentions', len(M))
out = open(H + 'parser_corpus_all.jsonl', 'w', encoding='utf-8'); held = open(H + 'exam_heldout.jsonl', 'w', encoding='utf-8')
st = collections.Counter(); nb = collections.Counter()
for hid, bid, nass, ms, me in con.execute('select id, book_id, nass, matn_start, matn_end from hadiths where nass is not null and matn_start is not null and matn_end is not null'):
    sp = M.get(hid)
    if not sp: st['no_spans'] += 1; continue
    if me <= ms: st['bad_matn_offsets'] += 1; continue
    pre = [x for x in sp if x[1] <= ms + 5]; post = [x for x in sp if x[0] >= me - 5]
    if pre and not post: order = 'chain_first'; sp = pre; last = max(e for _, e in sp)
    elif post and not pre: order = 'matn_first'; sp = post; last = max(e for _, e in sp)
    elif pre and post: order = 'chain_first'; sp = pre; last = max(e for _, e in sp); st['trailing_mentions_ignored'] += 1
    else: st['all_mentions_inside_matn_skipped'] += 1; continue
    if order == 'chain_first' and ms - last > 800: st['gap_too_long'] += 1; continue
    if order == 'matn_first' and min(a for a, _ in sp) - me > 800: st['gap_too_long'] += 1; continue
    st['order_' + order] += 1
    if hid in exam_kids: st['in_independent_exam'] += 1; continue
    cut = min(len(nass), max(ms + 80, last + 40)); rec = {'kid': hid, 'book': books.get(bid, ''), 'order': order, 'text': nass[:cut], 'spans': sp, 'matn_start': ms, 'matn_end': min(me, cut)}
    if hid % 20 == 0: held.write(json.dumps(rec, ensure_ascii=False) + '\n'); st['heldout'] += 1
    else: out.write(json.dumps(rec, ensure_ascii=False) + '\n'); st['train_pool'] += 1; nb[rec['book']] += 1
out.close(); held.close()
log('DONE', dict(st)); log('books in pool:', len(nb), '| top:', [(b[:20], c) for b, c in nb.most_common(5)], '| books with <50 hadith:', sum(1 for c in nb.values() if c < 50))
