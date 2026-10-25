"""Split chains at the transfer mark ح: every mention after a ح starts a new route (chain_no 2, 3 ...; pos restarts at 1 in each route).
Only hadith whose mentions are all still in chain_no 1 are touched.  A mention that itself spans the ح keeps the route of its start and the hadith is flagged h_span (re-parse candidate).
Old (chain_no, pos) of every changed mention is stored in surgery_log (step fix_44, kind chain_no_pos).  Gold hadith never change.
  python pipeline/fix_44_h_branches.py pilot [N] [seed]  |  apply"""
from paths import *
import sqlite3, sys, re, json, random, collections
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
H = re.compile('(?<![ء-يً-ْٰ])ح(?![ء-يً-ْٰ])')
todo = []; stats = collections.Counter()
c2 = db.cursor()
for h, text, ms, fl in c2.execute("select id,text,matn_start,flags from hadith where chain_tier in ('A','B','C') and matn_start>0"):
    if h in gold: continue
    hs = [m.start() for m in H.finditer(text[:ms])]
    if not hs: continue
    ments = c.execute('select rowid,start,end,coalesce(chain_no,1),pos from chain_mention where hadith_id=? and start is not null order by start', (h,)).fetchall()
    if not ments or any(m[3] != 1 for m in ments): stats['skip: already split / no mentions'] += 1; continue
    br = [1 + sum(1 for p in hs if p < m[1]) for m in ments]
    span = any(m[1] < p < m[2] for m in ments for p in hs)
    ranks = {b: i + 1 for i, b in enumerate(sorted(set(br)))}; br = [ranks[b] for b in br]
    if max(br) == 1: stats['skip: no mention after the ح'] += 1; continue
    todo.append((h, text, ms, fl, ments, br, span)); stats['hadith to split'] += 1; stats['h_span'] += span
print(dict(stats), '| routes distribution:', collections.Counter(max(t[5]) for t in todo).most_common(6))
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for h, text, ms, fl, ments, br, span in random.sample(todo, min(ARG or 14, len(todo))):
        print('\n', h, 'span' if span else '', '| chain:', text[:min(ms, 330)].replace('\n', ' '))
        for k in sorted(set(br)): print(f'   route {k}:', [text[m[1]:m[2]].strip()[:20] for m, b in zip(ments, br) if b == k])
else:
    n = 0
    for h, text, ms, fl, ments, br, span in todo:
        cnt = collections.Counter()
        for m, b in zip(ments, br):
            cnt[b] += 1
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_44','chain_no_pos',?,?,?)", (m[0], json.dumps([m[3], m[4]]), json.dumps([b, cnt[b]])))
            c.execute('update chain_mention set chain_no=?, pos=? where rowid=?', (b, cnt[b], m[0]))
        for r in c.execute('select rowid,pos from chain_mention where hadith_id=? and start is null and pos<100000', (h,)).fetchall():      # unlocated mentions are parked after the numbered ones (as fix_24 does)
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_44','chain_no_pos',?,?,?)", (r[0], json.dumps([1, r[1]]), json.dumps([1, r[1] + 100000])))
            c.execute('update chain_mention set pos=? where rowid=?', (r[1] + 100000, r[0]))
        c.execute("update hadith set flags=? where id=?", (((fl or '') + ' h_branches' + (' h_span' if span else '')).strip(), h)); n += 1
        if n % 5000 == 0: db.commit(); print(n, flush=True)
    db.commit(); print('applied', n)
