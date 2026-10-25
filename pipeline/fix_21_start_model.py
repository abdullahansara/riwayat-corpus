"""Phase 2 - matn START / END models (TARGET=start|end env).  Candidates = word boundaries in a window around the current DB boundary;
a linear model over hashed word/context/chain features scores them (features in boundary_lib.py).
  TARGET=start python pipeline/fix_21_start_model.py cv  LABEL_OUT_DIR ...     # grouped 5-fold cross-validation vs the DB baseline
  TARGET=start python pipeline/fix_21_start_model.py fit LABEL_OUT_DIR ...     # fit on all labels, save models/<target>_model.pkl"""
from paths import *
from labels_lib import load_labels
from boundary_lib import build
import sqlite3, sys, random, pickle, collections, os, glob, json
import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
MODE = sys.argv[1]; DIRS = sys.argv[2:]; TARGET = os.environ.get('TARGET', 'start')
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
ids = set()
for d in DIRS:
    for fn in glob.glob(os.path.join(d, 'chunk_*.jsonl')):
        for l in open(fn, encoding='utf-8'):
            if l.strip(): ids.add(json.loads(l)['id'])
texts = {}; dbms = {}; dbme = {}
for h, t, ms, me in c.execute('select id,text,matn_start,matn_end from hadith'):
    if h in ids: texts[h] = t; dbms[h] = ms; dbme[h] = me if me is not None else len(t)
labels = load_labels(DIRS, texts)
data = []; skip = collections.Counter()
for h, o in labels.items():
    if TARGET == 'start':
        if o.get('chain_status') != 'has_chain': skip['not has_chain'] += 1; continue
        anchor, lab, lower = dbms[h], o['matn_start'], 0
    else:
        anchor, lab, lower = dbme[h], o['matn_end'], (dbms[h] or 0)
    if lab is None: skip['label boundary not found'] += 1; continue
    if anchor is None: skip['db has no boundary'] += 1; continue
    ments = c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 order by start', (h,)).fetchall()
    b = build(texts[h], anchor, lab, ments, TARGET, lower)
    if not b or not any(b[1]): skip['label boundary outside candidate window'] += 1; continue
    data.append((h, b, abs(anchor - lab) <= 2, anchor))
print('usable', len(data), dict(skip))
hasher = FeatureHasher(n_features=2 ** 19, input_type='dict')
def fit(sub):
    X = hasher.transform([f for h, b, _, _ in sub for f in b[0]]); y = np.array([v for h, b, _, _ in sub for v in b[1]])
    m = LogisticRegression(C=0.5, max_iter=400, class_weight={0: 1, 1: 8}); m.fit(X, y); return m
def predict(m, b):
    p = m.predict_proba(hasher.transform(b[0]))[:, 1]; i = int(np.argmax(p)); return b[2][i], float(p[i])
if MODE == 'cv':
    random.seed(0); order = list(range(len(data))); random.shuffle(order); K = 5; conf = []
    for f in range(K):
        te_idx = set(order[f::K]); te = [data[i] for i in order[f::K]]; tr = [data[i] for i in order if i not in te_idx]
        m = fit(tr)
        for h, b, dbok, anchor in te:
            s, p = predict(m, b); conf.append((p, b[1][b[2].index(s)] == 1, dbok, h, s, anchor))
    print(f'model correct {sum(x[1] for x in conf)}/{len(data)} = {sum(x[1] for x in conf) / len(data):.3f} | DB correct {sum(x[2] for x in conf)}/{len(data)} = {sum(x[2] for x in conf) / len(data):.3f}')
    for th in (0.97, 0.95, 0.9, 0.8, 0.7):
        chg = [x for x in conf if x[0] >= th and abs(x[4] - x[5]) > 2]
        if chg: print(f'  ACTUAL CHANGES p>={th}: {len(chg)} ({len(chg) / len(conf):.1%} of hadith); right {sum(x[1] for x in chg) / len(chg):.3f}; DB was right in {sum(x[2] for x in chg)} of them')
    json.dump([(x[3], x[4], x[0], x[1], x[5]) for x in conf], open('labels/_cv_' + TARGET + '.json', 'w'))
else:
    m = fit(data); os.makedirs('models', exist_ok=True); pickle.dump((m, hasher), open('models/' + TARGET + '_model.pkl', 'wb')); print('saved models/' + TARGET + '_model.pkl on', len(data))
