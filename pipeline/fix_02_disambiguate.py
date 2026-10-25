"""Surgery step 02 - choose between candidate narrators for an ambiguous name using
  (a) popularity, (b) known student->teacher links (tier-A evidence), (c) death-year consistency with the chain neighbours.

  python pipeline/fix_02_disambiguate.py eval            leave-one-out test on trusted tier-A mentions (reports accuracy / abstention curve)
  python pipeline/fix_02_disambiguate.py apply [MARGIN]  re-resolve the guessed mentions (name_lookup_ambiguous, linker_prior_only), logged in surgery_log
Chain order: position i narrates from position i+1 (student = i, teacher = i+1).
"""
from paths import *
import sqlite3, re, sys, math, random, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'eval'
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = 'ً-ْٰـٓ-ٕ‏‎'
def norm(s):
    s = re.sub('[' + DIAC + ']', '', str(s or '')).translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', s)).strip()
def keys(surface):
    t = norm(surface).split(); out = []
    if not t: return out
    def add(tt):
        k = ' '.join(tt)
        if k and k not in out: out.append(k)
    add(t); t1 = list(t)
    if len(t1[0]) > 2 and t1[0][0] == 'و': t1[0] = t1[0][1:]
    if t1[0] in ('ابا', 'ابي'): t1[0] = 'ابو'
    t1 = ['بن' if (w == 'ابن' and i > 0) else w for i, w in enumerate(t1)]; add(t1)
    t2 = [w[:-1] if (len(w) > 3 and w.endswith('ا') and not w.endswith('ابا')) else w for w in t1]; add(t2)
    return out
log('loading narrators, names, edges ...')
death = {r[0]: r[1] for r in c.execute('SELECT id, death_year FROM narrator WHERE death_year IS NOT NULL')}
tradn = dict(c.execute('SELECT id, tradition FROM narrator'))
pop = dict(c.execute('SELECT narrator_id, count(*) FROM chain_mention WHERE narrator_id IS NOT NULL GROUP BY 1'))
name2n = collections.defaultdict(set)
# only name forms with solid evidence: registry forms, or chain-observed forms seen at least 3 times
for nid, nn in c.execute("SELECT narrator_id, norm FROM narrator_name WHERE norm IS NOT NULL AND length(norm)<=70 AND (type!='observed' OR observed_count>=3)"): name2n[nn].add(nid)
ANON = {r[0] for r in c.execute("SELECT id FROM narrator WHERE std_name IN ('اسم مبهم','مبهم','رجل','امرأة') OR std_name LIKE 'اسم مبهم%'")}
ANON_WORDS = re.compile(r'رجل|رجال|بعض|شيخ|مشيخ|امرأ|مرأ|مبهم|ناس|اهل|قوم|فلان|احد|غير')
edge = {}; edgeA = {}
for s, t, n, na in c.execute('SELECT student, teacher, n_hadith, n_tier_a FROM narrator_edge'): edge[(s, t)] = n; edgeA[(s, t)] = na or 0
log(f'narrators with death year {len(death):,} | name forms {len(name2n):,} | edges {len(edge):,}')
W = dict(pop=0.25, eA=2.2, eAll=0.6, chron=-3.0, era=0.0, co=0.0)   # era/co features tested: no gain, disabled
def _learn_era():
    import statistics
    ids = [r[0] for r in c.execute("SELECT id FROM hadith WHERE chain_tier='A' LIMIT 30000")]; by = collections.defaultdict(list)
    for k in range(0, len(ids), 5000):
        chunk = ids[k:k + 5000]; ph = ','.join('?' * len(chunk)); cur = collections.defaultdict(list)
        for hid, pos, nid in c.execute(f"SELECT hadith_id,pos,narrator_id FROM chain_mention WHERE hadith_id IN ({ph}) AND id_method='source_annotation_kg' ORDER BY hadith_id,pos", chunk): cur[hid].append(nid)
        for hid, ns in cur.items():
            for i, nid in enumerate(ns):
                if nid in death: by[min(len(ns) - 1 - i, 5)].append(death[nid])
    return {k: (statistics.mean(v), max(statistics.pstdev(v), 25.0)) for k, v in by.items() if len(v) > 50}
ERA = _learn_era(); log('era (mean death year, sd) by position from end:', {k: (round(m), round(sd)) for k, (m, sd) in sorted(ERA.items())})
def cands(surface):
    """union of candidates over all spelling variants of the surface (not only the first variant that has a hit)"""
    anon_ok = bool(ANON_WORDS.search(norm(surface))); out = []
    for k in keys(surface):
        for x in name2n.get(k, ()):
            if (anon_ok or x not in ANON) and x not in out: out.append(x)
    return out
def score(cn, prev, nxt, loo=None, true=None, kend=None, members=()):
    """loo = (student, teacher) pair to subtract one count from (leave-one-out evaluation)"""
    s = W['pop'] * math.log1p(max(0, pop.get(cn, 0) - (1 if cn == true else 0)))
    for pair in ((prev, cn), (cn, nxt)):
        if pair[0] is None or pair[1] is None: continue
        ea = edgeA.get(pair, 0); e = edge.get(pair, 0)
        if loo is not None and pair in loo and cn == true: ea -= 1; e -= 1
        s += W['eA'] * math.log1p(max(ea, 0)) + W['eAll'] * math.log1p(max(e, 0))
    for m in members:                                              # links to ANY other narrator of the same chain (not only the neighbours)
        if m == cn or m == prev or m == nxt: continue
        e2 = edgeA.get((cn, m), 0) + edgeA.get((m, cn), 0)
        if loo is not None and cn == true: e2 = max(0, e2 - 0)
        if e2: s += W['co'] * math.log1p(e2)
    d = death.get(cn)
    if d is not None and kend is not None and min(kend, 5) in ERA:
        mu, sd = ERA[min(kend, 5)]; s += W['era'] * max(-4.0, -0.5 * ((d - mu) / sd) ** 2)
    if d is not None:
        if prev is not None and death.get(prev) is not None and d > death[prev] + 10: s += W['chron']          # teacher died long after the student
        if nxt is not None and death.get(nxt) is not None and death[nxt] > d + 10: s += W['chron']
        if prev is not None and death.get(prev) is not None and death[prev] - d > 150: s += W['chron'] / 2         # implausibly large gap
    return s
def rank(surface, prev, nxt, loo=None, true=None, kend=None, members=()):
    cs = cands(surface)
    if not cs: return []
    r = sorted(((score(x, prev, nxt, loo, true, kend, members), x) for x in cs), reverse=True)
    return r

d2norm = norm
TRUST = ('source_annotation_kg', 'linker_unique', 'name_lookup_unique', 'linker_context')
if MODE == 'eval':
    random.seed(5)
    ids = [r[0] for r in c.execute("SELECT id FROM hadith WHERE chain_tier='A'")]; random.shuffle(ids); ids = ids[:40000]
    res = []; base = 0; n = 0; abst = collections.defaultdict(lambda: [0, 0])
    for k in range(0, len(ids), 5000):
        chunk = ids[k:k + 5000]; ph = ','.join('?' * len(chunk))
        by = collections.defaultdict(list)
        for hid, pos, surf, nid, meth in c.execute(f'SELECT hadith_id,pos,surface,narrator_id,id_method FROM chain_mention WHERE hadith_id IN ({ph}) ORDER BY hadith_id,pos', chunk): by[hid].append((pos, surf, nid, meth))
        for hid, ms in by.items():
            for i, (pos, surf, nid, meth) in enumerate(ms):
                if nid is None or meth not in TRUST or not surf: continue
                cs = cands(surf)
                if len(cs) < 2 or nid not in cs: continue
                prev = ms[i - 1][2] if i > 0 and ms[i - 1][3] in TRUST else None
                nxt = ms[i + 1][2] if i + 1 < len(ms) and ms[i + 1][3] in TRUST else None
                loo = {(prev, nid), (nid, nxt)}
                mem = [x[2] for j, x in enumerate(ms) if j != i and x[3] in TRUST and x[2]]; r = rank(surf, prev, nxt, loo, nid, len(ms) - 1 - i, mem); best = r[0][1]; margin = r[0][0] - r[1][0]
                n += 1; ok = best == nid
                pp = sorted(cs, key=lambda x: -(pop.get(x, 0) - (1 if x == nid else 0)))[0]; base += (pp == nid)
                has_ctx = prev is not None or nxt is not None
                res.append((ok, margin, has_ctx, len(cs), min(len(d2norm(surf).split()), 3)))
    log(f'ambiguous trusted mentions tested: {n:,} | popularity-only baseline accuracy: {base/n:.1%} | rescoring accuracy: {sum(r[0] for r in res)/n:.1%}')
    for lo, hi in ((0, 1), (1, 3), (3, 5), (5, 6), (6, 7), (7, 8), (8, 10), (10, 12), (12, 15), (15, 20), (20, 999)):
        sel = [r for r in res if lo <= r[1] < hi]
        if sel: log(f'   margin [{lo},{hi}): n={len(sel):6,} accuracy {sum(r[0] for r in sel)/len(sel):.1%}')
    for nt in (1, 2, 3):
        for thr in (5, 7, 10, 12, 15, 20, 25):
            sel = [r for r in res if r[4] == nt and r[1] >= thr]
            if sel: log(f'   {nt}-word names, margin >= {thr:2d}: n={len(sel):7,} ({len(sel)/max(1,sum(1 for r in res if r[4]==nt)):.0%} of that length) accuracy {sum(r[0] for r in sel)/len(sel):.2%}')
    for thr in (0, 1, 3, 5, 6, 7, 8, 10, 12, 15, 20):
        sel = [r for r in res if r[1] >= thr]; log(f'   answer only if margin >= {thr}: coverage {len(sel)/n:.1%} accuracy {sum(r[0] for r in sel)/len(sel):.1%}')

if MODE == 'apply':
    MARGIN = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    TARGET = ('name_lookup_ambiguous', 'linker_prior_only', 'linker_prior_only+backoff')
    CTX = ('source_annotation_kg', 'source_annotation_thaqalayn', 'linker_unique', 'linker_unique+backoff', 'name_lookup_unique', 'name_lookup_unique_v2', 'linker_context', 'linker_context+backoff', 'surgery_disambiguated', 'manual_gold')
    c.executescript('CREATE TABLE IF NOT EXISTS surgery_log(step TEXT, kind TEXT, key TEXT, old TEXT, new TEXT);')
    hids = [r[0] for r in c.execute("SELECT DISTINCT hadith_id FROM chain_mention WHERE id_method IN (%s)" % ','.join('?' * len(TARGET)), TARGET)]
    log(f'hadith with guessed mentions: {len(hids):,} | margin threshold {MARGIN}')
    upd = []; stat = collections.Counter(); logrows = []
    def conf(margin): return 0.95 if margin >= 5 else 0.8 if margin >= 3 else 0.65 if margin >= 2 else 0.6 if margin >= 1 else 0.3
    for k in range(0, len(hids), 5000):
        chunk = hids[k:k + 5000]; ph = ','.join('?' * len(chunk)); by = collections.defaultdict(list)
        for rid, hid, pos, surf, nid, meth in c.execute(f'SELECT rowid,hadith_id,pos,surface,narrator_id,id_method FROM chain_mention WHERE hadith_id IN ({ph}) ORDER BY hadith_id,pos', chunk): by[hid].append([rid, surf, nid, meth])
        for hid, ms in by.items():
            for sweep in (0, 1):
                for i, m in enumerate(ms):
                    rid, surf, nid, meth = m
                    if meth not in TARGET or not surf: continue
                    prev = ms[i - 1][2] if i > 0 and ms[i - 1][3] in CTX else None
                    nxt = ms[i + 1][2] if i + 1 < len(ms) and ms[i + 1][3] in CTX else None
                    mem = [x[2] for j, x in enumerate(ms) if j != i and x[3] in CTX and x[2]]
                    r = rank(surf, prev, nxt, None, None, len(ms) - 1 - i, mem)
                    if len(r) == 0: stat['no_candidates'] += 1; continue
                    best = r[0][1]; margin = (r[0][0] - r[1][0]) if len(r) > 1 else 99
                    if margin >= MARGIN:
                        stat['changed' if best != nid else 'confirmed'] += 1
                        alts = [x[1] for x in r[1:4]]
                        upd.append((best, 'surgery_disambiguated', conf(margin), str(alts).replace("'", '"'), rid))
                        logrows.append(('fix_02', 'narrator_id', rid, nid, best)); m[2] = best; m[3] = 'surgery_disambiguated'
                    elif sweep == 1:
                        stat['low_margin_kept'] += 1; upd.append((nid, meth, 0.3, None, rid)); m[3] = meth
        if k % 50000 == 0: log(f'  {k:,}/{len(hids):,} hadith | {dict(stat)}')
    log('result:', dict(stat))
    c.executemany("UPDATE chain_mention SET narrator_id=?, id_method=?, id_confidence=?, alternatives=COALESCE(?, alternatives) WHERE rowid=?", upd)
    c.executemany('INSERT INTO surgery_log VALUES(?,?,?,?,?)', logrows[:300000])
    db.commit(); log('committed', len(upd), 'updates')
