"""Phase 3 - narrator ID ranker.  For each narrator mention, candidate narrators (id_lib.candidates) are scored by a gradient-boosted model
trained on the Claude labels (choice = a candidate id, or NONE).  Prediction = argmax candidate + its probability.
  python pipeline/fix_25_ranker.py cv  SAMPLE_DIR:LABEL_DIR ...      # e.g. labels/pilot:labels/pilot_out labels/wave1:labels/wave1_out
  python pipeline/fix_25_ranker.py fit SAMPLE_DIR:LABEL_DIR ...      # saves models/ranker.pkl"""
from paths import *
from id_lib import Ctx, candidates, feats
import sqlite3, sys, json, glob, os, random, pickle, collections
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import HistGradientBoostingClassifier
if __name__ == '__main__':
    MODE = sys.argv[1]; PAIRS = [a.split(':') for a in sys.argv[2:]]
    c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
    ctx = Ctx(c)
    items = {}; lab = {}
    for sd, ld in PAIRS:
        for f in glob.glob(os.path.join(sd, 'chunk_*.json')):
            for it in json.load(open(f, encoding='utf-8')): items[it['id']] = it
        for f in glob.glob(os.path.join(ld, 'chunk_*.jsonl')):
            for l in open(f, encoding='utf-8'):
                if l.strip():
                    o = json.loads(l); lab.setdefault(o['id'], o)
    rows = []   # (hadith, mention_key, cand, feats, y, db_correct_flag)
    stats = collections.Counter()
    for h, o in lab.items():
        it = items.get(h)
        if not it: continue
        L = {m['i']: m for m in o['mentions']}; M = it['mentions']
        meth = {r[0]: r[1] for r in c.execute('select start,id_method from chain_mention where hadith_id=?', (h,)) if r[0] is not None}
        for k, m in enumerate(M):
            l = L.get(m['i'])
            if not l or l['kind'] != 'narrator': continue
            prev_id = next((M[j]['cur_id'] for j in range(k - 1, -1, -1) if M[j]['cur_id']), None)
            next_id = next((M[j]['cur_id'] for j in range(k + 1, len(M)) if M[j]['cur_id']), None)
            cands = candidates(ctx, m['surface'], m['cur_id'], m['cur_guess'], prev_id)
            if not cands: stats['no candidates'] += 1; continue
            ch = l['choice']
            if ch != 'NONE' and ch not in cands: stats['label choice not among candidates'] += 1; continue
            stats['usable' + (' NONE' if ch == 'NONE' else '')] += 1
            for cd in cands:
                rows.append((h, (h, m['i']), cd, feats(ctx, m['surface'], cd, cands, m['cur_id'], m['cur_guess'], meth.get(m['start']), prev_id, next_id, it['tradition'], k, len(M)), int(cd == ch),
                             'asserted' if m['cur_id'] else 'guess' if m['cur_guess'] else 'none'))
    print('mentions', dict(stats), 'rows', len(rows))
    dv = DictVectorizer(sparse=False); X = dv.fit_transform([r[3] for r in rows]); y = np.array([r[4] for r in rows])
    keys = [r[1] for r in rows]; uniq = sorted(set(keys)); random.seed(0); random.shuffle(uniq); fold = {k: i % 5 for i, k in enumerate(uniq)}
    def mk(): return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)
    if MODE == 'cv':
        pred = {}
        for f in range(5):
            tr = np.array([fold[k] != f for k in keys]); te = ~tr
            m = mk().fit(X[tr], y[tr]); p = m.predict_proba(X[te])[:, 1]
            for r, pp in zip([r for r, t in zip(rows, te) if t], p): pred.setdefault(r[1], []).append((pp, r[2], r[4], r[5]))
        # per mention: top candidate vs truth.  truth NONE = no candidate has y=1
        res = []
        for k, v in pred.items():
            v.sort(reverse=True); top = v[0]; has_truth = any(x[2] for x in v)
            res.append((top[0], bool(top[2]), has_truth, top[3]))
        n = len(res); n_t = sum(1 for r in res if r[2])
        print(f'mentions {n}; with a labelled ID {n_t}; top-1 accuracy among those {sum(1 for r in res if r[1]) / n_t:.3f}')
        for th in (0.5, 0.7, 0.8, 0.9, 0.95):
            sel = [r for r in res if r[0] >= th]
            if sel: print(f'  p>={th}: {len(sel)} mentions ({len(sel) / n:.1%}); correct {sum(1 for r in sel if r[1]) / len(sel):.3f}; of which currently asserted/guess/none: {collections.Counter(r[3] for r in sel)}')
        for st in ('asserted', 'guess', 'none'):
            sub = [r for r in res if r[3] == st]
            for th in (0.8, 0.9):
                sel = [r for r in sub if r[0] >= th]
                if sel: print(f'  [{st}] p>={th}: {len(sel)} of {len(sub)}; correct {sum(1 for r in sel if r[1]) / len(sel):.3f}')
    else:
        m = mk().fit(X, y); os.makedirs('models', exist_ok=True); pickle.dump((m, dv), open('models/ranker.pkl', 'wb')); print('saved models/ranker.pkl')
