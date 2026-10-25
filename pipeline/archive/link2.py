import sys, collections, time, math, re, csv, ast, gc, os
from array import array
sys.path.insert(0, '<WORKDIR>')
import numpy as np
from link_lib import *
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:5.0f}s]', *a, flush=True)
K = 12; EDGE = 3.0; PAIRW = 0.9; PRIOR_W = 0.6
# ---------------- 1. profiles -> compact tables --------------
P = load_profiles(); idx, first = build_index(P); vocab = set(w for k in idx for w in k.split())
death = {}; grade = {}; teach = {}; stud = {}; deg = {}; fullkey = {}; TOKS = {}
for i, p in P.items():
    m = re.search(r'(\d{1,4})', str(p.get('death') or ''))
    if m and 1 <= int(m.group(1)) <= 1500: death[i] = int(m.group(1))
    grade[i] = p['grade_en']; t = p.get('teachers') or []; s_ = p.get('students') or []
    if t: teach[i] = frozenset(t)
    if s_: stud[i] = frozenset(s_)
    deg[i] = len(t) + len(s_); fullkey[i] = norm2(p['full_name']); ts = set()
    for fld in ('full_name', 'kunya', 'laqab', 'nasab'):
        v = p.get(fld)
        if v and v != '-': ts |= set(norm2(v).replace('ابن', 'بن').split())
    TOKS[i] = frozenset(ts)
del P; gc.collect(); log('profiles', len(deg))
EMPTY = frozenset()
def pop0(c): return 1.0 + math.log1p(deg[c]) + (0.5 if grade[c] in ('companion', 'reliable', 'mostly_reliable') else 0.0)
# ---------------- 2. candidates ------------------------------
ANON = {'من','بعض','رجل','رجلا','عمن','شيخ','شيخا','رجال','احد','اهل','قوم','امراه','ناس','غير','فلان','انسان','ثقه','اصحاب','جماعه'}
REL = {'ابيه','ابوه','اباه','ابيها','ابي','جده','جدي','جدها','عمه','عمي','اخيه','امه','ابنه','عمها','خاله','ابوها','جدتها','ابيهم','اخوه','عمهم','جد','ابا','عنه','عنها'}
def cands0(key):
    t = key.split()
    if not t: return [], 'empty'
    if t[0] in ANON: return [], 'anon'
    if len(t) <= 2 and t[0] in REL: return [], 'rel'
    if key in idx: return sorted(idx[key]), 0
    t2 = [w[:-1] if (w.endswith('ا') and len(w) > 2 and w not in vocab and w[:-1] in vocab) else w for w in t]
    if len(t2[0]) > 2 and t2[0][0] in 'وف' and t2[0] not in vocab and t2[0][1:] in vocab: t2[0] = t2[0][1:]
    k2 = ' '.join(t2)
    if k2 != key and k2 in idx: return sorted(idx[k2]), 1
    for drop in range(1, min(4, len(t2) - 1)):
        k3 = ' '.join(t2[:len(t2) - drop])
        if len(t2) - drop >= 2 and k3 in idx: return sorted(idx[k3]), 1 + drop
    if len(t2) >= 3 and t2[0] in ('ابو', 'ابن', 'ام'):
        k3 = ' '.join(t2[1:])
        if k3 in idx: return sorted(idx[k3]), 5
    if len(t2) == 1 and t2[0] in idx: return sorted(idx[t2[0]]), 1
    return [], -1
def cands(key):
    c, l = cands0(key)
    if isinstance(l, str) or not c: return c, l
    kt = set(key.replace('ابن', 'بن').split()); f = [x for x in c if kt <= TOKS[x]]
    return (f, l) if f else ([], -1)
# ---------------- 3. stream chains (compact) -----------------
def stream_chains():
    """yields (tag, src_row, book, num, raw_names) in a fixed order"""
    with open(S + 'sanadset.csv', encoding='utf-8', newline='') as f:
        r = csv.reader(f); next(r)
        for i, row in enumerate(r, 2):
            if row[4].strip() == 'No SANAD': continue
            try: names = ast.literal_eval(row[4])
            except Exception: continue
            yield ('orig', i, row[1], row[2], names)
    with open(S + 'nosanad_parsed_v3.csv', encoding='utf-8-sig', newline='') as f:
        r = csv.reader(f); next(r)
        for row in r:
            if row[8] != 'parsed': continue
            yield ('nosanad', int(row[0]), row[1], row[2], ast.literal_eval(row[5]))
key_id = {}; keys = []; kc = []; klev = []
flat = array('i'); off = array('q', [0])
for tag, sr, bk, nm, names in stream_chains():
    for n in names:
        k = norm2(n)
        if k not in key_id:
            key_id[k] = len(keys); keys.append(k); c, l = cands(k); kc.append(c); klev.append(l)
        flat.append(key_id[k])
    off.append(len(flat))
NCH = len(off) - 1; del key_id, idx, vocab; gc.collect()
log('chains', NCH, 'mentions', len(flat), 'keys', len(keys))
# ---------------- 4. model -----------------------------------
pop = {c: pop0(c) for c in deg}
cl = []; lp = []
def prep():
    global cl, lp
    cl = []; lp = []
    for k, cs in enumerate(kc):
        if isinstance(klev[k], str) or not cs: cl.append([None]); lp.append(np.zeros(1)); continue
        cs2 = sorted(cs, key=lambda c: -pop[c])[:K]; w = np.array([pop[c] for c in cs2])
        cl.append(cs2); lp.append(PRIOR_W * np.log(w / w.sum()) - 0.3 * min(klev[k], 4))
prep()
pair = collections.Counter()
def tp(x, y, own):
    if x is None or y is None: return 0.0
    if x == y: return -4.0
    s = 0.0
    if y in teach.get(x, EMPTY) or x in stud.get(y, EMPTY): s += EDGE
    c = pair.get((x, y), 0) - own.get((x, y), 0)
    if c > 0: s += PAIRW * math.log1p(c)
    dx = death.get(x); dy = death.get(y)
    if dx and dy:
        if dy > dx + 25: s -= 2.5
        elif dx - dy > 100: s -= 1.5
        elif 0 <= dx - dy <= 70: s += 0.3
    return s
def decode(ck, own):
    L = len(ck); cll = [cl[k] for k in ck]
    if all(len(c) == 1 for c in cll): return [(c[0], 1.0, 1) for c in cll]
    em = [lp[k] for k in ck]; al = [em[0]]; T = []
    for i in range(L - 1):
        M = np.array([[tp(x, y, own) for y in cll[i + 1]] for x in cll[i]]); T.append(M)
        al.append(em[i + 1] + np.logaddexp.reduce(al[i][:, None] + M, axis=0))
    be = [None] * L; be[L - 1] = np.zeros(len(cll[L - 1]))
    for i in range(L - 2, -1, -1): be[i] = np.logaddexp.reduce(T[i] + (em[i + 1] + be[i + 1])[None, :], axis=1)
    out = []; pick = []
    for i in range(L):
        z = al[i] + be[i]; z = np.exp(z - z.max()); z /= z.sum(); j = int(z.argmax()); pick.append(j); out.append([cll[i][j], float(z[j]), 0])
    for i in range(L):
        if len(cll[i]) == 1: out[i][2] = 1; continue
        sup = 0
        for a, b, M in ((i - 1, i, T[i - 1] if i > 0 else None), (i, i + 1, T[i] if i < L - 1 else None)):
            if M is None: continue
            x, y = cll[a][pick[a]], cll[b][pick[b]]
            if x is not None and y is not None and (y in teach.get(x, EMPTY) or x in stud.get(y, EMPTY) or pair.get((x, y), 0) - own.get((x, y), 0) > 0): sup = 1
        out[i][2] = sup
        if not sup: out[i][1] = min(out[i][1], 0.5)
    return [tuple(o) for o in out]
# pass 0
for n in range(NCH):
    ck = flat[off[n]:off[n + 1]]
    for a, b in zip(ck, ck[1:]):
        if len(cl[a]) == 1 and len(cl[b]) == 1 and cl[a][0] is not None and cl[b][0] is not None: pair[(cl[a][0], cl[b][0])] += 1
log('pass0 pairs', len(pair))
# pass 1 (decisions stored as flat arrays)
p1id = array('i', [-1]) * len(flat); p1cf = array('f', [0.0]) * len(flat); newpair = collections.Counter(); mention = collections.Counter()
for n in range(NCH):
    a0, a1 = off[n], off[n + 1]; out = decode(flat[a0:a1], {})
    for j, (c, cf, ev) in enumerate(out):
        p1id[a0 + j] = -1 if c is None else c; p1cf[a0 + j] = cf
        if c is not None and cf >= 0.7: mention[c] += 1
    for (a, ca, _), (b, cb, _) in zip(out, out[1:]):
        if a is not None and b is not None and ca >= 0.8 and cb >= 0.8: newpair[(a, b)] += 1
    if n % 100000 == 0: log('pass1', n)
pair = newpair
for c in pop: pop[c] = 0.5 * pop0(c) + 0.3 * math.sqrt(mention.get(c, 0)) + 0.1
prep(); del mention; gc.collect(); log('pass1 done; confident pairs', len(pair))
# pass 2 + streaming output
FATHER = {'ابيه','ابوه','اباه','ابي','ابيها','ابوها','ابيهم','ابا'}
def father_of(x):
    t = fullkey[x].split()
    if 'بن' in t[:-1]: return t[t.index('بن') + 1]
w = csv.writer(open(S + 'sanadset_linked_v2.csv', 'w', encoding='utf-8-sig', newline=''))
w.writerow(['source','src_row','Book','Num_hadith','Narrators_raw','Rijal_ids','Link_conf','Link_method'])
meth = collections.Counter(); n = 0
for tag, sr, bk, nm, names in stream_chains():
    a0, a1 = off[n], off[n + 1]; ck = flat[a0:a1]
    if len(names) != len(ck): log('LENGTH MISMATCH at chain', n); sys.exit(1)
    prev = [(p1id[a0 + j], p1cf[a0 + j]) for j in range(a1 - a0)]; own = collections.Counter()
    for (a, ca), (b, cb) in zip(prev, prev[1:]):
        if a >= 0 and b >= 0 and ca >= 0.8 and cb >= 0.8: own[(a, b)] += 1
    out = decode(ck, own); ids = []; cf = []; mt = []
    for i, (k, (c, conf, ev)) in enumerate(zip(ck, out)):
        lev = klev[k]; nc = len(cl[k])
        if lev == 'anon': ids.append(None); cf.append(0); mt.append('anonymous')
        elif lev == 'rel':
            m = 'relative_unresolved'; cid = None; cc = 0
            if i > 0 and keys[k] in FATHER and out[i - 1][0] is not None and out[i - 1][1] >= 0.5:
                x = out[i - 1][0]; fn = father_of(x)
                if fn:
                    ms = [t for t in teach.get(x, EMPTY) if t in fullkey and fullkey[t].split()[:1] == [fn]]
                    if len(ms) == 1: cid, cc, m = ms[0], 0.9, 'relative_father'
            ids.append(cid); cf.append(cc); mt.append(m)
        elif c is None: ids.append(None); cf.append(0); mt.append('unmatched')
        else:
            ids.append(c); cf.append(round(conf, 3)); m = ('unique' if nc == 1 else 'context' if ev else 'prior_only')
            if lev != 0 and nc >= 1: m += '+backoff'
            mt.append(m)
        meth[mt[-1]] += 1
    w.writerow([tag, sr, bk, nm, repr(names), repr(ids), repr(cf), repr(mt)]); n += 1
    if n % 100000 == 0: log('pass2', n)
tot = sum(meth.values()); log('DONE', n, 'chains')
for k, v in meth.most_common(): print(f'  {k:24s} {v:9d} {v/tot:6.1%}')
