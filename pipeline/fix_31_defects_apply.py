"""Phase 2 - apply Claude's matn boundaries for the hadith in labels/defects (no matn_start, or a chain mention inside the matn).
  python pipeline/fix_31_defects_apply.py pilot [N] [seed]   # read-only eye check
  python pipeline/fix_31_defects_apply.py apply              # writes; logged in surgery_log (step fix_31), flag claude_matn"""
from paths import *
from labels_lib import load_labels
import sqlite3, sys, json, random, collections
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'
c = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply'))
gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
import glob
ids = {json.loads(l)['id'] for f in glob.glob('labels/defects_out/chunk_*.jsonl') for l in open(f, encoding='utf-8') if l.strip()}
texts = {h: t for h, t in ((h, t) for h, t in c.execute('select id,text from hadith') if h in ids)}
L = load_labels(['labels/defects_out'], texts)
res = {}; skip = collections.Counter(); st = collections.Counter()
for h, o in L.items():
    st[o.get('chain_status')] += 1
    if h in gold: skip['gold'] += 1; continue
    text = texts[h]; ms0, me0, fl = c.execute('select matn_start,matn_end,flags from hadith where id=?', (h,)).fetchone()
    ms, me = o['matn_start'], o['matn_end']
    if ms is None or me is None or me <= ms + 5: skip['phrase_not_found_or_short'] += 1; continue
    last = c.execute('select max(end) from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and end<=?', (h, ms + 3)).fetchone()[0]
    res[h] = (text, ms0, me0, ms, me, fl)
print('labels', len(L), dict(st), 'applicable', len(res), dict(skip))
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for h in random.sample(list(res), min(ARG or 30, len(res))):
        text, ms0, me0, ms, me, fl = res[h]
        print(h, '| before:', text[max(0, ms - 40):ms].replace('\n', ' '), '[[', text[ms:ms + 60].replace('\n', ' '), '...', text[max(ms, me - 30):me].replace('\n', ' '), ']]', text[me:me + 25].replace('\n', ' '), '| old', ms0, me0, 'new', ms, me)
else:
    n = 0
    for h, (text, ms0, me0, ms, me, fl) in res.items():
        if ms != ms0: c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_31','matn_start',?,?,?)", (h, ms0, ms))
        if me != me0: c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_31','matn_end',?,?,?)", (h, me0, me))
        c.execute('update hadith set matn_start=?,matn_end=?,flags=? where id=?', (ms, me, ((fl or '') + ' claude_matn').strip(), h)); n += 1
    c.commit(); print('applied', n)
