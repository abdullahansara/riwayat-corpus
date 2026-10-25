"""Phase 2 - missed-narrator model.  Token tagger (B / I / O) over the chain region, trained on Claude labels:
positives = parsed mentions the labeller accepted (kind narrator/relative/anonymous) + names the labeller listed as 'missed'.
Inference only proposes spans inside gaps, i.e. in tokens not covered by an existing mention.
  python pipeline/fix_23_gap_model.py cv  LABEL_OUT_DIR ...     # grouped 5-fold CV: precision / recall of newly proposed spans vs the 'missed' lists
  python pipeline/fix_23_gap_model.py fit LABEL_OUT_DIR ...     # save models/gap_model.pkl"""
from paths import *
from labels_lib import load_labels, find, plain
import sqlite3, sys, re, random, pickle, collections, os, glob, json, bisect
import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
CONN = set('حدثنا حدثني اخبرنا اخبرني ثنا نا انا عن قال وقال قالت يقول سمعت ان انه ثم ف و ح انبانا انبا اخبرناه حدثناه ثني قالا قالوا'.split())
def toks(text, end):
    return [(m.start(), m.end(), plain(m.group())[0], m.group()) for m in re.finditer(r'\S+', text[:end])]
def tfeats(T, i, covered):
    f = {}
    w = lambda j: T[j][2] if 0 <= j < len(T) else ('<s>' if j < 0 else '</s>')
    raw = lambda j: T[j][3] if 0 <= j < len(T) else ''
    f['w=' + w(i)] = 1
    for d in (1, 2, 3): f[f'p{d}={w(i - d)}'] = 1; f[f'n{d}={w(i + d)}'] = 1
    f[f'p2p1={w(i - 2)}_{w(i - 1)}'] = 1; f[f'p1w={w(i - 1)}_{w(i)}'] = 1; f[f'wn1={w(i)}_{w(i + 1)}'] = 1
    f['conn'] = int(w(i) in CONN); f['p1conn'] = int(w(i - 1) in CONN); f['n1conn'] = int(w(i + 1) in CONN)
    f['p1comma'] = int(raw(i - 1).endswith(('،', ','))); f['comma'] = int(raw(i).endswith(('،', ',')))
    f['al'] = int(w(i).startswith('ال')); f['bn'] = int(w(i) in ('بن', 'ابن')); f['abu'] = int(w(i) in ('ابو', 'ابي', 'ابا'))
    f['p1bn'] = int(w(i - 1) in ('بن', 'ابن')); f['p1abu'] = int(w(i - 1) in ('ابو', 'ابي', 'ابا'))
    f['covered'] = int(covered[i]); f['p1cov'] = int(i > 0 and covered[i - 1]); f['n1cov'] = int(i + 1 < len(T) and covered[i + 1])
    f['pos=' + str(min(i, 40) // 5)] = 1
    return f
def prepare(h, text, label, c):
    end = label['matn_start'] if label['matn_start'] else len(text)
    T = toks(text, end)
    if not T: return None
    starts = [t[0] for t in T]
    ments = c.execute('select start,end,rowid from chain_mention where hadith_id=? and start is not null order by start', (h,)).fetchall()
    kinds = {m['i']: m['kind'] for m in label['mentions']}
    # mentions of this hadith as the sampler listed them: ordered by start, same order as 'i'
    ordered = c.execute('select start,end from chain_mention where hadith_id=? and start is not null order by start limit 30', (h,)).fetchall()
    covered = [False] * len(T); tag = ['O'] * len(T)
    for (s, e, _r) in ments:
        a = bisect.bisect_left(starts, s); b = bisect.bisect_left(starts, e)
        for j in range(a, min(b, len(T))): covered[j] = True
    spans = []
    for k, (s, e) in enumerate(ordered):
        if kinds.get(k) in ('narrator', 'relative', 'anonymous'): spans.append((s, e, 'cur'))
    for name in label.get('missed', []):
        r = find(text, name)
        if r and r[0] < end: spans.append((r[0], r[1], 'missed'))
    for s, e, src in spans:
        a = bisect.bisect_left(starts, s); b = bisect.bisect_left(starts, e)
        for j in range(a, min(max(b, a + 1), len(T))): tag[j] = 'B' if j == a else 'I'
    return T, covered, tag, spans
def decode(T, covered, P):
    """spans (start,end) built from tokens in gaps: B (or I after O) starts, I continues; mean prob must exceed 0.5"""
    out = []; cur = None
    for i in range(len(T)):
        lab = int(np.argmax(P[i])); pr = P[i][lab]
        if covered[i] or lab == 0:
            if cur: out.append(cur); cur = None
            continue
        if lab == 1 or cur is None:
            if cur: out.append(cur)
            cur = [i, i, pr]
        else: cur[1] = i; cur[2] = min(cur[2], pr)
    if cur: out.append(cur)
    return [(T[a][0], T[b][1], p) for a, b, p in out]
CL = {'O': 0, 'B': 1, 'I': 2}
if __name__ == '__main__':
    MODE = sys.argv[1]; DIRS = sys.argv[2:]
    c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
    ids = set()
    for d in DIRS:
        for fn in glob.glob(os.path.join(d, 'chunk_*.jsonl')):
            for l in open(fn, encoding='utf-8'):
                if l.strip(): ids.add(json.loads(l)['id'])
    texts = {h: c.execute('select text from hadith where id=?', (h,)).fetchone()[0] for h in ids}
    labels = load_labels(DIRS, texts)
    data = []
    for h, o in labels.items():
        if o.get('chain_status') != 'has_chain' or o['matn_start'] is None: continue
        r = prepare(h, texts[h], o, c)
        if r: data.append((h, r))
    print('hadith', len(data), 'tokens', sum(len(r[1][0]) for r in data), 'missed spans', sum(1 for h, r in data for s in r[3] if s[2] == 'missed'))
    hasher = FeatureHasher(n_features=2 ** 19, input_type='dict')
    def XY(sub):
        X = hasher.transform([tfeats(T, i, cov) for h, (T, cov, tag, sp) in sub for i in range(len(T))])
        y = np.array([CL[t] for h, (T, cov, tag, sp) in sub for t in tag]); return X, y
    def fit(sub):
        X, y = XY(sub); return LogisticRegression(C=1.0, max_iter=300).fit(X, y)
    if MODE == 'cv':
        random.seed(0); order = list(range(len(data))); random.shuffle(order); K = 5
        res = collections.defaultdict(lambda: [0, 0, 0])      # threshold -> [proposed, correct, total_missed]
        total_missed = sum(1 for h, r in data for s in r[3] if s[2] == 'missed')
        for f in range(K):
            te_idx = set(order[f::K]); te = [data[i] for i in order[f::K]]; tr = [data[i] for i in order if i not in te_idx]
            m = fit(tr)
            for h, (T, cov, tag, sp) in te:
                P = m.predict_proba(hasher.transform([tfeats(T, i, cov) for i in range(len(T))]))
                missed = {(s, e) for s, e, src in sp if src == 'missed'}
                for th in (0.5, 0.7, 0.8, 0.9):
                    for s, e, p in decode(T, cov, P):
                        if p < th: continue
                        res[th][0] += 1
                        # correct when it overlaps a missed span by >=60% of the shorter one
                        res[th][1] += any(min(e, e2) - max(s, s2) >= 0.6 * min(e - s, e2 - s2) for s2, e2 in missed)
        print('total labelled missed', total_missed)
        for th in sorted(res): print(f'  p>={th}: proposed {res[th][0]}, correct {res[th][1]} -> precision {res[th][1] / max(1, res[th][0]):.3f}, recall {res[th][1] / total_missed:.3f}')
    else:
        m = fit(data); os.makedirs('models', exist_ok=True); pickle.dump((m, hasher), open('models/gap_model.pkl', 'wb')); print('saved models/gap_model.pkl')
