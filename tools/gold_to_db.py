"""Write the hand-verified gold chains (gold/gold_chains.jsonl) into the database, replacing the chain mentions of those hadith.
Unlike gold_apply.py --db this does NOT re-read gold/edits (their mention positions refer to an older database state);
it uses the finished jsonl, whose mentions carry text offsets. Narrator IDs that were merged later (fix_08) are mapped through narrator_merge.
Original mentions are saved in table gold_replaced_mention. Re-running is safe.
Usage: HADITH_DB=... python tools/gold_to_db.py [--apply]"""
import sqlite3, sys, os, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
dbp = os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
APPLY = '--apply' in sys.argv
c = sqlite3.connect(dbp, timeout=120)
merge = dict(c.execute('select old_id,new_id from narrator_merge'))
def fin(n):
    seen = 0
    while n in merge and seen < 10: n = merge[n]; seen += 1
    return n
valid = {r[0] for r in c.execute('select id from narrator')}
c.executescript('CREATE TABLE IF NOT EXISTS gold_replaced_mention AS SELECT * FROM chain_mention WHERE 0;')
n = bad = 0
for line in open(ROOT / 'gold' / 'gold_chains.jsonl', encoding='utf-8'):
    o = json.loads(line); hid = o['hadith_id']
    text, = c.execute('select text from hadith where id=?', (hid,)).fetchone()
    if text != o['text']: print('TEXT DIFFERS', hid); bad += 1; continue
    ms = o['mentions']
    for m in ms:
        if m['narrator_id']: m['narrator_id'] = fin(m['narrator_id'])
        if m['narrator_id'] and m['narrator_id'] not in valid: print('UNKNOWN ID', hid, m['narrator_id']); bad += 1
    if not APPLY: continue
    if not c.execute('select 1 from gold_replaced_mention where hadith_id=?', (hid,)).fetchone():
        c.execute('INSERT INTO gold_replaced_mention SELECT * FROM chain_mention WHERE hadith_id=?', (hid,))
    c.execute('DELETE FROM chain_mention WHERE hadith_id=?', (hid,))
    for i, m in enumerate(ms, 1):
        c.execute('INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,flags,chain_no) VALUES(?,?,?,?,?,?,?,?,?,1)',
                  (hid, i, m['start'], m['end'], m['surface'], m['narrator_id'],
                   'manual_gold' if m['id_verified'] and m['narrator_id'] else 'manual_gold_unverified_id', 1.0 if m['id_verified'] else 0.5, 'gold'))
    fl = c.execute('select flags from hadith where id=?', (hid,)).fetchone()[0] or ''
    if 'gold_reviewed' not in fl.split(): fl = (fl + ' gold_reviewed').strip()
    c.execute('UPDATE hadith SET n_narrators=?, flags=? WHERE id=?', (len(ms), fl, hid)); n += 1
c.commit(); print('hadith written:', n, '| problems:', bad)
