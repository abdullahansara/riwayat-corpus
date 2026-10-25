import sys, collections, time, pickle, math, re, random
sys.path.insert(0, '<WORKDIR>')
import numpy as np
from link_lib import *
K = 12; CFG = dict(edge=3.0, pairw=0.9, prior_w=0.6, filt=True, sqrt_pop=True)
P = load_profiles()
death = {}; grade = {}; teach = {}; stud = {}; deg = {}; fullkey = {}
for i, p in P.items():
    m = re.search(r'(\d{1,4})', str(p.get('death') or ''))
    if m and 1 <= int(m.group(1)) <= 1500: death[i] = int(m.group(1))
    grade[i] = p['grade_en']; teach[i] = set(p.get('teachers') or []); stud[i] = set(p.get('students') or [])
    deg[i] = len(teach[i]) + len(stud[i]); fullkey[i] = norm2(p['full_name'])
    ts = set()
    for fld in ('full_name', 'kunya', 'laqab', 'nasab'):
        v = p.get(fld)
        if v and v != '-': ts |= set(norm2(v).replace('ابن', 'بن').split())
    toks_of = globals().setdefault('toks_of', {}); toks_of[i] = ts
def pop0(c): return 1.0 + math.log1p(deg[c]) + (0.5 if grade[c] in ('companion', 'reliable', 'mostly_reliable') else 0.0)
class Linker:
    def __init__(self, chains, keys, kc, klev):
        self.chains, self.keys, self.kc, self.klev = chains, keys, kc, klev
        self.pop = {c: pop0(c) for c in P}
        self.pair = collections.Counter(); self.own = {}
        self._prep()
    def _prep(self):
        self.cl = []; self.lp = []
        for k, cs in enumerate(self.kc):
            if isinstance(self.klev[k], str) or not cs: self.cl.append([None]); self.lp.append(np.zeros(1)); continue
            if CFG['filt']:
                kt = set(self.keys[k].replace('ابن', 'بن').split()); f = [c for c in cs if kt <= toks_of[c]]
                if f: cs = f
            cs = sorted(cs, key=lambda c: -self.pop[c])[:K]
            w = np.array([self.pop[c] for c in cs]); lp = CFG['prior_w'] * np.log(w / w.sum()) - 0.3 * min(self.klev[k], 4)
            self.cl.append(cs); self.lp.append(lp)
    def tp(self, x, y, own):
        if x is None or y is None: return 0.0
        if x == y: return -4.0
        s = 0.0
        if y in teach[x] or x in stud[y]: s += CFG['edge']
        c = self.pair.get((x, y), 0) - own.get((x, y), 0)
        if c > 0: s += CFG['pairw'] * math.log1p(c)
        dx = death.get(x); dy = death.get(y)
        if dx and dy:
            if dy > dx + 25: s -= 2.5
            elif dx - dy > 100: s -= 1.5
            elif 0 <= dx - dy <= 70: s += 0.3
        return s
    def decode(self, ck, own):
        L = len(ck); cl = [self.cl[k] for k in ck]; em = [self.lp[k] for k in ck]
        if all(len(c) == 1 for c in cl): return [(c[0], 1.0, 1) for c in cl]
        al = [em[0]]; T = []
        for i in range(L - 1):
            M = np.array([[self.tp(x, y, own) for y in cl[i + 1]] for x in cl[i]]); T.append(M)
            al.append(em[i + 1] + np.logaddexp.reduce(al[i][:, None] + M, axis=0))
        be = [None] * L; be[L - 1] = np.zeros(len(cl[L - 1]))
        for i in range(L - 2, -1, -1):
            be[i] = np.logaddexp.reduce(T[i] + (em[i + 1] + be[i + 1])[None, :], axis=1)
        out = []; pick = []
        for i in range(L):
            z = al[i] + be[i]; z = np.exp(z - z.max()); z /= z.sum(); j = int(z.argmax()); pick.append(j); out.append([cl[i][j], float(z[j]), 0])
        for i in range(L):                       # evidence: does the chosen candidate have an edge / corpus pair with a chosen neighbour?
            if len(cl[i]) == 1: out[i][2] = 1; continue
            sup = 0
            for a, b, M in ((i - 1, i, T[i - 1] if i > 0 else None), (i, i + 1, T[i] if i < L - 1 else None)):
                if M is None: continue
                x, y = cl[a][pick[a]], cl[b][pick[b]]
                if x is not None and y is not None and (y in teach[x] or x in stud[y] or self.pair.get((x, y), 0) - own.get((x, y), 0) > 0): sup = 1
            out[i][2] = sup
            if not sup: out[i][1] = min(out[i][1], 0.5)
        return [tuple(o) for o in out]
    def pass0(self):
        self.pair = collections.Counter()
        for ch in self.chains:
            ck = ch[4]
            for a, b in zip(ck, ck[1:]):
                if len(self.cl[a]) == 1 and len(self.cl[b]) == 1 and self.cl[a][0] is not None and self.cl[b][0] is not None:
                    self.pair[(self.cl[a][0], self.cl[b][0])] += 1
    def run(self, limit=None, thr=0.8):
        res = []; t0 = time.time(); newpair = collections.Counter(); mention = collections.Counter(); own_new = {}
        for n, ch in enumerate(self.chains[:limit]):
            ck = ch[4]; own = self.own.get(n, {})
            out = self.decode(ck, own); res.append(out)
            mine = collections.Counter()
            for (a, ca, _), (b, cb, _) in zip(out, out[1:]):
                if a is not None and b is not None and ca >= thr and cb >= thr: mine[(a, b)] += 1
            for pr, c in mine.items(): newpair[pr] += c
            if mine: own_new[n] = dict(mine)
            for c, cf, _ in out:
                if c is not None and cf >= 0.7: mention[c] += 1
            if n and n % 100000 == 0: print(' ', n, round(time.time() - t0), 's', flush=True)
        return res, newpair, own_new, mention
    def update(self, newpair, own_new, mention):
        self.pair = newpair; self.own = own_new
        for c in P: self.pop[c] = 0.5 * pop0(c) + (0.3 * math.sqrt(mention.get(c, 0)) if CFG['sqrt_pop'] else mention.get(c, 0)) + 0.1
        self._prep()
if __name__ == '__main__':
    chains, keys, kc, klev = pickle.load(open('link_stage1.pkl', 'rb'))
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    random.seed(1); sub = chains if lim is None else random.sample(chains, lim)
    L = Linker(sub, keys, kc, klev); t0 = time.time(); L.pass0(); print('pass0 pairs', len(L.pair), round(time.time() - t0), 's')
    res, newpair, own_new, mention = L.run(); print('pass1', round(time.time() - t0), 's')
    L.update(newpair, own_new, mention); res2, np2, on2, m2 = L.run(); print('pass2', round(time.time() - t0), 's')
    tot = ok = 0; ambig = hi = 0
    for ch, out in zip(sub, res2):
        for k, (c, cf, ev) in zip(ch[4], out):
            if len(L.cl[k]) > 1: ambig += 1; hi += cf >= 0.8
    print('ambiguous mentions', ambig, 'of which confident>=0.8:', hi)
