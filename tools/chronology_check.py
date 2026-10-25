"""Chronology validator.  In a chain (chain_no 1) the mention at pos p is the student of the mention at pos p+1.  A firm ID pair is flagged when the student's recorded
death year is more than GAP years BEFORE the teacher's (impossible except for data errors / wrong identification).  Read-only.
  python tools/chronology_check.py [db] [N examples]"""
import sqlite3, sys, collections, random, os
GAP = 20
db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'HadithMaster', 'hadith_master.db')
c = sqlite3.connect('file:' + db + '?mode=ro', uri=True)
D = dict(c.execute('select id,death_year from narrator where death_year is not null'))
rows = c.execute("select hadith_id,pos,narrator_id,id_method,rowid from chain_mention where coalesce(chain_no,1)=1 and narrator_id is not null order by hadith_id,pos").fetchall()
bad = collections.Counter(); tot = collections.Counter(); ex = []; hb = set(); npairs = 0
prev = None
for r in rows:
    if prev and prev[0] == r[0] and r[1] == prev[1] + 1 and prev[2] in D and r[2] in D:
        npairs += 1; tot[r[3]] += 1; tot[prev[3]] += 0
        if D[prev[2]] < D[r[2]] - GAP: bad[prev[3]] += 1; bad[r[3]] += 0; hb.add(r[0]); ex.append((r[0], prev[1], prev[2], D[prev[2]], prev[3], r[2], D[r[2]], r[3]))
    prev = r
print('adjacent firm-ID pairs with known death years:', npairs, '| violations:', len(ex), f'({len(ex)/max(1,npairs):.2%}) in', len(hb), 'hadith')
print('violations by method of the student mention:', bad.most_common(12))
random.seed(1)
for e in random.sample(ex, min(int(sys.argv[2]) if len(sys.argv) > 2 else 8, len(ex))): print(e)
