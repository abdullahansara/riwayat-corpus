"""Surgery step 03 - remove biography/commentary names that were read as chain links.
A mention is removed when a biography phrase (روى عن / روى عنه / وروى عن / يروي عن / روي عنه) occurs before it
more recently than any chain verb (حدثنا, أخبرنا, أنبأ, ثنا, نا, أنا ...), within a short window.
Dry run by default; --apply writes (deleted rows are kept in table `removed_mention`; positions are renumbered).
Checked against the gold set: no gold-kept mention may be removed (the script prints the count)."""
from paths import *
import sqlite3, re, sys, json, collections
APPLY = '--apply' in sys.argv
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
BIO = re.compile(r'(?:^|\s)(?:و?روى|و?يروي|و?روي|و?رووا)\s+(?:عنه|عنها|عنهم|عن)(?:\s|$)')
VERB = re.compile(r'(?:^|\s)(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انبا|انبانى|ثنا|ثني|نا|انا|اخبرناه|حدثناه|سمعت|قال)(?:\s|$)')
def strip(s): return DIAC.sub('', s).translate(str.maketrans('أإآٱ', 'اااا'))
WIN = 160
def is_bio(text, s):
    w = strip(text[max(0, s - WIN):s])
    b = [m.end() for m in BIO.finditer(w)]
    if not b: return False
    v = [m.end() for m in VERB.finditer(w)]
    return (not v) or b[-1] > v[-1]
c.executescript('CREATE TABLE IF NOT EXISTS removed_mention(hadith_id TEXT, pos INT, start INT, end INT, surface TEXT, narrator_id TEXT, id_method TEXT, step TEXT);')
gold = {}
for l in open(PIPE + '../gold/gold_chains.jsonl', encoding='utf-8'):
    g = json.loads(l); gold[g['hadith_id']] = g
def ov(a, b):
    o = min(a[1], b[1]) - max(a[0], b[0]); return o > 0 and o >= 0.5 * min(a[1] - a[0], b[1] - b[0])
rows = c.execute("SELECT h.id, h.text, h.chain_tier FROM hadith h WHERE h.chain_tier!='none' AND EXISTS (SELECT 1 FROM chain_mention m WHERE m.hadith_id=h.id AND m.start IS NOT NULL) AND (h.text LIKE '%روى%' OR h.text LIKE '%يروي%' OR h.text LIKE '%روي%')").fetchall()
print('hadith to inspect:', len(rows), flush=True)
rem = []; tier = collections.Counter(); gold_bad = gold_ok = 0
for hid, text, ct in rows:
    for pos, s, e, surf, nid, meth in c.execute('SELECT pos,start,end,surface,narrator_id,id_method FROM chain_mention WHERE hadith_id=? AND start IS NOT NULL', (hid,)).fetchall():
        if ct != 'C' or s < 5 or not is_bio(text, s): continue
        rem.append((hid, pos, s, e, surf, nid, meth)); tier[ct] += 1
        if hid in gold:
            if any(ov((s, e), (m['start'], m['end'])) for m in gold[hid]['mentions']): gold_bad += 1
            else: gold_ok += 1
print(f'mentions to remove: {len(rem):,} by tier {dict(tier)} | gold: wrongly removed {gold_bad}, correctly removed {gold_ok}')
for r in rem[:5]: print('   ', r[0], r[1], repr(r[4][:40]), r[5], r[6])
if APPLY and gold_bad == 0:
    c.executemany("INSERT INTO removed_mention VALUES(?,?,?,?,?,?,?,'fix_03')", rem)
    c.executemany('DELETE FROM chain_mention WHERE hadith_id=? AND pos=?', [(r[0], r[1]) for r in rem])
    hs = sorted({r[0] for r in rem})
    for hid in hs:                                       # renumber positions 1..n and refresh n_narrators
        rws = c.execute('SELECT rowid FROM chain_mention WHERE hadith_id=? ORDER BY pos', (hid,)).fetchall()
        for i, (rid,) in enumerate(rws, 1): c.execute('UPDATE chain_mention SET pos=? WHERE rowid=?', (i, rid))
        c.execute('UPDATE hadith SET n_narrators=? WHERE id=?', (len(rws), hid))
    db.commit(); print('applied to', len(hs), 'hadith')
elif APPLY: print('NOT applied: rule removed gold-kept mentions')
