"""Pilot review of a surgery step on a small random tier-C sample (the 99% gate).
  python tools/pilot_review.py split N [SEED]      step 04: show N split mentions (original surface -> resulting parts with narrator)
  python tools/pilot_review.py ids N [SEED]        step 02: show N re-chosen narrator IDs (old -> new) with context
  python tools/pilot_review.py bio N [SEED]        step 03: show N removed biography mentions with the words before them
  python tools/pilot_review.py rel N [SEED]        step 05: show N resolved relative pronouns (X عن أبيه -> father)
  python tools/pilot_review.py span N [SEED]       step 06: show N recovered spans
Each item must be judged correct/incorrect by a person; a step passes the gate at >= 99 % correct."""
import sqlite3, sys, os, re, random, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
db = os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
kind, n = sys.argv[1], int(sys.argv[2]); seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
P = lambda s: DIAC.sub('', s or '')
std = lambda nid: ((c.execute('select std_name,death_year from narrator where id=?', (nid,)).fetchone() or ('?', None)) if nid else ('NONE', None))
nm = lambda nid: (lambda r: f'{r[0][:30]} d.{r[1]}')(std(nid))
random.seed(seed)
if kind == 'split':
    ids = [r[0] for r in c.execute("SELECT DISTINCT m.hadith_id FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id WHERE h.chain_tier='C' AND m.flags LIKE '%split_from_merged%'")]
    random.shuffle(ids)
    for hid in ids[:n]:
        old = c.execute("SELECT surface FROM removed_mention WHERE hadith_id=? AND step='fix_04' LIMIT 1", (hid,)).fetchone()
        print(f'## {hid}  ORIGINAL: {P(old[0])[:150] if old else "?"}')
        for pos, surf, nid, meth, conf in c.execute("SELECT pos,surface,narrator_id,id_method,id_confidence FROM chain_mention WHERE hadith_id=? AND flags LIKE '%split_from_merged%' ORDER BY pos", (hid,)):
            print(f'     {pos}. {P(surf)[:40]!r:44s} -> {nid} {nm(nid)} ({meth},{conf})')
elif kind == 'ids':
    rows = c.execute("SELECT l.key, l.old, l.new, m.hadith_id, m.pos, m.surface FROM surgery_log l JOIN chain_mention m ON m.rowid=CAST(l.key AS INTEGER) JOIN hadith h ON h.id=m.hadith_id WHERE l.step='fix_02' AND h.chain_tier='C' AND l.old IS NOT l.new LIMIT 200000").fetchall()
    random.shuffle(rows)
    for key, old, new, hid, pos, surf in rows[:n]:
        nb = c.execute('SELECT pos,surface,narrator_id FROM chain_mention WHERE hadith_id=? AND pos IN (?,?) ORDER BY pos', (hid, pos - 1, pos + 1)).fetchall()
        print(f'## {hid} pos{pos} {P(surf)[:40]!r}\n     OLD {old} {nm(old)}\n     NEW {new} {nm(new)}\n     neighbours: ' + ' | '.join(f'{p}:{P(s)[:20]}={nm(i)[:24]}' for p, s, i in nb))
elif kind == 'bio':
    rows = c.execute("SELECT r.hadith_id, r.pos, r.start, r.surface, r.narrator_id FROM removed_mention r JOIN hadith h ON h.id=r.hadith_id WHERE r.step='fix_03' AND h.chain_tier='C'").fetchall()
    random.shuffle(rows)
    for hid, pos, st, surf, nid in rows[:n]:
        t = c.execute('select text from hadith where id=?', (hid,)).fetchone()[0]
        print(f'## {hid}  REMOVED {P(surf)[:35]!r}  before it: ...{P(t[max(0, st - 70):st])}')
elif kind == 'rel':
    rows = c.execute("SELECT l.key, l.old, l.new, m.hadith_id, m.pos, m.surface FROM surgery_log l JOIN chain_mention m ON m.rowid=CAST(l.key AS INTEGER) JOIN hadith h ON h.id=m.hadith_id WHERE l.step='fix_05' AND l.new IS NOT NULL AND h.chain_tier='C'").fetchall()
    random.shuffle(rows)
    for key, old, new, hid, pos, surf in rows[:n]:
        prev = c.execute('SELECT narrator_id FROM chain_mention WHERE hadith_id=? AND pos=?', (hid, pos - 1)).fetchone()
        print(f'## {hid} {P(surf)!r}: previous narrator {nm(prev[0] if prev else None)}  =>  resolved to {nm(new)}')
elif kind == 'span':
    rows = c.execute("SELECT m.hadith_id, m.pos, m.surface, m.narrator_id FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id WHERE m.flags LIKE '%span_recovered%' AND h.chain_tier='C'").fetchall()
    random.shuffle(rows)
    for hid, pos, surf, nid in rows[:n]: print(f'## {hid} pos{pos} located {P(surf)[:40]!r}  for narrator {nm(nid)}')
