"""Surgery step 04 - split mentions in which several narrators were merged into one span
(e.g. "عَبْدُ الرَّحِيمِ بْنُ سُلَيْمَانَ ، عَنْ لَيْثٍ ، عَنْ مُجَاهِدٍ ، قَالَ : كَانَ ابْنُ عُمَرَ").
A mention is split only when its surface contains real chain markers (عن / a transmission verb after a comma).
Each part is looked up in the narrator registry and ranked with the chooser of fix_02 (popularity, known links, death years).
  python pipeline/fix_04_split_merged.py            dry run (counts + examples, and a check on the gold hadith)
  python pipeline/fix_04_split_merged.py --apply    write (old rows kept in table removed_mention, step fix_04)"""
from paths import *
import sqlite3, re, sys, math, collections, json, time, importlib.util
APPLY = '--apply' in sys.argv
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
sp = importlib.util.spec_from_file_location('d2', PIPE + 'fix_02_disambiguate.py')
sys.argv_backup = sys.argv; sys.argv = [sys.argv[0], 'noop']                       # import helpers without running eval/apply
d2 = importlib.util.module_from_spec(sp); sp.loader.exec_module(d2); sys.argv = sys.argv_backup
db = d2.db; c = d2.c; norm = d2.norm
D = '[ً-ْٰـٓ-ٕ]'
VERBS = r'(?:حدثنا|حدثني|[أا]خبرنا|[أا]خبرني|[أا]خبرنيه|[أا]نبأنا|[أا]نبأ|[أا]نبأني|[أا]نبانا|[أا]نبا|ثنا|ثني|نا|[أا]نا|[أا]خبرناه|حدثناه|سمعت|قال|قالا|قالوا|يقول|يعني)'
SPLIT = re.compile(r'\s*[،,]\s*(?:و\s*)?(?:%s\s*[:،,]?\s*)*عن\s+|\s+عن\s+|\s*[،,]\s*(?:%s)\s*[:،,]?\s*' % (VERBS, VERBS))
MARK = re.compile(r'(?:^|\s)عن\s|[،,]\s*(?:و\s*)?' + VERBS + r'(?:\s|$)')
LEAD = re.compile(r'^\s*(?:و?(?:%s|كان|أن)(?=\s|$))?\s*[:،,]?\s*' % VERBS)
def strip_map(s):
    keep = [i for i, ch in enumerate(s) if not re.match(D, ch)]
    return ''.join(s[i] for i in keep), keep
def plain(s): return re.sub(D, '', s)
NAMEY = re.compile(r'(?:^|\s)(?:بن|ابن|بنت|أبو|أبي|ابا|أبا|أم|ام|بني)(?:\s|$)')
def looks_name(p):
    n = norm(p)
    if len(n.split()) > 12: return False
    return bool(d2.cands(p)) or bool(NAMEY.search(p if False else re.sub(D, '', p)))
log('helpers loaded')
targets = c.execute("""SELECT m.rowid, m.hadith_id, m.pos, m.start, m.end, m.surface, m.narrator_id, m.id_method FROM chain_mention m
                       WHERE m.start IS NOT NULL AND (m.surface LIKE '%،%' OR m.surface LIKE '%, %' OR m.surface LIKE '% عن %' OR m.surface LIKE '%عَنْ %' OR m.surface LIKE '%عَنِ %') AND length(m.surface)>25""").fetchall()
log(f'candidate mentions: {len(targets):,}')
plan = []; skipped = collections.Counter()
for rid, hid, pos, st, en, surf, nid, meth in targets:
    pl, keep = strip_map(surf)
    if not MARK.search(pl): skipped['no chain marker'] += 1; continue
    cuts = []; last = 0
    for m in SPLIT.finditer(pl):
        cuts.append((last, m.start())); last = m.end()
    cuts.append((last, len(pl)))
    out = []
    for a, b in cuts:
        seg = pl[a:b]; lm = LEAD.match(seg); a2 = a + (lm.end() if lm else 0)
        seg2 = pl[a2:b]; l = len(seg2) - len(seg2.lstrip(' ،,:')); a2 += l; seg2 = seg2.strip(' ،,:')
        if not seg2: continue
        oa = keep[a2]; ob = keep[a2 + len(seg2) - 1] + 1
        while ob < len(surf) and re.match(D, surf[ob]): ob += 1
        if looks_name(surf[oa:ob]): out.append((oa, ob, surf[oa:ob]))
    if len(out) < 2: skipped['fewer than 2 name parts'] += 1; continue
    plan.append((rid, hid, pos, st, en, surf, nid, meth, out))
log(f'mentions to split: {len(plan):,} into {sum(len(p[8]) for p in plan):,} parts | skipped {dict(skipped)}')
for p in plan[:4]: log('  ', plain(p[5])[:70], '=>', [plain(x[2])[:22] for x in p[8]])
gold = {json.loads(l)['hadith_id'] for l in open(PIPE + '../gold/gold_chains.jsonl', encoding='utf-8')}
log('gold hadith affected:', sorted({p[1] for p in plan if p[1] in gold}))
if not APPLY: sys.exit(0)

# ---- apply: build new mention rows per hadith, rank each part with its neighbours
c.executescript('CREATE TABLE IF NOT EXISTS removed_mention(hadith_id TEXT, pos INT, start INT, end INT, surface TEXT, narrator_id TEXT, id_method TEXT, step TEXT);')
byh = collections.defaultdict(list)
for p in plan: byh[p[1]].append(p)
n_new = 0
for k, (hid, ps) in enumerate(byh.items()):
    ms = c.execute('SELECT rowid,pos,start,end,surface,narrator_id,id_method,id_confidence,id_source_ref,alternatives,flags FROM chain_mention WHERE hadith_id=? ORDER BY pos', (hid,)).fetchall()
    rows = [dict(rid=r[0], start=r[2], end=r[3], surface=r[4], nid=r[5], meth=r[6], conf=r[7], ref=r[8], alt=r[9], flags=r[10]) for r in ms]
    split = {p[0]: p for p in ps}; new = []
    for r in rows:
        if r['rid'] not in split: new.append(r); continue
        p = split[r['rid']]; base = r['start']; parts = []
        for a, b, seg in p[8]:
            cs = d2.cands(seg); parts.append(dict(rid=None, start=base + a, end=base + b, surface=seg, nid=None, meth='surgery_split', cs=cs, conf=None, ref=None, alt=None, flags='split_from_merged'))
        # a part keeps the old id when that id is one of its candidates
        for q in parts:
            if p[6] in q['cs']: q['nid'] = p[6]; q['conf'] = 0.9
        new.extend(parts)
    for i, r in enumerate(new):            # resolve remaining parts left-to-right with neighbour context
        if r['rid'] is None and r['nid'] is None:
            prev = new[i - 1]['nid'] if i > 0 else None; nxt = new[i + 1]['nid'] if i + 1 < len(new) else None
            rk = d2.rank(r['surface'], prev, nxt)
            if rk:
                margin = (rk[0][0] - rk[1][0]) if len(rk) > 1 else 99
                r['nid'] = rk[0][1]; r['conf'] = 0.95 if margin >= 5 else 0.8 if margin >= 3 else 0.6 if margin >= 1 else 0.3
    for r in rows:
        if r['rid'] in split:
            c.execute("INSERT INTO removed_mention SELECT hadith_id,pos,start,end,surface,narrator_id,id_method,'fix_04' FROM chain_mention WHERE rowid=?", (r['rid'],))
    c.execute('DELETE FROM chain_mention WHERE hadith_id=?', (hid,))
    for i, r in enumerate(new, 1):
        c.execute('INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,id_source_ref,alternatives,flags) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (hid, i, r['start'], r['end'], r['surface'], r['nid'], r['meth'], r['conf'], r['ref'], r['alt'], r['flags']))
    n_new += len(new)
    c.execute('UPDATE hadith SET n_narrators=? WHERE id=?', (len(new), hid))
    if k % 20000 == 0: log(f'  {k:,}/{len(byh):,} hadith'); db.commit()
db.commit(); log(f'applied: {len(byh):,} hadith rewritten')
