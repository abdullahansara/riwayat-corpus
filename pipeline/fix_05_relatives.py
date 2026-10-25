"""Surgery step 05 - resolve relative-pronoun narrators (أبيه, جده, أبي ...) from the previous narrator's name.
"X عن أبيه": the father of X is named inside X's standard name ("علي بن إبراهيم بن هاشم" -> "إبراهيم بن هاشم").
  python pipeline/fix_05_relatives.py eval     test on mentions whose answer is known from the source annotation
  python pipeline/fix_05_relatives.py apply    write: junk narrators named "أبيه" etc. are replaced by the resolved father, or by NULL when unresolved"""
from paths import *
import sqlite3, re, sys, math, random, collections, time, importlib.util
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'eval'
sp = importlib.util.spec_from_file_location('d2', PIPE + 'fix_02_disambiguate.py')
argv = sys.argv; sys.argv = [argv[0], 'noop']; d2 = importlib.util.module_from_spec(sp); sp.loader.exec_module(d2); sys.argv = argv
db = d2.db; c = d2.c; norm = d2.norm; name2n = d2.name2n; death = d2.death; pop = d2.pop; edge = d2.edge
std = dict(c.execute('SELECT id, std_name FROM narrator'))
FATHER = {'ابيه', 'ابوه', 'اباه', 'ابيها', 'ابيهم'}; GRAND = {'جده', 'جدها'}; REL = FATHER | GRAND
JUNK_NAMES = {n for n in (norm(s) for s in std.values() if s) if n in REL or n in ('ابي', 'ابنه', 'اخيه', 'عمه', 'رجاله')}
junk_ids = {k for k, v in std.items() if v and norm(v) in JUNK_NAMES}
log(f'junk relative-pronoun narrator records: {len(junk_ids)}')
def father_of(nid, loo_pair=None):
    """candidate fathers of narrator nid, best first, as (score, id)"""
    toks = norm(std.get(nid, '')).split()
    if 'بن' not in toks[1:]: return []
    i = toks.index('بن', 1); tail = toks[i + 1:]
    out = {}
    for L in range(len(tail), 0, -1):                              # longest name first: "ابراهيم بن هاشم", then "ابراهيم"
        for cid in name2n.get(' '.join(tail[:L]), ()):
            if cid == nid: continue
            e = edge.get((nid, cid), 0) - (1 if loo_pair == (nid, cid) else 0)
            s = 2.0 * math.log1p(max(e, 0)) + 0.25 * math.log1p(pop.get(cid, 0)) + 0.5 * L
            dn, dc = death.get(nid), death.get(cid)
            if dn is not None and dc is not None:
                if dc > dn + 5: s -= 4
                elif dn - dc > 90: s -= 2
            if cid not in out or out[cid] < s: out[cid] = s
        if len(out) >= 1 and L >= 2: break
    return sorted(((s, i) for i, s in out.items()), reverse=True)
def decide(nid, loo=None):
    r = father_of(nid, loo)
    if not r: return None, 0
    margin = r[0][0] - (r[1][0] if len(r) > 1 else r[0][0] - 3)
    return (r[0][1], margin) if margin >= 1.0 else (None, margin)

if MODE == 'eval':
    random.seed(7); ok = tot = abstain = 0
    rows = c.execute("""SELECT m.hadith_id, m.pos, m.narrator_id, m.surface FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id
                        WHERE h.chain_tier='A' AND m.id_method='source_annotation_kg' AND m.pos>1""").fetchall()
    rows = [r for r in rows if norm(r[3]) in FATHER]; random.shuffle(rows); rows = rows[:30000]
    for hid, pos, truth, surf in rows:
        prev = c.execute('SELECT narrator_id FROM chain_mention WHERE hadith_id=? AND pos=?', (hid, pos - 1)).fetchone()
        if not prev or not prev[0]: continue
        best, margin = decide(prev[0], (prev[0], truth))
        tot += 1
        if best is None: abstain += 1
        else: ok += (best == truth)
    log(f'father mentions tested {tot:,} | answered {tot-abstain:,} ({(tot-abstain)/max(tot,1):.1%}) | accuracy when answered {ok/max(tot-abstain,1):.1%}')

if MODE == 'apply':
    c.executescript('CREATE TABLE IF NOT EXISTS surgery_log(step TEXT, kind TEXT, key TEXT, old TEXT, new TEXT);')
    rows = c.execute("SELECT rowid, hadith_id, pos, surface, narrator_id, id_method FROM chain_mention WHERE surface IS NOT NULL").fetchall()
    rows = [r for r in rows if norm(r[3]) in REL and (r[4] is None or r[4] in junk_ids or r[5] in ('linker_relative_unresolved', 'linker_unmatched'))]
    log(f'relative-pronoun mentions to process: {len(rows):,}')
    stat = collections.Counter(); upd = []; lg = []
    bypos = {}
    for rid, hid, pos, surf, nid, meth in rows: bypos[(hid, pos)] = rid
    for rid, hid, pos, surf, nid, meth in rows:
        n = norm(surf); anchor = None
        pm = c.execute('SELECT narrator_id FROM chain_mention WHERE hadith_id=? AND pos=?', (hid, pos - 1)).fetchone() if pos > 1 else None
        anchor = pm[0] if pm and pm[0] and pm[0] not in junk_ids else None
        if n in GRAND and anchor:                                  # grandfather = father of the father
            f, _ = decide(anchor); anchor = f
        best, margin = decide(anchor) if anchor else (None, 0)
        if best:
            stat['resolved'] += 1; upd.append((best, 'surgery_relative_father', 0.7 if margin < 3 else 0.85, rid)); lg.append(('fix_05', 'narrator_id', rid, nid, best))
        elif nid in junk_ids:
            stat['junk_cleared'] += 1; upd.append((None, 'relative_unresolved', 0.0, rid)); lg.append(('fix_05', 'narrator_id', rid, nid, None))
        else: stat['left'] += 1
    c.executemany('UPDATE chain_mention SET narrator_id=?, id_method=?, id_confidence=? WHERE rowid=?', upd)
    c.executemany('INSERT INTO surgery_log VALUES(?,?,?,?,?)', lg); db.commit()
    log('result', dict(stat), '| committed')
