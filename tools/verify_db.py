"""Integrity and summary check for hadith_master.db.  Usage: python tools/verify_db.py [path/to/hadith_master.db]"""
import sqlite3, sys, os, pathlib, pathlib
db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'HadithMaster', 'hadith_master.db')
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
print('quick_check:', c.execute('pragma quick_check').fetchone()[0])
for t in ('hadith', 'chain_mention', 'narrator', 'narrator_name', 'narrator_source_id', 'narrator_edge', 'reference_chain', 'narrator_merge'):
    print(f'{t:20s}', c.execute(f'select count(*) from {t}').fetchone()[0])
print('chain tiers:', c.execute('select chain_tier, count(*) from hadith group by 1 order by 2 desc').fetchall())
print('mentions without narrator id:', c.execute('select count(*) from chain_mention where narrator_id is null').fetchone()[0])
