"""Merge audit (P9, zero tokens).  fix_30/fix_08 moved 25K mentions onto merge targets.  A moved mention whose target's death year contradicts the identified neighbours in its chain
(target dies > 15y after its student-side neighbour or > 80y before it; or > 5y before / > 100y after its teacher-side neighbour) is chronologically impossible.  Baseline conflict rate for ordinary
assigned mentions is 15%; for moved mentions 28.6%.  Targets where >= 80% (n >= 6) of the moved mentions conflict are treated as wrong merges of several people: the CONFLICTING moved mentions on them
are taken off the narrator (narrator_id NULL, id_method 'fix_55_merge_conflict'), so the ranker can re-resolve them (its chronology filter keeps the conflicting candidate out).
  python pipeline/fix_55_merge_suspects.py list | apply"""
from paths import *
import sqlite3, sys, collections, json
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=300, uri=(MODE != 'apply')); c = db.cursor()
death = dict(c.execute('select id,death_year from narrator where death_year is not null'))
rows = c.execute("select key,old,new from surgery_log where step in ('fix_30','fix_08') and kind='mention_narrator_id'").fetchall()
def ctx(rid):
    r = c.execute('select hadith_id,coalesce(chain_no,1),narrator_id from chain_mention where rowid=?', (int(rid),)).fetchone()
    if not r or not r[2]: return None
    h, cn, nid = r
    ch = c.execute('select rowid,narrator_id from chain_mention where hadith_id=? and coalesce(chain_no,1)=? and start is not null order by pos,rowid', (h, cn)).fetchall()
    k = next((i for i, x in enumerate(ch) if x[0] == int(rid)), None)
    if k is None: return None
    prev = next((death.get(x[1]) for x in reversed(ch[:k]) if x[1] and death.get(x[1])), None)
    nxt = next((death.get(x[1]) for x in ch[k + 1:] if x[1] and death.get(x[1])), None)
    return nid, prev, nxt
def conf(nid, prev, nxt):
    dc = death.get(nid)
    if not dc: return None
    return bool((prev and (dc > prev + 15 or dc < prev - 80)) or (nxt and (dc < nxt - 5 or dc > nxt + 100)))
tot = collections.Counter(); bad = collections.Counter(); badrows = collections.defaultdict(list)
for rid, old, new in rows:
    x = ctx(rid)
    if not x: continue
    r = conf(*x)
    if r is None: continue
    tot[x[0]] += 1
    if r: bad[x[0]] += 1; badrows[x[0]].append(int(rid))
sus = [n for n in tot if tot[n] >= 6 and bad[n] / tot[n] >= 0.8]
names = dict(c.execute('select id,std_name from narrator'))
print('suspect targets', len(sus), '| conflicting moved mentions to unassign', sum(bad[n] for n in sus), flush=True)
if MODE == 'list':
    for n in sorted(sus, key=lambda n: -bad[n])[:15]: print(n, death.get(n), (names.get(n) or '')[:50], tot[n], bad[n])
else:
    k = 0
    for n in sus:
        for rid in badrows[n]:
            r = c.execute('select narrator_id,id_method,id_confidence,guess_narrator_id from chain_mention where rowid=?', (rid,)).fetchone()
            if not r or r[0] != n or str(r[1]).startswith('manual_gold'): continue
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_55','merge_conflict_mention',?,?,'NULL')", (str(rid), '|'.join(str(v) for v in r)))
            c.execute("update chain_mention set narrator_id=NULL, id_method='fix_55_merge_conflict', id_confidence=NULL where rowid=?", (rid,)); k += 1
    db.commit(); print('unassigned', k)
