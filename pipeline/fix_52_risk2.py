"""Risk model v2: target = 'a Claude re-parse differs from the DB chain' (what a re-parse tranche actually pays for), trained on the agent re-parses whose PRE-apply DB state
is still available (HadithMaster\\hadith_master.PRE_AUDIT_P0_20261023.db holds the Oct-12 state): labels/reparse_pilot_out + labels/reparse2_out.  Features = fix_41 feats() (structural + joint-tagger agreement).
  python pipeline/fix_52_risk2.py cv      # 5-fold CV: overall AUC, AUC inside the current risk>=0.8 band, top-quartile differ rate (accept: band AUC >= 0.68 and top-quartile >= 45%)
  python pipeline/fix_52_risk2.py fit     # models/chain_risk2.pkl
  python pipeline/fix_52_risk2.py score   # labels/chain_risk%s.db' % V + '(hadith_id, risk) for every chained hadith of the CURRENT db (resumable)"""
import sys, os
MODE = sys.argv[1]
V = os.environ.get('RISK_V', '2')      # '3' adds the tranche-1/2 agent outputs (pre-rewrite state from the backup) to the training set
from paths import *
from labels_lib import find, plain
import fix_41_chain_risk as R
import sqlite3, json, glob, os, pickle, random, time
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import roc_auc_score
BACKUP = OUT + 'hadith_master.PRE_AUDIT_P0_20261023.db'; CUR = OUT + 'hadith_master.db'
GOLD = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
def load_labels():
    pairs = [('labels/reparse_pilot_out', 'labels/reparse_pilot'), ('labels/reparse2_out', 'labels/reparse2')]
    if V == '3': pairs += [('labels/reparse3_out', 'labels/reparse3'), ('labels/reparse4g_out', 'labels/reparse4g')]
    b = sqlite3.connect('file:' + BACKUP + '?mode=ro', uri=True); p = sqlite3.connect('labels/joint_pred.db'); X = []; y = []; ids = []
    for od, cd in pairs:
        A = {}
        for f in glob.glob(os.path.join(od, 'chunk_*.jsonl')):
            for l in open(f, encoding='utf-8'):
                if l.strip():
                    try: o = json.loads(l); A[o['id']] = o
                    except Exception: pass
        for h, o in A.items():
            if h in GOLD or not o.get('transmitters'): continue
            r = b.execute('select text,matn_start,chain_tier,tradition,book from hadith where id=?', (h,)).fetchone()
            if not r or r[1] is None: continue
            text, ms, tier, trad, book = r
            pos = 0; sp = []; ok = True
            for t in o['transmitters']:
                q = find(text[:ms + 700][pos:], t['text'])
                if not q: ok = False; break
                sp.append((pos + q[0], pos + q[1])); pos += q[1]
            if not ok: continue
            db = [(a, e) for a, e in b.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<?', (h, ms + 3))]
            allm = [a for a, e in b.execute('select start,end from chain_mention where hadith_id=? and start is not null and start<?', (h, ms + 3))]
            differ = not (len(allm) == len(sp) and all(R.close(a, allm) for a, e in sp))
            pr = p.execute('select spans from pred where hadith_id=?', (h,)).fetchone()
            tag = [(a, e, mp) for a, e, mp in json.loads(pr[0]) if a < ms + 3] if pr else None
            X.append(R.feats(text, ms, db, tag, tier, trad, book)); y.append(int(differ)); ids.append(h)
    return X, np.array(y), ids
if MODE in ('cv', 'fit'):
    X, y, ids = load_labels(); print(len(y), 'labelled hadith; agent list differs from DB:', int(y.sum()), f'({y.mean():.1%})', flush=True)
    dv = DictVectorizer(sparse=False); M = dv.fit_transform(X)
    if MODE == 'cv':
        cur = dict(sqlite3.connect('labels/chain_risk.db').execute('select hadith_id,risk from risk')); cr = np.array([cur.get(h, 0.0) for h in ids])
        res = {}
        for seed in range(5):                       # repeated 5-fold to stabilise the small sample
            idx = list(range(len(y))); random.Random(seed).shuffle(idx); pr = np.zeros(len(y))
            for f in range(5):
                te = idx[f::5]; tr = [i for i in idx if i not in set(te)]
                pr[te] = R.mk().fit(M[tr], y[tr]).predict_proba(M[te])[:, 1]
            band = cr >= 0.8; top = pr[band] >= np.quantile(pr[band], 0.75)
            for k, v in (('auc_all', roc_auc_score(y, pr)), ('auc_band', roc_auc_score(y[band], pr[band])), ('topq_rate', y[band][top].mean()), ('rest_rate', y[band][~top].mean())): res.setdefault(k, []).append(v)
        print('current score: AUC all %.2f, AUC in band>=0.8 %.2f (n=%d, differ %.0f%%)' % (roc_auc_score(y, cr), roc_auc_score(y[cr >= 0.8], cr[cr >= 0.8]), (cr >= 0.8).sum(), 100 * y[cr >= 0.8].mean()))
        print({k: round(float(np.mean(v)), 3) for k, v in res.items()}, '-> accept' if np.mean(res['auc_band']) >= 0.68 and np.mean(res['topq_rate']) >= 0.45 else '-> REJECT (keep the current score)')
    else:
        pickle.dump((R.mk().fit(M, y), dv), open('models/chain_risk%s.pkl' % V, 'wb')); print('saved models/chain_risk2.pkl')
else:
    m, dv = pickle.load(open('models/chain_risk%s.pkl' % V, 'rb')); c = sqlite3.connect('file:' + CUR + '?mode=ro', uri=True); p = sqlite3.connect('labels/joint_pred.db')
    out = sqlite3.connect('labels/chain_risk%s.db' % V + ''); out.execute('create table if not exists risk(hadith_id text primary key, risk real)')
    have = {r[0] for r in out.execute('select hadith_id from risk')}; t0 = time.time(); n = 0; buf = []
    for h, text, ms, tier, trad, book in c.execute("select id,text,matn_start,chain_tier,tradition,book from hadith where chain_tier in ('A','B','C') and matn_start is not null order by id").fetchall():
        if h in have: continue
        db = [(a, e) for a, e in c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<?', (h, ms + 3))]
        pr = p.execute('select spans from pred where hadith_id=?', (h,)).fetchone(); tag = [(a, e, mp) for a, e, mp in json.loads(pr[0]) if a < ms + 3] if pr else None
        buf.append((h, R.feats(text, ms, db, tag, tier, trad, book)))
        if len(buf) >= 5000:
            P = m.predict_proba(dv.transform([f for h, f in buf]))[:, 1]; out.executemany('insert or replace into risk values(?,?)', [(h, float(x)) for (h, f), x in zip(buf, P)]); out.commit(); n += len(buf); buf = []; print(n, round(time.time() - t0), 's', flush=True)
    if buf:
        P = m.predict_proba(dv.transform([f for h, f in buf]))[:, 1]; out.executemany('insert or replace into risk values(?,?)', [(h, float(x)) for (h, f), x in zip(buf, P)]); out.commit(); n += len(buf)
    print('scored', n)
