"""P4: weak-guess policy.  A weak guess (narrator_id NULL, guess_narrator_id set, not a relative/anonymous node) is KEPT only if
  guess_confidence >= 0.5 AND the guess is backed by the narrator's own name: every content token of the surface is in the narrator's std_name,
  or the exact normalised surface is a form of that narrator observed >= 2 times in chains.
Everything else is demoted to an honest 'unresolved' (guess_narrator_id/guess_confidence NULL; old value in surgery_log, candidates stay in `alternatives`).
Audit 2026-10-22: weak guesses ~1/3 right (7/22), bare names resolved to hubs (عبد الله -> Ibn Abbas).
  python pipeline/fix_50_weak_guesses.py count | pilot [seed] | apply"""
from paths import *
import sqlite3, sys, re, random, collections
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nrm(s): return re.sub(r'\s+', ' ', re.sub(r'[^ء-ي ]', ' ', re.sub(r'[A-Za-z]-?\d+', ' ', DIAC.sub('', s or '')).translate(TR))).strip()
STRIP = {'بن', 'و', 'ابن'}
def toks(n): return [w for w in n.split() if w not in STRIP]
def strip_conj(n): return n[1:] if n.startswith('و') and len(n) > 3 else n
cache = {}
def stdtoks(g):
    if g not in cache:
        std = c.execute('select std_name from narrator where id=?', (g,)).fetchone()
        cache[g] = set(toks(nrm(std[0] if std else '')))
        if len(cache) > 200000: cache.pop(next(iter(cache)))
    return cache[g]
HEAD = {'ابي', 'ابو', 'ام'}
def keep(surface, g, conf):
    """dominance: the guess carries >= 80% of the chain observations of the exact surface form (and >= 5); or a rare form (<= 2 narrators) whose 2+ content tokens are in std_name"""
    if (conf or 0) < 0.5: return False
    s = strip_conj(nrm(surface))
    if not s: return False
    rows = c.execute('select narrator_id,max(observed_count) from narrator_name where norm=? group by narrator_id', (s,)).fetchall()
    obs = {n: (o or 0) for n, o in rows}; tot = sum(obs.values()); og = obs.get(g, 0)
    if og >= 5 and og >= 0.8 * tot: return True
    content = [w for w in toks(s) if w not in HEAD]
    return 0 < len(rows) <= 2 and g in obs and len(content) >= 2 and set(content) <= stdtoks(g)
Q = "select rowid,hadith_id,pos,coalesce(chain_no,1),surface,guess_narrator_id,guess_confidence,id_method from chain_mention where narrator_id is null and guess_narrator_id is not null and node_key is null and surface is not null"
if MODE == 'count':
    k = d = 0; by = collections.Counter()
    for rid, h, pos, cn, s, g, gc, m in c.execute(Q):
        r = keep(s, g, gc); k += r; d += (not r); by[(r, m.split(':')[0])] += 1
    print('keep', k, 'demote', d); print(by.most_common(12))
elif MODE == 'pilot':
    random.seed(int(sys.argv[2])); mx = c.execute('select max(rowid) from chain_mention').fetchone()[0]; kk, dd = [], []
    while len(kk) < 20 or len(dd) < 6:
        r = c.execute(Q + ' and rowid>=? limit 1', (random.randint(1, mx),)).fetchone()
        if r: (kk if keep(r[4], r[5], r[6]) else dd).append(r)
    for tag, lst in (('KEEP', kk[:20]), ('DEM ', dd[:6])):
        for rid, h, pos, cn, s, g, gc, m in lst:
            std = c.execute('select std_name,death_year from narrator where id=?', (g,)).fetchone()
            ch = c.execute('select surface from chain_mention where hadith_id=? and coalesce(chain_no,1)=? order by pos', (h, cn)).fetchall()
            print(f'{tag} {h}#{pos} c={gc} "{s[:30]}" -> {std[0][:40]} d{std[1]}   ctx: ' + ' | '.join((x[0] or '?')[:22] for x in ch[max(0, pos - 2):pos + 2]))
else:
    rows = c.execute(Q).fetchall(); n = 0; B = 20000
    dem = [(rid, g, gc) for rid, h, pos, cn, s, g, gc, m in rows if not keep(s, g, gc)]
    for i in range(0, len(dem), B):
        ch = dem[i:i + B]
        c.executemany("insert into surgery_log values('fix_50','weak_guess_demoted',?,?,'NULL')", [(str(r), f'{g}|{gc}') for r, g, gc in ch])
        c.executemany("update chain_mention set guess_narrator_id=NULL, guess_confidence=NULL where rowid=?", [(r,) for r, g, gc in ch])
        db.commit(); n += len(ch); print('demoted', n, flush=True)
