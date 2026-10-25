import csv, sqlite3, json, collections, time
csv.field_size_limit(10**9)
S = '<ROOT>/Sanadset/'
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
agree = {}   # sanadset_row -> (kg_id, category)
with open(S + 'chain_agreement.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[2] in ('identical', 'same_chain_name_variants'): agree[int(x[0])] = (int(x[1]), x[2])
log('agreeing hadith', len(agree))
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True); cur = con.cursor()
bookname = dict(cur.execute('select id, name from books'))
items = sorted(agree.items()); out = open('<ROOT>/HadithKG/parser_corpus_tierA.jsonl', 'w', encoding='utf-8')
n = skipped = 0; stat = collections.Counter(); B = 3000
for i in range(0, len(items), B):
    chunk = items[i:i + B]; ids = [k for _, (k, _) in chunk]; q = ','.join('?' * len(ids))
    H = {h: (b, t, ms, me) for h, b, t, ms, me in cur.execute(f'select id, book_id, nass, matn_start, matn_end from hadiths where id in ({q})', ids)}
    M = collections.defaultdict(list)
    for h, seq, a, b in cur.execute(f'select hadith_id, seq, start, end from hadith_rawis where hadith_id in ({q}) order by hadith_id, seq', ids): M[h].append((a, b))
    for sid, (kid, cat) in chunk:
        b, t, ms, me = H[kid]; sp = M.get(kid, [])
        if not t or not sp or ms is None: skipped += 1; continue
        last_end = max(e for _, e in sp)
        if ms < last_end: stat['matn_before_last_narrator'] += 1            # inconsistent -> drop
        elif ms - last_end > 400: stat['gap_too_long'] += 1
        else:
            cut = min(len(t), ms + 80)
            out.write(json.dumps({'sid': sid, 'kid': kid, 'book': bookname.get(b, ''), 'cat': cat, 'text': t[:cut], 'spans': sp, 'matn_start': ms}, ensure_ascii=False) + '\n'); n += 1
            stat['kept'] += 1; continue
        skipped += 1
    if (i // B) % 20 == 0: log('processed', i + len(chunk), 'kept', n)
out.close(); log('DONE kept', n, 'skipped', skipped, dict(stat))
