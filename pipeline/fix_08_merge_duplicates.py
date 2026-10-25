"""Surgery step 08 - merge duplicate narrator records (same person under two IDs).
A pair is merged when ALL hold:
  - identical normalised standard name with >= 3 words (or >= 2 words and the same death year; >= 5 words when a death year is missing)
  - same tradition family (shia vs sunni/unknown)
  - death years equal, or one missing (then >= 4 words required), never both present and > 2 apart
  - the two records share no source: they never appear as two different people inside one source dataset
Target = the record with more source ids, then more mentions. Everything is moved to the target; the old record is deleted and logged in narrator_merge.
  python pipeline/fix_08_merge_duplicates.py          dry run (counts + samples)
  python pipeline/fix_08_merge_duplicates.py --apply"""
from paths import *
import sqlite3, re, sys, collections, random, json
APPLY = '--apply' in sys.argv
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = 'ً-ْٰـٓ-ٕ‏‎'
def norm(s):
    s = re.sub('[' + DIAC + ']', '', str(s or '')).translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', s)).strip()
nar = c.execute('SELECT id, std_name, death_year, tradition, n_sources FROM narrator').fetchall()
srcs = collections.defaultdict(set)
for nid, s in c.execute('SELECT narrator_id, source FROM narrator_source_id'): srcs[nid].add(s)
pop = dict(c.execute('SELECT narrator_id, count(*) FROM chain_mention WHERE narrator_id IS NOT NULL GROUP BY 1'))
groups = collections.defaultdict(list)
for nid, name, dy, tr, ns in nar:
    n = norm(name)
    if len(n.split()) >= 2: groups[n].append((nid, dy, 'shia' if (tr or '').startswith('shi') else 'sunni', ns or 0))
merges = {}; rejected = collections.Counter()
for n, g in groups.items():
    if len(g) < 2: continue
    w = len(n.split())
    g.sort(key=lambda x: (-len(srcs[x[0]]), -pop.get(x[0], 0)))
    for i, a in enumerate(g):
        if a[0] in merges: continue
        for b in g[i + 1:]:
            if b[0] in merges: continue
            if a[2] != b[2]: rejected['tradition'] += 1; continue
            if a[1] is not None and b[1] is not None:
                if abs(a[1] - b[1]) > 2: rejected['death years differ'] += 1; continue
                if w < 3 and a[1] != b[1]: rejected['2-word name without equal death year'] += 1; continue
            else:
                if w < 5: rejected['missing death year and short name'] += 1; continue
                if len(g) > 3: rejected['one date missing, name shared by >3 records (ambiguous)'] += 1; continue
            if srcs[a[0]] & srcs[b[0]]: rejected['shared source'] += 1; continue
            merges[b[0]] = a[0]
print(f'duplicate groups: {sum(1 for g in groups.values() if len(g) > 1):,} | merges proposed: {len(merges):,} | rejected: {dict(rejected)}')
random.seed(4)
for old, new in random.sample(list(merges.items()), min(8, len(merges))):
    r1 = c.execute('select std_name,death_year from narrator where id=?', (old,)).fetchone(); r2 = c.execute('select std_name,death_year from narrator where id=?', (new,)).fetchone()
    print('  ', old, r1[0][:40], r1[1], srcs[old], '->', new, r2[1], srcs[new], pop.get(old, 0), pop.get(new, 0))
if APPLY:
    c.executescript('CREATE TABLE IF NOT EXISTS narrator_merge(old_id TEXT PRIMARY KEY, new_id TEXT, reason TEXT, jaccard REAL, n_hadith INT);')
    rows = [(o, n, 'fix_08 identical normalised name + compatible dates + disjoint sources', None, pop.get(o, 0)) for o, n in merges.items()]
    c.executemany('INSERT OR REPLACE INTO narrator_merge VALUES(?,?,?,?,?)', rows)
    pairs = list(merges.items())
    for o, n in pairs:  # reversibility: log which mentions moved
        c.execute("INSERT INTO surgery_log(step,kind,key,old,new) SELECT 'fix_08','mention_narrator_id',rowid,?,? FROM chain_mention WHERE narrator_id=?", (o, n, o))
        c.execute("INSERT INTO surgery_log(step,kind,key,old,new) SELECT 'fix_08','mention_guess_id',rowid,?,? FROM chain_mention WHERE guess_narrator_id=?", (o, n, o))
    for t in ('removed_mention', 'narrator_flag', 'purged_name_form'):
        c.executemany(f'UPDATE OR IGNORE {t} SET narrator_id=? WHERE narrator_id=?', [(n, o) for o, n in pairs])
    c.executemany('UPDATE chain_mention SET narrator_id=? WHERE narrator_id=?', [(n, o) for o, n in pairs])
    c.executemany('UPDATE chain_mention SET guess_narrator_id=? WHERE guess_narrator_id=?', [(n, o) for o, n in pairs])
    c.executemany('UPDATE OR IGNORE narrator_name SET narrator_id=? WHERE narrator_id=?', [(n, o) for o, n in pairs])
    c.executemany('UPDATE OR IGNORE narrator_source_id SET narrator_id=? WHERE narrator_id=?', [(n, o) for o, n in pairs])
    for o, n in pairs:
        old = c.execute('select death_year,birth_year,tabaqa,city from narrator where id=?', (o,)).fetchone()
        for col, val in zip(('death_year', 'birth_year', 'tabaqa', 'city'), old or ()):
            if val is not None: c.execute(f'UPDATE narrator SET {col}=? WHERE id=? AND {col} IS NULL', (val, n))
    c.executemany('DELETE FROM narrator WHERE id=?', [(o,) for o, n in pairs])
    c.execute('UPDATE narrator SET n_sources=(select count(distinct source) from narrator_source_id s where s.narrator_id=narrator.id)')
    mp = dict(pairs); fixed = 0
    for rid, ids in c.execute('select rowid, narrator_ids from reference_chain').fetchall():
        L = json.loads(ids)
        if any(x in mp for x in L): c.execute('UPDATE reference_chain SET narrator_ids=? WHERE rowid=?', (json.dumps([mp.get(x, x) for x in L]), rid)); fixed += 1
    db.commit(); print('applied;', len(pairs), 'records merged;', fixed, 'reference chains updated')
