"""Draw a reproducible random sample of hadith for manual review of chain parsing / narrator IDs.
Usage: python tools/sample_for_review.py TIER N [SEED] [tradition]   e.g.  C 25 1 sunni
Prints, per hadith, the text opening and every chain mention with its assigned narrator."""
import sqlite3, sys, os, pathlib, random
tier, n = sys.argv[1], int(sys.argv[2]); seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
trad = sys.argv[4] if len(sys.argv) > 4 else None
db = os.path.join(os.path.dirname(__file__), '..', 'data', 'HadithMaster', 'hadith_master.db')
if os.environ.get('HADITH_DB'): db = os.environ['HADITH_DB']
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
q = "select id from hadith where chain_tier=?" + (" and tradition=?" if trad else "")
ids = [r[0] for r in c.execute(q, (tier, trad) if trad else (tier,))]
random.Random(seed).shuffle(ids)
for hid in ids[:n]:
    h = c.execute('select tradition, book, number, text, matn_start from hadith where id=?', (hid,)).fetchone()
    print(f'=== {hid} | {h[0]} | {h[1]} #{h[2]} | tier {tier} | matn_start={h[4]}')
    print('TEXT:', h[3][:int(os.environ.get('SHOW', 420))].replace('\n', ' '))
    for pos, s, e, surf, nid, meth, conf in c.execute('select pos,start,end,surface,narrator_id,id_method,id_confidence from chain_mention where hadith_id=? order by pos', (hid,)):
        std = c.execute('select std_name from narrator where id=?', (nid,)).fetchone() if nid else None
        print(f'  {pos}. [{s}:{e}] {surf!r} -> {nid} {std[0][:38] if std else "NONE"} ({meth},{conf})')
