"""Surgery step 02b - assert narrator IDs only where measured precision is >= 99 %; keep weaker choices as guesses.
Thresholds come from the leave-one-out evaluation of fix_02 (188,044 ambiguous trusted mentions, name evidence cleaned):
    1-word names: margin >= 10 (99.2 %)   2-word names: margin >= 7 (99.1 %)   3+ word names: margin >= 6 (99.3 %)
For guessed mentions (name_lookup_ambiguous, linker_prior_only*, surgery_disambiguated, surgery_split*):
    margin >= threshold -> narrator_id = best candidate, id_method 'surgery_asserted'
    otherwise           -> narrator_id = NULL, guess_narrator_id = best candidate, guess_confidence = calibrated accuracy of its margin bucket,
                           alternatives = top-3 candidates, id_method 'candidates_only'
  python pipeline/fix_02b_assert.py pilot [N]    print N random tier-C decisions (asserted ones first) for manual review; writes nothing
  python pipeline/fix_02b_assert.py apply"""
from paths import *
import sqlite3, sys, json, random, collections, time, importlib.util
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
sp = importlib.util.spec_from_file_location('d2', PIPE + 'fix_02_disambiguate.py')
argv = sys.argv; sys.argv = [argv[0], 'noop']; d2 = importlib.util.module_from_spec(sp); sp.loader.exec_module(d2); sys.argv = argv
db = d2.db; c = d2.c; norm = d2.norm
T = {1: 10.0, 2: 7.0, 3: 6.0}
CAL = [(25, 0.998), (15, 0.997), (12, 0.996), (10, 0.994), (7, 0.99), (6, 0.93), (5, 0.88), (3, 0.85), (1, 0.70), (-99, 0.49)]
def calib(m): return next(v for lo, v in CAL if m >= lo)
TARGET = ('name_lookup_ambiguous', 'linker_prior_only', 'linker_prior_only+backoff', 'surgery_disambiguated', 'surgery_split', 'surgery_split_candidates_only', 'candidates_only')
CTX = ('source_annotation_kg', 'source_annotation_thaqalayn', 'linker_unique', 'linker_unique+backoff', 'name_lookup_unique', 'name_lookup_unique_v2', 'linker_context', 'linker_context+backoff', 'surgery_asserted', 'manual_gold', 'surgery_relative_father')
cols = [r[1] for r in c.execute('PRAGMA table_info(chain_mention)')]
if MODE == 'apply':
    for col, typ in (('guess_narrator_id', 'TEXT'), ('guess_confidence', 'REAL')):
        if col not in cols: c.execute(f'ALTER TABLE chain_mention ADD COLUMN {col} {typ}')
def decide(ms, i):
    rid, surf, nid, meth = ms[i][:4]
    prev = ms[i - 1][2] if i > 0 and ms[i - 1][3] in CTX else None
    nxt = ms[i + 1][2] if i + 1 < len(ms) and ms[i + 1][3] in CTX else None
    mem = [x[2] for j, x in enumerate(ms) if j != i and x[3] in CTX and x[2]]
    r = d2.rank(surf, prev, nxt, None, None, len(ms) - 1 - i, mem)
    if not r: return None
    margin = (r[0][0] - r[1][0]) if len(r) > 1 else 99.0
    k = min(len(norm(surf).split()), 3) or 1
    return r[0][1], margin, margin >= T[k], [x[1] for x in r[1:4]]
if MODE == 'pilot':
    N = int(argv[2]) if len(argv) > 2 else 120; random.seed(33)
    hids = [r[0] for r in c.execute("SELECT DISTINCT m.hadith_id FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id WHERE h.chain_tier='C' AND m.id_method IN (%s) LIMIT 60000" % ','.join('?' * len(TARGET)), TARGET)]
    random.shuffle(hids); out = []; stat = collections.Counter()
    for hid in hids[:800]:
        ms = [list(r) for r in c.execute('SELECT rowid,surface,narrator_id,id_method FROM chain_mention WHERE hadith_id=? ORDER BY pos', (hid,))]
        for i, m in enumerate(ms):
            if m[3] not in TARGET or not m[1]: continue
            d = decide(ms, i)
            if d is None: stat['no_candidates'] += 1; continue
            stat['asserted' if d[2] else 'guess_only'] += 1
            if d[2]: out.append((hid, m[1], m[2], d[0], d[1], ms[i - 1][1] if i else '', ms[i + 1][1] if i + 1 < len(ms) else ''))
    print(dict(stat)); random.shuffle(out)
    nm = lambda x: (c.execute('select std_name,death_year from narrator where id=?', (x,)).fetchone() or ('NONE', None)) if x else ('NONE', None)
    P = lambda s: __import__('re').sub('[ً-ْٰـ]', '', s or '')
    for hid, surf, old, new, margin, ps, ns in out[:N]:
        a = nm(new); o = nm(old)
        print(f'{hid} [{P(ps)[:16]} | {P(surf)[:26]} | {P(ns)[:16]}] m={margin:.0f}  OLD {o[0][:22]} -> NEW {a[0][:30]} d.{a[1]}')
else:
    TODO = [t for t in TARGET if t != 'candidates_only']                       # candidates_only = already decided; repeated calls resume
    hids = [r[0] for r in c.execute("SELECT DISTINCT hadith_id FROM chain_mention WHERE id_method IN (%s)" % ','.join('?' * len(TODO)), TODO)]
    import os; hids.sort(); hids = hids[int(os.environ.get('START', 0)):][:int(os.environ.get('COUNT', 10**9))]   # processed hadith leave TARGET (asserted) so repeated calls resume
    print(f'hadith with guessed mentions: {len(hids):,}', flush=True); upd = []; stat = collections.Counter(); t0 = time.time()
    for k in range(0, len(hids), 5000):
        chunk = hids[k:k + 5000]; ph = ','.join('?' * len(chunk)); by = collections.defaultdict(list)
        for rid, hid, surf, nid, meth in c.execute(f'SELECT rowid,hadith_id,surface,narrator_id,id_method FROM chain_mention WHERE hadith_id IN ({ph}) ORDER BY hadith_id,pos', chunk): by[hid].append([rid, surf, nid, meth])
        for hid, ms in by.items():
            for sweep in (0, 1):
                for i, m in enumerate(ms):
                    if m[3] not in TARGET or not m[1]: continue
                    d = decide(ms, i)
                    if d is None:
                        if sweep == 1: stat['no_candidates'] += 1; upd.append((None, 'unresolved', 0.0, None, None, None, m[0])); m[2] = None; m[3] = 'unresolved'
                        continue
                    best, margin, ok, alts = d
                    if ok: upd.append((best, 'surgery_asserted', 0.95, json.dumps(alts), None, None, m[0])); m[2] = best; m[3] = 'surgery_asserted'; stat['asserted'] += 1 if sweep == 1 or True else 0
                    elif sweep == 1: upd.append((None, 'candidates_only', 0.0, json.dumps(alts), best, calib(margin), m[0])); m[2] = None; m[3] = 'candidates_only'; stat['guess_only'] += 1
        c.executemany('UPDATE chain_mention SET narrator_id=?, id_method=?, id_confidence=?, alternatives=COALESCE(?, alternatives), guess_narrator_id=?, guess_confidence=? WHERE rowid=?', list({u[6]: u for u in upd}.values())); db.commit(); upd = []
        if True: print(f'  {k:,}/{len(hids):,} {dict(stat)} {time.time()-t0:.0f}s', flush=True)
    print('committed |', dict(stat))
