"""Chain-parsing RISK model.  Predicts, for every hadith, whether the database's transmitter list is wrong, from signals that do not need the labels:
  structural: number of chain connectors (حدثنا ثنا أخبرنا عن ح ...) in the chain part vs number of parsed mentions, surfaces that contain connectors, very long / very short surfaces,
              text between the last mention and the matn start, chain length, tier / tradition / book family
  agreement : the joint tagger's narrator spans (labels/joint_pred.db) vs the database mentions: matched, database-only, tagger-only, lowest tagger probability
Target (training): the database list is NOT 'tolerant-right' against Claude's labelled list (fix_40 tol_ok).  HistGradientBoosting, 5-fold CV on the labelled hadith.
  python pipeline/fix_41_chain_risk.py cv        # recall of wrong chains vs share of hadith sent to Claude
  python pipeline/fix_41_chain_risk.py fit       # models/chain_risk.pkl
  python pipeline/fix_41_chain_risk.py score     # writes labels/chain_risk.db (hadith_id, risk) for every chained hadith"""
from paths import *
from labels_lib import plain
from fix_33_joint_data import build
import sqlite3, sys, re, json, random, pickle, os, collections, time
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
CONN = set('حدثنا حدثني حدثنى ثنا نا اخبرنا اخبرني اخبرنى انا انبانا انبا انبأنا اخبره حدثه ح عن قال قالا قالت يقول سمعت سمعنا'.split())
HEAVY = set('حدثنا حدثني حدثنى ثنا نا اخبرنا اخبرني اخبرنى انا انبانا انبا انبأنا'.split())
close = lambda a, B: any(abs(a - b) <= 3 for b in B)
def feats(text, ms, db, tag, tier, trad, book):
    """db: list of (start,end) of chain_no 1 mentions before ms; tag: list of (start,end,minp) tagger spans before ms"""
    chain = text[:ms]; toks = plain(chain)[0].split(); n_db = len(db)
    nh = sum(1 for t in toks if t in HEAVY); nc = sum(1 for t in toks if t == 'عن'); nharf = sum(1 for t in toks if t == 'ح')
    f = {'n_db': n_db, 'n_heavy': nh, 'n_an': nc, 'n_h': nharf, 'conn_total': nh + nc, 'conn_minus_db': nh + nc - n_db, 'heavy_minus_db': nh - n_db,
         'chain_chars': min(ms, 3000), 'n_tokens': len(toks), 'tier_' + str(tier): 1, 'trad_' + str(trad): 1}
    f['book_' + re.sub(r'\W+', '', (book or '')[:12])] = 1
    surf = [plain(text[a:b])[0] for a, b in db]; w = [len(s.split()) for s in surf]
    f['max_words'] = max(w) if w else 0; f['min_words'] = min(w) if w else 0; f['n_one_word'] = sum(1 for x in w if x == 1)
    f['surf_has_conn'] = sum(1 for s in surf if any(t in CONN or t == 'ح' for t in s.split()))
    f['surf_has_h'] = sum(1 for s in surf if 'ح' in s.split())
    last = max((b for a, b in db), default=0)
    gap = plain(text[last:ms])[0].split() if ms > last else []
    f['gap_words'] = min(len(gap), 30); f['gap_has_heavy'] = int(any(t in HEAVY for t in gap)); f['gap_has_an'] = int('عن' in gap)
    first = min((a for a, b in db), default=ms); pre = plain(text[:first])[0].split()
    f['pre_words'] = min(len(pre), 20)
    if tag is not None:
        ts = [a for a, b, p in tag]; ds = [a for a, b in db]
        f['n_tag'] = len(ts); f['tag_minus_db'] = len(ts) - n_db
        f['matched'] = sum(close(a, ts) for a in ds); f['db_only'] = n_db - f['matched']; f['tag_only'] = sum(1 for a in ts if not close(a, ds))
        f['tag_minp'] = min((p for a, b, p in tag), default=1.0); f['tag_only_hi'] = sum(1 for a, b, p in tag if not close(a, ds) and p >= 0.9)
        f['same'] = int(f['db_only'] == 0 and f['tag_only'] == 0)
    return f
def tol_right(pred, gold, toks, offs):
    if all(close(a, pred) for a in gold) and all(close(b, gold) for b in pred): return True
    pm = [b for b in pred if not close(b, gold)]; gm = [a for a in gold if not close(a, pred)]
    if len(pm) + len(gm) != 1: return False
    x = pm[0] if pm else gm[0]
    if x != max(pred if pm else gold): return False
    k = max((i for i, (a, b) in enumerate(offs) if a < x), default=None)
    prev = plain(toks[k])[0].strip() if k is not None else ''
    return prev not in set('عن ثنا نا حدثنا حدثني اخبرنا اخبرني انا انبانا انبا حدثنى اخبرنى ح و'.split())
def training_set():
    pairs = [('labels/' + a, 'labels/' + b) for a, b in (('pilot', 'pilot_out'), ('wave1', 'wave1_out'), ('defects', 'defects_out'), ('unparsed', 'unparsed_out'), ('wave2', 'wave2_out'))]
    ex = build(pairs); c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); p = sqlite3.connect('labels/joint_pred.db')
    X = []; y = []; ids = []
    for e in ex:
        h = e['id']; r = c.execute('select text,matn_start,chain_tier,tradition,book from hadith where id=?', (h,)).fetchone()
        if not r or r[1] is None: continue
        text, ms, tier, trad, book = r
        db = [(a, b) for a, b in c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<?', (h, ms + 3))]
        pr = p.execute('select spans from pred where hadith_id=?', (h,)).fetchone()
        tag = [(a, b, mp) for a, b, mp in json.loads(pr[0]) if a < ms + 3] if pr else None
        gold = [a for a, b in e['spans'] if a < e['ms'] + 3]
        right = tol_right([a for a, b in db], gold, e['tokens'], e['offs'])
        X.append(feats(text, ms, db, tag, tier, trad, book)); y.append(0 if right else 1); ids.append(h)
    return X, np.array(y), ids
def mk(): return HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)
if __name__ == '__main__':
    from sklearn.feature_extraction import DictVectorizer
    if MODE in ('cv', 'fit'):
        X, y, ids = training_set(); print(len(y), 'hadith; database list wrong (tolerant):', int(y.sum()), f'({y.mean():.1%})', flush=True)
        dv = DictVectorizer(sparse=False); M = dv.fit_transform(X)
        if MODE == 'cv':
            idx = list(range(len(y))); random.seed(0); random.shuffle(idx); pr = np.zeros(len(y))
            for f in range(5):
                te = idx[f::5]; tr = [i for i in idx if i not in set(te)]
                pr[te] = mk().fit(M[tr], y[tr]).predict_proba(M[te])[:, 1]
            order = np.argsort(-pr)
            for share in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
                k = int(len(y) * share); got = y[order[:k]].sum(); rest = y[order[k:]]
                print(f'  send top {share:.0%} to Claude: catches {got / y.sum():.1%} of the wrong chains; left unchecked {len(rest)} hadith, {rest.mean():.1%} of them wrong -> overall wrong after fixing ~ {rest.sum() / len(y):.1%}')
        else:
            os.makedirs('models', exist_ok=True); pickle.dump((mk().fit(M, y), dv), open('models/chain_risk.pkl', 'wb')); print('saved models/chain_risk.pkl')
    else:
        m, dv = pickle.load(open('models/chain_risk.pkl', 'rb')); c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); p = sqlite3.connect('labels/joint_pred.db')
        out = sqlite3.connect('labels/chain_risk.db'); out.execute('create table if not exists risk(hadith_id text primary key, risk real)')
        have = {r[0] for r in out.execute('select hadith_id from risk')}; t0 = time.time(); n = 0
        tagd = {}
        rows = c.execute("select id,text,matn_start,chain_tier,tradition,book from hadith where chain_tier in ('A','B','C') and matn_start is not null order by id").fetchall()
        buf = []
        for h, text, ms, tier, trad, book in rows:
            if h in have: continue
            db = [(a, b) for a, b in c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<?', (h, ms + 3))]
            pr = p.execute('select spans from pred where hadith_id=?', (h,)).fetchone()
            tag = [(a, b, mp) for a, b, mp in json.loads(pr[0]) if a < ms + 3] if pr else None
            buf.append((h, feats(text, ms, db, tag, tier, trad, book)))
            if len(buf) >= 5000:
                P = m.predict_proba(dv.transform([f for h, f in buf]))[:, 1]; out.executemany('insert or replace into risk values(?,?)', [(h, float(x)) for (h, f), x in zip(buf, P)]); out.commit(); n += len(buf); buf = []
                print(f'{n:,} {time.time() - t0:.0f}s', flush=True)
        if buf:
            P = m.predict_proba(dv.transform([f for h, f in buf]))[:, 1]; out.executemany('insert or replace into risk values(?,?)', [(h, float(x)) for (h, f), x in zip(buf, P)]); out.commit(); n += len(buf)
        print('scored', n)
