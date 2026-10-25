"""Narrated-frame classifier.  For a hadith whose matn_start lies after the last chain mention, the text between them (the 'gap') is either
 a quotation formula (سمعت رسول الله ﷺ يقول :) that stays out of the matn, or the opening of a narrated report (سألت ابن عباس عن ..., خرجنا مع ...) that belongs in it.
Trained on Claude labels (wave2, defects, unparsed: the frame-in-matn convention).  Apply: matn_start moves to the first word after the last mention + leading connectors.
  python pipeline/fix_37_frame_model.py cv | fit | pilot [N] [seed] | apply        (surgery_log step fix_37, flag frame_start)"""
from paths import *
from labels_lib import load_labels, plain
from boundary_metric import CONN, conn_only
import sqlite3, sys, re, json, glob, random, pickle, os, collections
import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'; P_INC = 0.9
c = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply'))
LEAD = re.compile(r'^[\s,،:؛"«»\-–.]*')
CHAINW = set('عن حدثنا حدثني ثنا نا اخبرنا اخبرني انا انبانا ح قال قالت يقول تقول عنه عنها ان انه انها ثم و'.split()) | CONN
def chain_like(text, e, limit):
    """a mention ending at e is a chain narrator when what follows is punctuation, a connector or a chain verb (not narrative words)"""
    rest = text[e:limit]; m = re.match(r'[\s]*([,،:؛.])', rest)
    if m: return True
    w = re.match(r'[\s]*(\S+)', rest)
    if not w: return True
    ww = plain(w.group(1))[0].strip()
    return (not ww) or ww in CHAINW or ww.lstrip('و') in CHAINW
def gap_of(text, ms):
    rows = c.execute('select end from chain_mention where hadith_id=? and coalesce(chain_no,1)=1 and start is not null and end<=? order by end desc limit 6', (HID[0], ms + 3)).fetchall()
    for (e,) in rows:
        if chain_like(text, e, ms): return e
    return rows[0][0] if rows else None
def advance(text, a, b):
    """first position in [a,b] after leading connector words / punctuation"""
    i = a + len(LEAD.match(text[a:b]).group(0))
    while i < b:
        m = re.match(r'\S+', text[i:b])
        if not m: break
        w = plain(m.group(0))[0].strip()
        if w and (w in CONN or w.lstrip('و') in CONN or w in ('ما',)): i += m.end(); i += len(LEAD.match(text[i:b]).group(0))
        elif not w: i += m.end()
        else: break
    return i
def feats(text, a, b, ms):
    gw = plain(text[a:b])[0].split(); mw = plain(text[ms:ms + 60])[0].split()[:4]; f = {}
    for w in gw: f['g_' + w] = 1
    for x, y in zip(gw, gw[1:]): f['gb_' + x + '_' + y] = 1
    for w in mw: f['m_' + w] = 1
    f['n_gap'] = min(len(gw), 20) / 20.0; f['first_' + (gw[0] if gw else '')] = 1; f['last_' + (gw[-1] if gw else '')] = 1
    f['has_sam3'] = int('سمعت' in gw or 'سمعنا' in gw); f['has_rasul'] = int('رسول' in gw)
    f['ends_yaqul'] = int(bool(gw) and gw[-1] in ('يقول', 'قال', 'تقول', 'قالت', 'قوله'))
    return f
H = FeatureHasher(2 ** 16)
def dataset():
    X = []; y = []; ids = []; V = {}
    for f in glob.glob('labels/gaps_out/chunk_*.jsonl'):
        for l in open(f, encoding='utf-8'):
            if l.strip():
                try: o = json.loads(l); V[o['id']] = o['label']
                except Exception: pass
    print('labels', collections.Counter(V.values()))
    for h, lab in V.items():
        if lab not in ('frame', 'formula'): continue
        text, ms = c.execute('select text,matn_start from hadith where id=?', (h,)).fetchone()
        HID[0] = h; le = gap_of(text, ms)
        if le is None or le >= ms: continue
        y.append(1 if lab == 'frame' else 0); X.append(feats(text, le, ms, ms)); ids.append(h)
    return X, np.array(y), ids
HID = [None]
if MODE in ('cv', 'fit'):
    X, y, ids = dataset(); print(len(y), 'examples; include-frame', int(y.sum()))
    M = H.transform(X)
    if MODE == 'cv':
        idx = list(range(len(y))); random.seed(0); random.shuffle(idx); pr = np.zeros(len(y))
        for f in range(5):
            te = idx[f::5]; tr = [i for i in idx if i not in set(te)]
            pr[te] = LogisticRegression(C=3, max_iter=400).fit(M[tr], y[tr]).predict_proba(M[te])[:, 1]
        for th in (0.5, 0.7, 0.8, 0.9, 0.95):
            sel = pr >= th; print(f'  P(frame)>={th}: {int(sel.sum())} ({sel.mean():.1%}) precision {y[sel].mean():.3f}')
        for th in (0.3, 0.1, 0.05):
            sel = pr <= th; print(f'  P(frame)<={th}: {int(sel.sum())} ({sel.mean():.1%}) precision(formula) {1 - y[sel].mean():.3f}')
    else:
        os.makedirs('models', exist_ok=True); pickle.dump(LogisticRegression(C=3, max_iter=400).fit(M, y), open('models/frame_model.pkl', 'wb')); print('saved models/frame_model.pkl')
else:
    m = pickle.load(open('models/frame_model.pkl', 'rb'))
    gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
    rows = c.execute("select id,text,matn_start,matn_end,flags from hadith where chain_tier in ('A','B','C') and matn_start>0").fetchall()
    cand = []; skip = collections.Counter()
    for h, text, ms, me, fl in rows:
        if h in gold: continue
        HID[0] = h; le = gap_of(text, ms)
        if le is None or le >= ms: continue
        gw = [w for w in plain(text[le:ms])[0].split() if w not in CONN and w.lstrip('و') not in CONN]
        if not gw: continue
        cand.append((h, text, ms, me, fl, le))
    print('gap hadith', len(cand))
    P = m.predict_proba(H.transform([feats(t, le, ms, ms) for h, t, ms, me, fl, le in cand]))[:, 1]
    V = {}
    for f in glob.glob('labels/gaps_out/chunk_*.jsonl'):
        for l in open(f, encoding='utf-8'):
            if l.strip():
                try: o = json.loads(l); V[o['id']] = o['label']
                except Exception: pass
    chg = []
    for (h, text, ms, me, fl, le), p in zip(cand, P):
        if V.get(h) in ('formula', 'chain', 'other'): continue          # Claude said: leave
        if V.get(h) != 'frame' and p < P_INC: continue
        ns = advance(text, le, ms)
        if ns >= ms - 3 or (me is not None and ns >= me): skip['no_move'] += 1; continue
        w12 = plain(text[ns:ms])[0].split()[:14]
        if any(w in ('ثنا', 'نا', 'حدثنا', 'اخبرنا', 'انا', 'حدثني', 'اخبرني', 'انبانا', 'انبا', 'ح') for w in w12) or (w12 and w12[0] in ('يا', 'ما', 'عن')): skip['chain_words_in_gap'] += 1; continue
        chg.append((h, text, ms, me, fl, ns, p))
    print('P>=', P_INC, ':', sum(1 for p in P if p >= P_INC), '| would move', len(chg), dict(skip))
    if MODE == 'pilot':
        random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 2)
        for h, text, ms, me, fl, ns, p in random.sample(chg, min(ARG or 30, len(chg))): print(h, round(float(p), 2), '|', text[max(0, ns - 30):ns].replace('\n', ' '), '[[', text[ns:ms][:130].replace('\n', ' '), ']]', text[ms:ms + 25].replace('\n', ' '))
    else:
        n = 0
        for h, text, ms, me, fl, ns, p in chg:
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_37','matn_start',?,?,?)", (h, ms, ns))
            c.execute('update hadith set matn_start=?, flags=? where id=?', (ns, ((fl or '') + ' frame_start').strip(), h)); n += 1
        c.commit(); print('applied', n)
