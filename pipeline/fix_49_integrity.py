"""P0 integrity: (1) narrator_merge chains (a new_id that was itself merged away) -> point at the final target;
(2) guess_narrator_id values that no longer exist -> the merge target if one exists, else NULL (guess dropped).
Logged in surgery_log.   python pipeline/fix_49_integrity.py"""
from paths import *
import sqlite3
db = sqlite3.connect(OUT + 'hadith_master.db', timeout=120); c = db.cursor()
merge = dict(c.execute('select old_id,new_id from narrator_merge'))
def final(x):
    seen = set()
    while x in merge and x not in seen: seen.add(x); x = merge[x]
    return x
exist = set(r[0] for r in c.execute('select id from narrator'))
n1 = 0
for old, new in list(merge.items()):
    f = final(new)
    if f != new and f in exist:
        c.execute("insert into surgery_log values('fix_49','merge_target',?,?,?)", (old, new, f)); c.execute('update narrator_merge set new_id=? where old_id=?', (f, old)); merge[old] = f; n1 += 1
print('merge targets repointed', n1, '| still missing', sum(1 for v in merge.values() if v not in exist))
n2 = n3 = 0
for rid, g in c.execute('select rowid,guess_narrator_id from chain_mention where guess_narrator_id is not null').fetchall():
    if g in exist: continue
    f = final(g)
    if f in exist:
        c.execute("insert into surgery_log values('fix_49','guess_repoint',?,?,?)", (str(rid), g, f)); c.execute('update chain_mention set guess_narrator_id=? where rowid=?', (f, rid)); n2 += 1
    else:
        c.execute("insert into surgery_log values('fix_49','guess_dropped',?,?,NULL)", (str(rid), g)); c.execute('update chain_mention set guess_narrator_id=NULL, guess_confidence=NULL where rowid=?', (rid,)); n3 += 1
db.commit(); print('guesses repointed', n2, 'dropped', n3)
