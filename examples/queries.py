"""Example queries.  Usage: python examples/queries.py [path/to/hadith_master.db]"""
import sqlite3, sys, os, pathlib, pathlib
db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'HadithMaster', 'hadith_master.db')
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)

# 1. Find a narrator by any known name form (diacritic-normalised column `norm`)
name = 'ابو هريره'   # normalised form: no diacritics, ة->ه, أإآ->ا, ى->ي
for nid, std in c.execute('select distinct n.id, n.std_name from narrator_name nn join narrator n on n.id=nn.narrator_id where nn.norm=? limit 5', (name,)):
    print('narrator', nid, std)

# 2. The ordered chain of one hadith with narrator IDs
hid = c.execute("select id from hadith where chain_tier='A' limit 1").fetchone()[0]
print('chain of', hid)
for pos, surface, nid, method, conf in c.execute('select pos, surface, narrator_id, id_method, id_confidence from chain_mention where hadith_id=? order by pos', (hid,)):
    print(' ', pos, surface, nid, method, conf)

# 3. A narrator's most frequent teachers (student -> teacher edges)
nid = c.execute('select student from narrator_edge group by 1 order by sum(n_hadith) desc limit 1').fetchone()[0]
print('top teachers of', nid)
for t, n in c.execute('select e.teacher, e.n_hadith from narrator_edge e where e.student=? order by 2 desc limit 5', (nid,)):
    print(' ', t, c.execute('select std_name from narrator where id=?', (t,)).fetchone()[0], n)
