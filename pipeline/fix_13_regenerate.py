"""Surgery step 13 - regenerate derived data after the in-place fixes (the stored copies were stale).
  text_tagged   : full text with <N id="N..."> (asserted ID), <N guess="N..."> (weak ID) or <N> (no ID) around every located chain mention
  narrator_edge : student->teacher pairs from ADJACENT mentions (pos, pos+1) of the same chain_no, both with an asserted ID
  hadith.n_narrators : number of chain mentions (all chains)
  narrator_name.observed_count : recount of how often each existing observed form occurs (no forms are added back, so fix_09 purges stay purged)
  python pipeline/fix_13_regenerate.py [tagged|edges|counts|all]"""
from paths import *
import sqlite3, sys, time, collections, re
from xml.sax.saxutils import quoteattr
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'all'
db = sqlite3.connect(OUT + 'hadith_master.db', timeout=120); c = db.cursor()
if MODE in ('edges', 'all'):
    c.executescript('DROP TABLE IF EXISTS narrator_edge; CREATE TABLE narrator_edge(student TEXT, teacher TEXT, n_hadith INT, n_tier_a INT);')
    c.execute('''INSERT INTO narrator_edge
      SELECT a.narrator_id, b.narrator_id, count(DISTINCT a.hadith_id), count(DISTINCT CASE WHEN h.chain_tier='A' THEN a.hadith_id END)
      FROM chain_mention a JOIN chain_mention b ON a.hadith_id=b.hadith_id AND b.pos=a.pos+1 AND coalesce(a.chain_no,1)=coalesce(b.chain_no,1)
      JOIN hadith h ON h.id=a.hadith_id
      WHERE a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL AND a.narrator_id<>b.narrator_id GROUP BY 1,2''')
    c.executescript('CREATE INDEX IF NOT EXISTS ix_edge_s ON narrator_edge(student); CREATE INDEX IF NOT EXISTS ix_edge_t ON narrator_edge(teacher);'); db.commit()
    c.execute('ALTER TABLE narrator_edge ADD COLUMN suspect TEXT')
    c.execute("UPDATE narrator_edge SET suspect='teacher_died_30y_after_student' WHERE rowid IN (SELECT e.rowid FROM narrator_edge e JOIN narrator s ON s.id=e.student JOIN narrator t ON t.id=e.teacher WHERE s.death_year IS NOT NULL AND t.death_year IS NOT NULL AND t.death_year-s.death_year>=30)")
    c.execute("UPDATE narrator_edge SET suspect=coalesce(suspect||',','')||'two_cycle' WHERE rowid IN (SELECT a.rowid FROM narrator_edge a JOIN narrator_edge b ON a.student=b.teacher AND a.teacher=b.student)"); db.commit()
    log('narrator_edge rows:', c.execute('select count(*) from narrator_edge').fetchone()[0])
if MODE in ('counts', 'all'):
    c.execute('UPDATE hadith SET n_narrators=(SELECT count(*) FROM chain_mention m WHERE m.hadith_id=hadith.id)'); db.commit()
    log('n_narrators refreshed')
    DIAC = re.compile('[ً-ْٰـٓ-ٕ‏‎]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
    def norm(s): return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
    cnt = collections.Counter()
    for nid, s, n in c.execute('SELECT narrator_id, surface, count(*) FROM chain_mention WHERE narrator_id IS NOT NULL AND surface IS NOT NULL GROUP BY 1,2'): cnt[(nid, norm(s))] += n
    rows = [(cnt.get((nid, nn), 0), rid) for rid, nid, nn in c.execute('SELECT rowid, narrator_id, norm FROM narrator_name')]
    c.executemany('UPDATE narrator_name SET observed_count=? WHERE rowid=?', rows); db.commit()
    log('observed_count recounted')
if MODE in ('tagged', 'all'):
    ids = [r[0] for r in c.execute('SELECT id FROM hadith ORDER BY id')]
    done = 0
    for k in range(0, len(ids), 20000):
        upd = []
        for hid in ids[k:k + 20000]:
            text, = c.execute('SELECT text FROM hadith WHERE id=?', (hid,)).fetchone()
            ms = c.execute('SELECT start,end,narrator_id,guess_narrator_id FROM chain_mention WHERE hadith_id=? AND start IS NOT NULL AND end>start ORDER BY start', (hid,)).fetchall()
            if not ms: upd.append((None, hid)); continue
            out = []; pos = 0
            for s, e, nid, g in ms:
                if s < pos or e > len(text): continue                 # overlapping / out of range
                tag = f'<N id="{nid}">' if nid else (f'<N guess="{g}">' if g else '<N>')
                out.append(text[pos:s]); out.append(tag + text[s:e] + '</N>'); pos = e
            out.append(text[pos:]); upd.append((''.join(out), hid))
        c.executemany('UPDATE hadith SET text_tagged=? WHERE id=?', upd); db.commit(); done += len(upd)
        log(f'text_tagged {done:,}/{len(ids):,}')
