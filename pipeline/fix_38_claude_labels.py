"""Store every Claude label in the database and write Claude's narrator choices onto the mentions they came from.
Tables (additive, idempotent):  claude_label_hadith(hadith_id, source, chain_status, matn_start_phrase, matn_end_phrase, note)
                                claude_label_mention(hadith_id, start, surface, kind, choice, source)
Sources with mention-level IDs: pilot, wave1, recheck, defects, unparsed, wave2 (chunk files carry the mention offsets).  Deep-identify files (labels/deep_out) are stored as source 'deep'.
Apply: a mention whose label is kind narrator with choice Nxxxx (registry id, still existing after merges via narrator_merge) gets narrator_id=choice, id_method 'claude_label',
id_confidence 0.95 unless it already has exactly that id; kind not_a_narrator gets flag claude_not_narrator (the mention is kept).  Gold hadith are never changed.  Logged in surgery_log (step fix_38).
Later sources never override earlier ones for the same mention; deep > wave2 > defects > unparsed > wave1 > pilot > recheck.
  python pipeline/fix_38_claude_labels.py pilot | apply"""
from paths import *
import sqlite3, sys, json, glob, os, collections, re
ISID = lambda x: bool(re.fullmatch(r'N\d+', str(x)))
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
merge = dict(c.execute('select old_id,new_id from narrator_merge')) if c.execute("select 1 from sqlite_master where name='narrator_merge'").fetchone() else {}
SRC = [('deep', None, 'deep_out'), ('wave2', 'wave2', 'wave2_out'), ('defects', 'defects', 'defects_out'), ('unparsed', 'unparsed', 'unparsed_out'), ('wave1', 'wave1', 'wave1_out'), ('pilot', 'pilot', 'pilot_out'), ('recheck', 'recheck', 'recheck_out')]
H = {}; M = {}                                                   # (hadith) -> row ; (hadith,start) -> row
for name, cd, od in SRC:
    if name == 'deep':
        for f in glob.glob('labels/deep_out/H*.jsonl'):
            h = os.path.basename(f)[:8]
            for l in open(f, encoding='utf-8'):
                if not l.strip(): continue
                o = json.loads(l); r = c.execute('select start from chain_mention where hadith_id=? and pos=? and coalesce(chain_no,1)=1', (h, o['pos'])).fetchone()
                ch = o['registry_id']
                if r and r[0] is not None and (h, r[0]) not in M:
                    M[(h, r[0])] = (h, r[0], o['surface'], 'narrator' if ISID(ch) else ('not_a_narrator' if ch == 'NOT_A_NARRATOR' else 'narrator'), ch if ISID(ch) else 'NONE', 'deep')
        continue
    items = {}
    for f in glob.glob(f'labels/{cd}/chunk_*.json'):
        for it in json.load(open(f, encoding='utf-8')): items[it['id']] = it
    for f in sorted(glob.glob(f'labels/{od}/chunk_*.jsonl')):
        for l in open(f, encoding='utf-8'):
            if not l.strip(): continue
            try: o = json.loads(l)
            except Exception: continue
            h = o.get('id'); it = items.get(h)
            if not it: continue
            if h not in H: H[h] = (h, name, o.get('chain_status'), o.get('matn_start_phrase'), o.get('matn_end_phrase'), o.get('note'))
            kinds = {m['i']: m for m in o.get('mentions', [])}
            for m in it['mentions']:
                k = kinds.get(m['i'])
                if k and (h, m['start']) not in M: M[(h, m['start'])] = (h, m['start'], m['surface'], k.get('kind'), k.get('choice') or '', name)
print('hadith labels', len(H), '| mention labels', len(M), collections.Counter(v[3] for v in M.values()), collections.Counter(v[5] for v in M.values()))
chg = []; skip = collections.Counter()
for (h, st), (_, _, surf, kind, ch, src) in M.items():
    if h in gold: skip['gold'] += 1; continue
    r = c.execute('select rowid,narrator_id,id_method,flags from chain_mention where hadith_id=? and start=? and coalesce(chain_no,1)=1', (h, st)).fetchone()
    if not r: skip['mention_gone'] += 1; continue
    rid, nid, meth, fl = r
    if kind == 'narrator' and ISID(ch):
        for _ in range(8):
            if ch in merge: ch = merge[ch]
            else: break
        if not c.execute('select 1 from narrator where id=?', (ch,)).fetchone(): skip['id_not_in_registry'] += 1; continue
        if nid == ch: skip['already_same'] += 1; continue
        chg.append(('id', rid, h, nid, ch, meth, fl, 'differs' if nid else 'new'))
    elif kind == 'not_a_narrator' and 'claude_not_narrator' not in (fl or '').split(): chg.append(('flag', rid, h, None, None, meth, fl, 'flag'))
print('would write', collections.Counter(x[0] + ':' + x[7] for x in chg), dict(skip))
if MODE == 'apply':
    c.executescript('''CREATE TABLE IF NOT EXISTS claude_label_hadith(hadith_id TEXT PRIMARY KEY, source TEXT, chain_status TEXT, matn_start_phrase TEXT, matn_end_phrase TEXT, note TEXT);
                       CREATE TABLE IF NOT EXISTS claude_label_mention(hadith_id TEXT, start INT, surface TEXT, kind TEXT, choice TEXT, source TEXT, PRIMARY KEY(hadith_id,start));''')
    c.executemany('INSERT OR REPLACE INTO claude_label_hadith VALUES(?,?,?,?,?,?)', list(H.values()))
    c.executemany('INSERT OR REPLACE INTO claude_label_mention VALUES(?,?,?,?,?,?)', list(M.values()))
    for t, rid, h, old, new, meth, fl, _ in chg:
        if t == 'id':
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_38','mention_narrator_id',?,?,?)", (rid, old, new))
            c.execute("update chain_mention set narrator_id=?, id_method='claude_label', id_confidence=0.95 where rowid=?", (new, rid))
        else:
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_38','mention_flags',?,?,?)", (rid, fl, ((fl or '') + ' claude_not_narrator').strip()))
            c.execute("update chain_mention set flags=? where rowid=?", (((fl or '') + ' claude_not_narrator').strip(), rid))
    db.commit(); print('applied', len(chg))
