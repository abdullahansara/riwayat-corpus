"""Surgery step 14 - re-export narrators.csv and the sample CSVs from the current database (same rows as the old samples where they still exist).
  python pipeline/fix_14_export.py"""
from paths import *
import sqlite3, csv, collections, os
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
PKG = os.path.dirname(PIPE.rstrip('/\\')) if PIPE else '.'
cnt = dict(c.execute('SELECT narrator_id, count(*) FROM chain_mention WHERE narrator_id IS NOT NULL GROUP BY 1'))
names = collections.defaultdict(list)
for nid, form in c.execute('SELECT narrator_id, form FROM narrator_name ORDER BY observed_count DESC'):
    if len(names[nid]) < 25 and form not in names[nid]: names[nid].append(form)
sids = collections.defaultdict(list)
for nid, src, sid in c.execute('SELECT narrator_id, source, source_id FROM narrator_source_id'): sids[nid].append(f'{src}:{sid}')
flags = collections.defaultdict(list)
for nid, fl in c.execute('SELECT narrator_id, flag FROM narrator_flag'): flags[nid].append(fl)
HEAD = ['narrator_id', 'standard_name', 'death_year', 'tradition', 'n_hadith', 'source_ids', 'alternative_names', 'flags']
rows = [[nid, nm, dy, tr, cnt.get(nid, 0), ' '.join(sids[nid]), ' | '.join(names[nid]), ';'.join(flags[nid])]
        for nid, nm, dy, tr in c.execute('SELECT id, std_name, death_year, tradition FROM narrator ORDER BY id')]
with open(OUT + 'narrators.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(HEAD); w.writerows(rows)
print('narrators.csv', len(rows))
S = os.path.join(PKG, 'sample')
def old_keys(fn, cols):
    with open(os.path.join(S, fn), encoding='utf-8-sig', newline='') as f: return [tuple(r[k] for k in cols) for r in csv.DictReader(f)]
def write(fn, head, data):
    with open(os.path.join(S, fn), 'w', encoding='utf-8-sig', newline='') as f: w = csv.writer(f); w.writerow(head); w.writerows(data)
write('narrators_sample.csv', HEAD, rows[:200])
ids = [k[0] for k in old_keys('hadith_sample.csv', ['id'])]
cols = [r[1] for r in c.execute('pragma table_info(hadith)')]
data = [c.execute(f'SELECT {",".join(cols)} FROM hadith WHERE id=?', (i,)).fetchone() for i in ids]
write('hadith_sample.csv', cols, [d for d in data if d])
keys = old_keys('chain_mention_sample.csv', ['hadith_id', 'pos'])
cols = [r[1] for r in c.execute('pragma table_info(chain_mention)')]
data = [c.execute(f'SELECT {",".join(cols)} FROM chain_mention WHERE hadith_id=? AND pos=?', (h, int(p))).fetchone() for h, p in keys]
write('chain_mention_sample.csv', cols, [d for d in data if d])
print('samples refreshed')
