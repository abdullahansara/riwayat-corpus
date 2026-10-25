"""Phase 4 - same-person classifier for pairs of narrator records with the same normalised name.
Trained on Claude verdicts (labels/pairs_out; 'unsure' excluded).  Features: death years, usage, tradition, source types, shared teachers/students,
co-occurrence in the same chain (a pair that appears together in one chain is almost never the same person), name length.
  python pipeline/fix_29_pair_model.py cv   |   fit   -> models/pair_model.pkl"""
from paths import *
from id_lib import norm
import sqlite3, sys, json, glob, os, random, pickle, math, collections
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import HistGradientBoostingClassifier
class PairCtx:
    def __init__(self, c):
        self.info = {i: (n, d, t) for i, n, d, t in c.execute('select id,std_name,death_year,tradition from narrator')}
        self.cnt = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
        self.src = collections.defaultdict(set)
        for i, s in c.execute('select narrator_id,source from narrator_source_id'): self.src[i].add(s)
        self.teach = collections.defaultdict(set); self.stud = collections.defaultdict(set)
        for s, t, n in c.execute('select student,teacher,n_hadith from narrator_edge'): self.teach[s].add(t); self.stud[t].add(s)
        self.c = c; self._h = {}
    def hadith(self, i):
        if i not in self._h:
            if len(self._h) > 20000: self._h.clear()          # bound memory
            self._h[i] = {r[0] for r in self.c.execute('select hadith_id from chain_mention where narrator_id=?', (i,))}
        return self._h[i]
def pair_feats(x, a, b):
    na, da, ta = x.info[a]; nb, db, tb = x.info[b]
    f = {'name_raw_equal': float(na == nb), 'n_words': len((na or '').split()), 'both_dead': float(bool(da and db)), 'one_dead': float(bool(da) != bool(db)),
         'death_diff': abs(da - db) if da and db else -1.0, 'death_diff_gt25': float(bool(da and db and abs(da - db) > 25)),
         'log_a': math.log1p(x.cnt.get(a, 0)), 'log_b': math.log1p(x.cnt.get(b, 0)), 'zero_use': float(min(x.cnt.get(a, 0), x.cnt.get(b, 0)) == 0), 'both_zero': float(max(x.cnt.get(a, 0), x.cnt.get(b, 0)) == 0),
         'trad_same': float(ta == tb), 'shia_sunni': float({ta, tb} == {'shia', 'sunni'})}
    for s in ('itq', 'kg', 'sh', 'thq', 'chains', 'hn'): f['src_' + s] = float(s in x.src[a]) + float(s in x.src[b])
    f['same_src_kinds'] = float(x.src[a] == x.src[b])
    sa, sb = x.teach[a], x.teach[b]; ua, ub = x.stud[a], x.stud[b]
    f['sh_teach'] = len(sa & sb); f['sh_stud'] = len(ua & ub); f['n_teach'] = len(sa) + len(sb); f['n_stud'] = len(ua) + len(ub)
    f['neigh_disjoint'] = float(len(sa) + len(ua) >= 2 and len(sb) + len(ub) >= 2 and not (sa & sb) and not (ua & ub))
    f['jac'] = len((sa | ua) & (sb | ub)) / max(1, len((sa | ua) | (sb | ub)))
    ha, hb = (x.hadith(a), x.hadith(b)) if f['zero_use'] == 0 else (set(), set())
    f['cooccur'] = len(ha & hb) if ha and hb else 0
    f['cooccur_any'] = float(f['cooccur'] > 0)
    try: f['id_gap'] = abs(int(a[1:]) - int(b[1:])) if abs(int(a[1:]) - int(b[1:])) < 50 else 50
    except Exception: f['id_gap'] = 50
    return f
def mk(): return HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_leaf_nodes=8, l2_regularization=2.0, random_state=0)
if __name__ == '__main__':
    MODE = sys.argv[1]
    c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True); x = PairCtx(c)
    items = {}
    for f in glob.glob('labels/pairs/chunk_*.json'):
        for it in json.load(open(f, encoding='utf-8')): items[it['pair_id']] = it
    V = {}
    for f in glob.glob('labels/pairs_out/chunk_*.jsonl'):
        for l in open(f, encoding='utf-8'):
            if l.strip():
                try: o = json.loads(l); V[o['pair_id']] = o
                except Exception: pass
    rows = [(p, pair_feats(x, items[p]['a']['id'], items[p]['b']['id']), int(o['verdict'] == 'same')) for p, o in V.items() if p in items]
    print('training pairs', len(rows), 'same', sum(r[2] for r in rows))
    dv = DictVectorizer(sparse=False); X = dv.fit_transform([r[1] for r in rows]); y = np.array([r[2] for r in rows])
    if MODE == 'cv':
        idx = list(range(len(rows))); random.seed(0); random.shuffle(idx); pr = np.zeros(len(rows))
        for f in range(5):
            te = idx[f::5]; tr = [i for i in idx if i not in set(te)]
            pr[te] = mk().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        for th in (0.7, 0.8, 0.9, 0.95):
            sel = pr >= th; print(f'  P(same)>={th}: {int(sel.sum())} pairs ({sel.mean():.1%}); truly same {y[sel].mean():.3f}')
        for th in (0.3, 0.1):
            sel = pr <= th; print(f'  P(same)<={th}: {int(sel.sum())} pairs; truly different {1 - y[sel].mean():.3f}')
        print('  note: unsure counted as not-same (merge only with evidence)')
    else:
        os.makedirs('models', exist_ok=True); pickle.dump((mk().fit(X, y), dv), open('models/pair_model.pkl', 'wb')); print('saved models/pair_model.pkl')
