"""Final derived-data repair (zero tokens): (1) renumber positions 1..n inside every (hadith, chain_no) chain whose positions have gaps (order kept; old pos in surgery_log step fix_66);
(2) refresh hadith.n_narrators = number of chain_mention rows (the convention of fix_03/fix_04).  Supplementary chains legitimately restart at pos 1, so they are NOT touched."""
from paths import *
import sqlite3
db = sqlite3.connect(OUT + 'hadith_master.db', timeout=300); c = db.cursor()
ch = c.execute('select hadith_id,coalesce(chain_no,1) from chain_mention group by 1,2 having max(pos)-min(pos)+1!=count(*) or min(pos)!=1').fetchall(); k = 0
for h, cn in ch:
    rows = c.execute('select rowid,pos from chain_mention where hadith_id=? and coalesce(chain_no,1)=? order by pos,rowid', (h, cn)).fetchall()
    for i, (rid, pos) in enumerate(rows, 1):
        if pos != i:
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_66','pos',?,?,?)", (str(rid), pos, i)); c.execute('update chain_mention set pos=? where rowid=?', (i, rid)); k += 1
bad = c.execute('select h.id,(select count(*) from chain_mention m where m.hadith_id=h.id) from hadith h where chain_tier!="none" and n_narrators is not (select count(*) from chain_mention m where m.hadith_id=h.id)').fetchall()
for h, n in bad: c.execute('update hadith set n_narrators=? where id=?', (n, h))
db.commit(); print('chains renumbered', len(ch), '| rows moved', k, '| n_narrators refreshed', len(bad))
