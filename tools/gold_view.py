"""Gold-standard review helper.
  python tools/gold_view.py make            # draw the fixed stratified sample -> gold/gold_ids.json
  python tools/gold_view.py show START N    # show N hadith from position START of the sample, with candidates
Env HADITH_DB overrides the database path."""
import sqlite3, sys, os, json, re, random, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
db = os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
GOLD = ROOT / 'gold'; GOLD.mkdir(exist_ok=True)
DIAC = re.compile('[ً-ْٰـٓ-ٕ‏‎]'); KEEP = re.compile('[^ء-ي ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
def keys(s):
    t = norm(s).split(); out = []
    if not t: return out
    for tt in (t, ([t[0][1:]] + t[1:]) if len(t[0]) > 2 and t[0][0] == 'و' else None):
        if tt:
            tt = ['بن' if (w == 'ابن' and i > 0) else w for i, w in enumerate(tt)]
            if tt[0] in ('ابا', 'ابي'): tt[0] = 'ابو'
            k = ' '.join(tt)
            if k not in out: out.append(k)
    return out
STRATA = [('C', 'sunni', 70), ('C', 'shia', 10), ('B', None, 10), ('A', None, 10)]
if sys.argv[1] == 'make':
    prev = [l.split()[0] for l in open(ROOT / 'gold' / 'seed_ids.txt')] if (ROOT / 'gold' / 'seed_ids.txt').exists() else []
    ids = list(prev)
    for tier, trad, n in STRATA:
        q = 'select id from hadith where chain_tier=?' + (' and tradition=?' if trad else '') + ' and n_narrators>0'
        pool = [r[0] for r in c.execute(q, (tier, trad) if trad else (tier,))]
        random.Random(2026).shuffle(pool)
        have = sum(1 for i in prev if c.execute('select chain_tier, tradition from hadith where id=?', (i,)).fetchone() == (tier, trad or c.execute('select tradition from hadith where id=?', (i,)).fetchone()[0]))
        add = [p for p in pool if p not in ids][:max(0, n - have)]
        ids += add
    json.dump(ids, open(GOLD / 'gold_ids.json', 'w'), ensure_ascii=False)
    print(len(ids), 'hadith in sample')
else:
    ids = json.load(open(GOLD / 'gold_ids.json')); a, n = int(sys.argv[2]), int(sys.argv[3])
    SHOW = int(os.environ.get('SHOW', 700))
    for k, hid in enumerate(ids[a:a + n], a):
        t, trad, book, num, text, ms, tier = c.execute('select id, tradition, book, number, text, matn_start, chain_tier from hadith where id=?', (hid,)).fetchone()
        print(f'##{k} {hid} | {trad} | {book} #{num} | tier {tier} | matn_start={ms}')
        print('TEXT:', text[:SHOW].replace('\n', ' '))
        for pos, s, e, surf, nid, meth, conf in c.execute('select pos,start,end,surface,narrator_id,id_method,id_confidence from chain_mention where hadith_id=? order by pos', (hid,)):
            r = c.execute('select std_name, death_year from narrator where id=?', (nid,)).fetchone() if nid else None
            print(f'  {pos}. [{s}:{e}] {surf.strip()!r} -> {nid} {(r[0][:34] + " d." + str(r[1])) if r else "NONE"} ({meth},{conf})')
            seen = {nid}; cands = []
            for kk in keys(surf):
                for cid, std, dy, nh in c.execute('select distinct n.id, n.std_name, n.death_year, n.n_sources from narrator_name x join narrator n on n.id=x.narrator_id where x.norm=? limit 6', (kk,)):
                    if cid not in seen: seen.add(cid); cands.append(f'{cid} {std[:26]} d.{dy}')
            if cands and (meth or '').find('ambiguous') >= 0 or (cands and (conf or 1) < 0.8): print('       alt:', ' | '.join(cands[:4]))
