from paths import *
import sqlite3, re, json, collections, math, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
HM = OUT + ''
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
db = sqlite3.connect(HM + 'hadith_master.db'); c = db.cursor()
std = dict(c.execute('select id, std_name from narrator')); nsrc = dict(c.execute('select id, n_sources from narrator'))
name2n = collections.defaultdict(list)
for nid, nn in c.execute('select narrator_id, norm from narrator_name'):
    if nn: name2n[nn].append(nid)
teachers = collections.defaultdict(set); students = collections.defaultdict(set)
for s_, t_ in c.execute('select student, teacher from narrator_edge'): teachers[s_].add(t_); students[t_].add(s_)
for s_, t_ in c.execute('select student, teacher from narrator_edge_seed'): teachers[s_].add(t_); students[t_].add(s_)
log('names', len(name2n), '| students with known teachers', len(teachers))
REL = {'ابيه', 'ابوه', 'اباه', 'ابيها', 'ابوها', 'ابيهم', 'ابي', 'ابا'}
def keys(surface):
    t = norm(surface).split(); out = []
    if not t: return out
    def add(tt):
        k = ' '.join(tt)
        if k and k not in out: out.append(k)
    add(t)
    t1 = list(t)
    if len(t1[0]) > 2 and t1[0][0] == 'و': t1[0] = t1[0][1:]
    if t1[0] in ('ابا', 'ابي'): t1[0] = 'ابو'
    t1 = ['بن' if w in ('ابن',) and i > 0 else w for i, w in enumerate(t1)]
    add(t1)
    t2 = [w[:-1] if (len(w) > 3 and w.endswith('ا') and not w.endswith('ابا')) else w for w in t1]; add(t2)
    t3 = ['ابن' if (i == 0 and w == 'بن') else w for i, w in enumerate(t2)]; add(t3)
    return out
def father_name(nid):
    t = norm(std.get(nid, '')).split()
    if 'بن' in t[:-1]: return t[t.index('بن') + 1]
    return None
# ---- load every mention of every hadith that has at least one unresolved mention
rows = c.execute('''SELECT rowid, hadith_id, pos, surface, narrator_id FROM chain_mention
  WHERE hadith_id IN (SELECT DISTINCT hadith_id FROM chain_mention WHERE narrator_id IS NULL AND surface IS NOT NULL) ORDER BY hadith_id, pos''').fetchall()
log('mentions loaded:', len(rows))
upd = []; stat = collections.Counter(); cur_h = None; grp = []
def process(grp):
    ids = [r[4] for r in grp]; new = {}
    for sweep in (0, 1):
        for i, (rid, h, pos, surf, nid) in enumerate(grp):
            if ids[i] is not None or not surf: continue
            prev = ids[i - 1] if i > 0 else None; nxt = ids[i + 1] if i + 1 < len(grp) else None
            ns = norm(surf)
            if ns in REL and prev:
                f = father_name(prev)
                cand = [t for t in teachers.get(prev, ()) if f and norm(std.get(t, '')).split()[:1] == [f]]
                if len(cand) == 1: ids[i] = cand[0]; new[i] = (cand[0], 'relative_father_edges', 0.8, None); stat['relative_father_edges'] += 1
                continue
            cands = []
            for k in keys(surf):
                cands = list(dict.fromkeys(name2n.get(k, [])))
                if cands: break
            if not cands: stat['no_candidate'] += 1; continue
            if len(cands) == 1:
                ids[i] = cands[0]; new[i] = (cands[0], 'name_lookup_unique_v2', 0.85, None); stat['unique'] += 1; continue
            def score(cn):
                s = 0.2 * math.log1p(nsrc.get(cn, 1))
                if prev and cn in teachers.get(prev, ()): s += 3
                if nxt and nxt in teachers.get(cn, ()): s += 3
                return s
            ranked = sorted(cands, key=lambda x: -score(x)); best = ranked[0]; edge = score(best) >= 3
            if edge and (len(ranked) == 1 or score(best) - score(ranked[1]) >= 2.5):
                ids[i] = best; new[i] = (best, 'name_plus_graph_edges', 0.75, ranked[1:4]); stat['graph_edges'] += 1
            elif sweep == 1:
                ids[i] = None; new[i] = None; stat['ambiguous_left_open'] += 1
    for i, v in new.items():
        if v: upd.append((v[0], v[1], v[2], json.dumps(v[3]) if v[3] else None, grp[i][0]))
for r in rows:
    if r[1] != cur_h:
        if grp: process(grp)
        cur_h = r[1]; grp = []
    grp.append(r)
if grp: process(grp)
log('resolutions found:', len(upd), dict(stat))
c.executemany('UPDATE chain_mention SET narrator_id=?, id_method=?, id_confidence=?, alternatives=? WHERE rowid=?', upd); db.commit()
tot = c.execute('select count(*) from chain_mention').fetchone()[0]; nul = c.execute('select count(*) from chain_mention where narrator_id is null').fetchone()[0]
log(f'mentions without a narrator id now: {nul:,} of {tot:,} ({nul/tot:.1%})')
