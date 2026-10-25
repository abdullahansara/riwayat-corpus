import sqlite3, csv, re, hashlib, collections, time, sys
csv.field_size_limit(10**9)
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655]')
KEEP = re.compile(r'[^\u0621-\u064A ]')
TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nk(s):
    s = re.sub(r'<[^>]+>', ' ', s).replace('ﷺ', ' صلى الله عليه وسلم ')
    s = DIAC.sub('', s).translate(TR); s = KEEP.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()
def h8(s): return hashlib.md5(s.encode()).digest()[:8]
# ---- hadith-kg keys
con = sqlite3.connect('file:<ROOT>/HadithKG/hadith-kg.db?mode=ro', uri=True); cur = con.cursor()
bookname = dict(cur.execute('select id, name from books'))
full = collections.defaultdict(list); head = collections.defaultdict(list); tail = collections.defaultdict(list); kgbook = {}
n = 0
for hid, bid, nass in cur.execute('select id, book_id, nass from hadiths where nass is not null'):
    s = nk(nass)
    if len(s) < 40: continue
    kgbook[hid] = bid
    full[h8(s)].append(hid); head[h8(s[:80])].append(hid); tail[h8(s[-80:])].append(hid); n += 1
    if n % 200000 == 0: log('kg keyed', n)
log('hadith-kg keyed', n)
# ---- Sanadset rows
S = '<ROOT>/Sanadset/'
out = open(S + 'align_sanadset_kg.csv', 'w', encoding='utf-8-sig', newline=''); w = csv.writer(out)
w.writerow(['sanadset_row', 'Book', 'kg_hadith_id', 'kg_book', 'match_type', 'n_candidates'])
stat = collections.Counter(); bybook = collections.defaultdict(lambda: [0, 0])
with open(S + 'sanadset.csv', encoding='utf-8', newline='') as f:
    r = csv.reader(f); next(r)
    for i, row in enumerate(r, 2):
        s = nk(row[0]); book = row[1]; bybook[book][1] += 1
        if len(s) < 40: stat['too_short'] += 1; w.writerow([i, book, '', '', 'too_short', 0]); continue
        mt = None; c = full.get(h8(s))
        if c: mt = 'full'
        else:
            ch = head.get(h8(s[:80])); ct = tail.get(h8(s[-80:]))
            if ch and ct:
                both = set(ch) & set(ct)
                if both: c = list(both); mt = 'head+tail'
            if not c and ch and len(ch) == 1: c = ch; mt = 'head_only'
        if not c: stat['no_match'] += 1; w.writerow([i, book, '', '', 'no_match', 0]); continue
        stat[mt + ('_unique' if len(c) == 1 else '_ambiguous')] += 1; bybook[book][0] += 1
        w.writerow([i, book, c[0], bookname.get(kgbook[c[0]], ''), mt, len(c)])
        if i % 100000 == 0: log('sanadset rows', i, dict(stat))
tot = sum(stat.values()); log('DONE', tot)
for k, v in stat.most_common(): print(f'  {k:24s} {v:8d} {v/tot:6.1%}')
matched = sum(v for k, v in stat.items() if k not in ('no_match', 'too_short'))
print(f'MATCHED: {matched} ({matched/tot:.1%})')
bb = sorted(bybook.items(), key=lambda kv: -kv[1][1])
print('largest Sanadset books and their match rate:')
for b, (m, t) in bb[:15]: print(f'  {t:6d}  {m/t:5.0%}  {b[:40]}')
zero = [(b, t) for b, (m, t) in bybook.items() if m == 0]
print('books with ZERO matches:', len(zero), ' rows in them:', sum(t for _, t in zero))
