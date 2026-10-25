"""Rule-based cleanups (zero tokens).
  dup_pos   make (hadith_id, chain_no, pos) unique: in each affected chain the rows are re-numbered in text order (an unlocated mention that shares a position goes BEFORE the located one), old positions in surgery_log
  dup_text  table dup_group(hadith_id, group_id, group_size): hadith with identical letters-only text (diacritics/punctuation/spacing ignored, length > 60); the text column is untouched
  flags     table hadith_flag(hadith_id, flag, note): hadith the re-parse agents identified as biography/rijal entries with no chain (flag 'non_hadith_entry'); nothing deleted
  python pipeline/fix_56_cleanups.py dup_pos|dup_text|flags|all"""
from paths import *
import sqlite3, sys, re, glob, json, hashlib, collections, os
MODE = sys.argv[1]
db = sqlite3.connect(OUT + 'hadith_master.db', timeout=300); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def letters(s): return re.sub('[^ء-ي]', '', DIAC.sub('', s or '').translate(TR))
def dup_pos():
    groups = c.execute('select hadith_id,coalesce(chain_no,1) from chain_mention group by hadith_id,coalesce(chain_no,1),pos having count(*)>1').fetchall()
    chains = sorted(set(groups)); n = 0
    for h, cn in chains:
        rows = c.execute('select rowid,pos,start from chain_mention where hadith_id=? and coalesce(chain_no,1)=? order by pos, (start is not null), start, rowid', (h, cn)).fetchall()
        base = min(r[1] for r in rows)
        for i, (rid, pos, st) in enumerate(rows):
            if pos != base + i:
                c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_56','pos',?,?,?)", (str(rid), pos, base + i)); c.execute('update chain_mention set pos=? where rowid=?', (base + i, rid)); n += 1
    db.commit(); print('chains renumbered', len(chains), '| rows moved', n)
def dup_text():
    c.execute('drop table if exists dup_group'); c.execute('create table dup_group(hadith_id text primary key, group_id text, group_size int)')
    by = collections.defaultdict(list)
    for h, t in c.execute('select id,text from hadith'):
        l = letters(t)
        if len(l) > 40: by[hashlib.md5(l.encode()).digest()].append(h)
    rows = []
    for k, hs in by.items():
        if len(hs) > 1:
            gid = 'D' + hashlib.md5(k).hexdigest()[:10]; rows += [(h, gid, len(hs)) for h in hs]
    c.executemany('insert into dup_group values(?,?,?)', rows); db.commit()
    print('duplicate-text groups', len({r[1] for r in rows}), '| hadith in groups', len(rows))
def flags():
    c.execute('create table if not exists hadith_flag(hadith_id text, flag text, note text, primary key(hadith_id, flag))'); n = 0
    for f in glob.glob('labels/reparse*_out/chunk_*.jsonl') + glob.glob('labels/reparse*g_out/chunk_*.jsonl'):
        for l in open(f, encoding='utf-8'):
            if not l.strip(): continue
            try: o = json.loads(l)
            except Exception: continue
            note = (o.get('note') or '')
            if not o.get('transmitters') and re.search(r'biograph|rijal|jarh|ta.?dil|entry|no chain|تعديل|ترجمة', note, re.I):
                c.execute('insert or ignore into hadith_flag values(?,?,?)', (o['id'], 'non_hadith_entry', note[:200])); n += 1
    db.commit(); print('flagged non-hadith entries', n)
if MODE in ('dup_pos', 'all'): dup_pos()
if MODE in ('dup_text', 'all'): dup_text()
if MODE in ('flags', 'all'): flags()
