"""Add a `narrator_flag` table and a `flags` column in narrators.csv for narrator records whose
standard name looks compound or malformed.  Idempotent; additive only (does not change narrators/mentions).

Flags
  merged_names_suspect  created by us (std_name_source='chains_new') and the name contains 'عن' or '،':
                        the chain parser probably failed to split two narrators.
  compound_source_name  name comes from a rijal source in the form "X ، عن Y" (narrator identified by his teacher).
  overlong_name         standard name longer than 120 characters (usually a full genealogy; harmless but noisy).
"""
from paths import *
import csv, sqlite3, shutil, os
csv.field_size_limit(10**9)
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
c.executescript('DROP TABLE IF EXISTS narrator_flag; CREATE TABLE narrator_flag(narrator_id TEXT, flag TEXT, PRIMARY KEY(narrator_id, flag));')
c.execute("""INSERT OR IGNORE INTO narrator_flag SELECT id, 'merged_names_suspect' FROM narrator
             WHERE std_name_source='chains_new' AND (std_name LIKE '% عن %' OR std_name LIKE '%،%')""")
c.execute("""INSERT OR IGNORE INTO narrator_flag SELECT id, 'compound_source_name' FROM narrator
             WHERE std_name_source<>'chains_new' AND (std_name LIKE '% عن %' OR std_name LIKE '%،%')""")
c.execute("INSERT OR IGNORE INTO narrator_flag SELECT id, 'overlong_name' FROM narrator WHERE length(std_name)>120")
db.commit()
fl = {}
for nid, f in c.execute('SELECT narrator_id, flag FROM narrator_flag'): fl.setdefault(nid, []).append(f)
print({k: sum(k in v for v in fl.values()) for k in ('merged_names_suspect', 'compound_source_name', 'overlong_name')}, 'flagged narrators:', len(fl))
src = OUT + 'narrators.csv'; tmp = src + '.tmp'
with open(src, encoding='utf-8-sig', newline='') as f, open(tmp, 'w', encoding='utf-8-sig', newline='') as g:
    r = csv.reader(f); w = csv.writer(g); h = next(r)
    if 'flags' in h: h = h[:h.index('flags')]
    idx = h.index('narrator_id')
    w.writerow(h + ['flags'])
    for row in r: w.writerow(row[:len(h)] + [';'.join(fl.get(row[idx], []))])
shutil.move(tmp, src); print('narrators.csv updated')
