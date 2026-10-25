"""Surgery step 04b - repair the narrator IDs of mentions produced by the splitter (fix_04), forward only (no revert).
The pilot review showed three faults: relative words ("أبي") inherited the old ID, short kunya parts took a popularity guess, and
parts other than the last one received the old ID.  New policy for parts flagged split_from_merged:
  1. relative-pronoun word (أبي, أبيه, جده ...)        -> ID cleared, method linker_relative_unresolved (step 05 resolves it from the previous narrator)
  2. last part of its original mention, >= 2 words, and the old ID is one of its name candidates -> keep the old ID (0.9)
  3. otherwise rank candidates with neighbours; assert the ID only if margin >= T (default 8); else ID cleared and the best candidates are stored in `alternatives`
  python pipeline/fix_04b_repair_split_ids.py pilot [N]      print the decisions for N random hadith (tier C first) for manual review, nothing written
  python pipeline/fix_04b_repair_split_ids.py apply [T]"""
from paths import *
import sqlite3, sys, re, random, collections, json, time, importlib.util
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
sp = importlib.util.spec_from_file_location('d2', PIPE + 'fix_02_disambiguate.py')
argv = sys.argv; sys.argv = [argv[0], 'noop']; d2 = importlib.util.module_from_spec(sp); sp.loader.exec_module(d2); sys.argv = argv
db = d2.db; c = d2.c; norm = d2.norm
REL = {'ابيه', 'ابي', 'ابوه', 'اباه', 'ابيها', 'جده', 'جدها', 'ابنه', 'اخيه', 'عمه', 'ابيهم', 'امه', 'اخوه'}
T = float(argv[2]) if MODE == 'apply' and len(argv) > 2 else (float(argv[3]) if MODE == 'pilot' and len(argv) > 3 else 7.0)
def plain(s): return re.sub('[ً-ْٰـ]', '', s or '')
def decide(hid, rows, old_by_span):
    out = {}
    for i, (rid, pos, st, en, surf, nid, meth) in enumerate(rows):
        if 'surgery_split' not in (meth or ''): continue
        n = norm(surf)
        if n in REL or n.replace('و', '', 1) in REL:
            out[rid] = (None, 'linker_relative_unresolved', 0.0, None, 'relative'); continue
        parts_of_same = [r for r in rows if old_by_span.get(r[0]) == old_by_span.get(rid)]
        is_last = parts_of_same and parts_of_same[-1][0] == rid
        old = old_by_span.get(rid)
        cs = d2.cands(surf)
        if old and is_last and len(n.split()) >= 2 and old in cs:
            out[rid] = (old, 'surgery_split', 0.9, None, 'old_id_last_part'); continue
        prev = rows[i - 1][5] if i > 0 else None; nxt = rows[i + 1][5] if i + 1 < len(rows) else None
        rk = d2.rank(surf, prev, nxt)
        if not rk: out[rid] = (None, 'surgery_split', None, None, 'no_candidates'); continue
        margin = (rk[0][0] - rk[1][0]) if len(rk) > 1 else 99
        if margin >= T or len(cs) == 1 and len(n.split()) >= 3: out[rid] = (rk[0][1], 'surgery_split', 0.95 if margin >= T else 0.9, None, 'ranked')
        else: out[rid] = (None, 'surgery_split_candidates_only', None, json.dumps([x[1] for x in rk[:3]]), 'low_margin')
    return out
def load(hid):
    rows = c.execute('SELECT rowid,pos,start,end,surface,narrator_id,id_method FROM chain_mention WHERE hadith_id=? ORDER BY pos', (hid,)).fetchall()
    olds = c.execute("SELECT start,end,narrator_id FROM removed_mention WHERE hadith_id=? AND step='fix_04'", (hid,)).fetchall()
    ob = {}
    for r in rows:
        for s, e, nid in olds:
            if r[2] is not None and s is not None and r[2] >= s and r[3] <= e: ob[r[0]] = (s, nid)
    return rows, {k: v[1] for k, v in ob.items()}
if MODE == 'pilot':
    N = int(argv[2]) if len(argv) > 2 else 40; random.seed(21)
    ids = [r[0] for r in c.execute("SELECT DISTINCT m.hadith_id FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id WHERE m.flags LIKE '%split_from_merged%' AND h.chain_tier IN ('C')")]
    ids += [r[0] for r in c.execute("SELECT DISTINCT m.hadith_id FROM chain_mention m WHERE m.flags LIKE '%split_from_merged%' LIMIT 3000")]
    random.shuffle(ids); ids = list(dict.fromkeys(ids))[:N]; stat = collections.Counter()
    for hid in ids:
        rows, olds = load(hid); dec = decide(hid, rows, olds)
        print('##', hid)
        for r in rows:
            if r[0] in dec:
                d = dec[r[0]]; stat[d[4]] += 1
                nm = lambda x: (c.execute('select std_name,death_year from narrator where id=?', (x,)).fetchone() or ('NONE', None)) if x else ('NONE', None)
                o = nm(r[5]); n = nm(d[0])
                print(f'   {plain(r[4])[:34]!r:38s} OLD {o[0][:26]:26s} -> NEW {n[0][:26]:26s} [{d[4]}]')
    print(dict(stat))
else:
    ids = [r[0] for r in c.execute("SELECT DISTINCT hadith_id FROM chain_mention WHERE flags LIKE '%split_from_merged%'")]
    import os; ids.sort(); ids = ids[int(os.environ.get('START', 0)):][:int(os.environ.get('COUNT', 10**9))]   # resumable slices
    print(f'hadith to repair: {len(ids):,} (T={T})', flush=True); stat = collections.Counter(); upd = []
    for k, hid in enumerate(ids):
        rows, olds = load(hid)
        for rid, d in decide(hid, rows, olds).items():
            stat[d[4]] += 1; upd.append((d[0], d[1], d[2], d[3], rid))
        if k % 5000 == 4999 or k == len(ids) - 1:
            c.executemany('UPDATE chain_mention SET narrator_id=?, id_method=?, id_confidence=?, alternatives=COALESCE(?, alternatives) WHERE rowid=?', upd); db.commit(); upd = []
            print(f'  {k+1:,}/{len(ids):,}', dict(stat), flush=True)
    print('committed', dict(stat))
