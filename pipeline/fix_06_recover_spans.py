"""Surgery step 06 - recover the text span of chain mentions that have a narrator ID but no location.
For each such mention the text between the nearest located neighbours is searched (ignoring vowel marks / hamza forms)
for any known name form of that narrator, longest form first.
  python pipeline/fix_06_recover_spans.py eval     hide known spans and see how often they are found again
  python pipeline/fix_06_recover_spans.py apply
"""
from paths import *
import sqlite3, re, sys, random, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'eval'
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ‏‎]'); MAP = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm_map(text):
    """normalised text with a map from normalised index -> original index (spaces collapsed)"""
    out = []; idx = []; prev_space = True
    for i, ch in enumerate(text):
        if DIAC.match(ch): continue
        ch = ch.translate(MAP) if ch in 'أإآٱىةؤئ' else ch
        if not ('ء' <= ch <= 'ي'): ch = ' '
        if ch == ' ':
            if prev_space: continue
            prev_space = True
        else: prev_space = False
        out.append(ch); idx.append(i)
    return ''.join(out), idx
forms_cache = {}
def forms(nid):
    if nid not in forms_cache:
        fs = [r[0] for r in c.execute("SELECT DISTINCT norm FROM narrator_name WHERE narrator_id=? AND norm IS NOT NULL AND length(norm) BETWEEN 3 AND 70", (nid,))]
        forms_cache[nid] = sorted(set(fs), key=lambda x: -len(x))[:60]
    return forms_cache[nid]
def locate(nt, idx, text, nid, lo, hi):
    """find a name form of nid inside original-text window [lo, hi); returns (start, end) or None"""
    a = next((k for k, i in enumerate(idx) if i >= lo), len(idx)); b = next((k for k, i in enumerate(idx) if i >= hi), len(idx))
    win = ' ' + nt[a:b] + ' '
    for f in forms(nid):
        for pre in ('', 'و'):
            k = win.find(' ' + pre + f + ' ')
            if k >= 0:
                ns = a + k; ne = a + k + len(pre) + len(f) + 1 - 1
                st = idx[ns] if ns < len(idx) else None; en = idx[min(ne, len(idx)) - 1] + 1
                while en < len(text) and DIAC.match(text[en]): en += 1
                return st, en
    return None
def run(hadith_ids, hide=None):
    found = tot = 0; upd = []; exact = 0
    for hid in hadith_ids:
        text, ms = c.execute('SELECT text, matn_start FROM hadith WHERE id=?', (hid,)).fetchone()
        rows = c.execute('SELECT rowid,pos,start,end,narrator_id FROM chain_mention WHERE hadith_id=? ORDER BY pos', (hid,)).fetchall()
        rows = [list(r) for r in rows]
        truth = {}
        if hide:                                           # evaluation: pretend these spans are unknown
            for r in rows:
                if r[0] in hide: truth[r[0]] = (r[2], r[3]); r[2] = r[3] = None
        nt, idx = norm_map(text)
        for i, r in enumerate(rows):
            if r[2] is not None or r[4] is None: continue
            lo = max([x[3] for x in rows[:i] if x[3] is not None] or [0])
            nxt = [x[2] for x in rows[i + 1:] if x[2] is not None]
            hi = nxt[0] if nxt else min(len(text), (ms if ms else lo + 500) + 30)
            res = locate(nt, idx, text, r[4], lo, hi); tot += 1
            if res:
                found += 1; r[2], r[3] = res; upd.append((res[0], res[1], text[res[0]:res[1]], r[0]))
                if r[0] in truth:
                    t = truth[r[0]]; o = min(res[1], t[1]) - max(res[0], t[0]); exact += o > 0 and o >= 0.5 * min(res[1] - res[0], t[1] - t[0])
    return tot, found, exact, upd
if MODE == 'eval':
    random.seed(3)
    ids = [r[0] for r in c.execute("SELECT DISTINCT hadith_id FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id WHERE h.chain_tier='B' AND m.start IS NOT NULL LIMIT 400000")]
    random.shuffle(ids); ids = ids[:3000]; hide = set()
    for hid in ids:
        rs = c.execute('SELECT rowid FROM chain_mention WHERE hadith_id=? AND start IS NOT NULL', (hid,)).fetchall()
        hide.update(r[0] for r in random.sample(rs, max(1, len(rs) // 3)))
    tot, found, exact, _ = run(ids, hide)
    log(f'hidden spans: {tot:,} | located: {found:,} ({found/tot:.1%}) | located at the right place: {exact:,} ({exact/max(found,1):.1%} of located)')
else:
    ids = [r[0] for r in c.execute("SELECT DISTINCT hadith_id FROM chain_mention WHERE start IS NULL AND narrator_id IS NOT NULL")]
    log(f'hadith with unlocated mentions: {len(ids):,}')
    tot, found, exact, upd = run(ids)
    c.executemany("UPDATE chain_mention SET start=?, end=?, surface=?, flags=COALESCE(flags,'')||' span_recovered' WHERE rowid=?", upd); db.commit()
    log(f'recovered {found:,} of {tot:,} unlocated mentions | committed')
