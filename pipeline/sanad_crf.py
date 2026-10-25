from paths import *
"""CRF tagger for isnad/matn segmentation.
usage: python -I -X utf8 sanad_crf.py train <csv> <model_out> <n_train>
       python -I -X utf8 sanad_crf.py apply <csv> <model> <out_csv>
"""
import csv, sys, re, ast, random, pickle, time, collections
import sklearn_crfsuite
csv.field_size_limit(10**9)
MAXTOK = 160
TOK = re.compile(r'<[^>]+>|[^\s،,:"“”.؛;()\[\]«»]+|[،,:"“”.؛;()\[\]«»]')
TAG = re.compile(r'<(/?)(SANAD|MATN|NAR|IDF)>')
DIAC = re.compile('[ً-ْٰـ]')
PUNCT = set('،,:"“”.؛;()[]«»')
random.seed(7)

def norm(t):
    t = DIAC.sub('', t)
    return t.translate(str.maketrans('أإآى', 'اااي'))

def tokenize(text):
    return [(m.group(), m.start(), m.end()) for m in TOK.finditer(text)]

def labeled(H):
    """tagged Hadith -> (tokens, labels, offsets); None if unusable."""
    if '<IDF>' in H or H.count('<SANAD>') != 1 or H.count('<MATN>') != 1:
        return None
    if H.count('<NAR>') != H.count('</NAR>'):
        return None
    state_s = state_n = False; state_m = False
    toks, labs = [], []
    first = False
    for part in TAG.split(H):
        pass
    pos = 0; out = []
    for m in TAG.finditer(H):
        out.append(('t', H[pos:m.start()])); out.append(('g', m.group(1) + m.group(2))); pos = m.end()
    out.append(('t', H[pos:]))
    inN = inM = False; prevN = False
    for kind, v in out:
        if kind == 'g':
            if v == 'NAR': inN = True; first = True
            elif v == '/NAR': inN = False
            elif v == 'MATN': inM = True
            continue
        for tk, _, _ in tokenize(v):
            if inM: lab = 'M'
            elif inN:
                lab = 'B' if first else 'I'; first = False
                if tk in PUNCT: lab = 'T'
            else: lab = 'T'
            toks.append(tk); labs.append(lab)
    if 'M' not in labs or 'B' not in labs: return None
    return toks, labs

def tok_feats(toks):
    n = len(toks); nt = [norm(t) for t in toks]
    feats = []
    seen_q = seen_c = False
    for i, t in enumerate(toks):
        w = nt[i]
        d = {'b': 1.0, 'w': w, 'p2': w[:2], 's2': w[-2:], 's3': w[-3:], 'pos': min(i, 40),
             'punct': t in PUNCT, 'ld': (DIAC.findall(t) or ['-'])[-1] if t not in PUNCT else '-',
             'q': seen_q, 'c': seen_c, 'len': min(len(w), 8)}
        for o in (-2, -1, 1, 2, 3):
            j = i + o
            d['w%+d' % o] = nt[j] if 0 <= j < n else ('<s>' if j < 0 else '</s>')
        d['w-1|w'] = (nt[i-1] if i else '<s>') + '|' + w
        d['w|w+1'] = w + '|' + (nt[i+1] if i+1 < n else '</s>')
        feats.append(d)
        if t in ('"', '“', '”', '«'): seen_q = True
        if t == ':': seen_c = True
    return feats

def load_train(path, n_train):
    clean = []
    with open(path, encoding='utf-8', newline='') as f:
        r = csv.reader(f); next(r)
        for row in r:
            if row[4].strip() == 'No SANAD': continue
            try: sl = ast.literal_eval(row[4])
            except Exception: continue
            H = row[0]
            nars = re.findall(r'<NAR>(.*?)</NAR>', H, re.S)
            if [x.strip() for x in nars] != [x.strip() for x in sl] or len(sl) != int(row[5]): continue
            hm = re.search(r'<MATN>(.*?)</MATN>', H, re.S)
            if not hm or hm.group(1).strip() != row[3].strip(): continue
            if random.random() > n_train * 1.3 / 480000: continue
            clean.append(H)
    print('clean sampled', len(clean), flush=True)
    return clean

def make_seq(H, mode):
    r = labeled(H)
    if r is None: return None
    toks, labs = r
    if mode == 'matn_only':           # synthetic: chain removed
        k = labs.index('M'); toks, labs = toks[k:], labs[k:]
    elif mode == 'no_prefix':         # synthetic: opening verb(s) before first narrator removed
        k = labs.index('B'); toks, labs = toks[k:], labs[k:]
    toks, labs = toks[:MAXTOK], labs[:MAXTOK]
    return toks, labs

def train(path, out, n_train):
    Hs = load_train(path, n_train)
    random.shuffle(Hs)
    cut = int(len(Hs) * 0.92); tr, te = Hs[:cut], Hs[cut:]
    X, Y = [], []
    for H in tr:
        u = random.random()
        mode = 'matn_only' if u < 0.12 else 'no_prefix' if u < 0.27 else 'full'
        s = make_seq(H, mode)
        if s: X.append(tok_feats(s[0])); Y.append(s[1])
    print('train seqs', len(X), 'tokens', sum(map(len, Y)), flush=True)
    crf = sklearn_crfsuite.CRF(algorithm='lbfgs', c1=0.05, c2=0.05, max_iterations=70,
                               all_possible_transitions=True, verbose=False)
    t0 = time.time(); crf.fit(X, Y); print('fit s', int(time.time() - t0), flush=True)
    pickle.dump(crf, open(out, 'wb'))
    # held-out eval, per mode
    for mode in ('full', 'no_prefix', 'matn_only'):
        Xt, Yt = [], []
        for H in te:
            s = make_seq(H, mode)
            if s: Xt.append(tok_feats(s[0])); Yt.append(s[1])
        P = crf.predict(Xt)
        tokacc = sum(a == b for p, y in zip(P, Yt) for a, b in zip(p, y)) / sum(map(len, Yt))
        def bnd(l): return l.index('M') if 'M' in l else len(l)
        exact = sum(bnd(p) == bnd(y) for p, y in zip(P, Yt)) / len(Yt)
        def spans(l):
            s, cur = set(), None
            for i, x in enumerate(l):
                if x == 'B': cur = i; s.add([i, i])  if False else None
            return None
        def nspans(l):
            res, st = set(), None
            for i, x in enumerate(l + ['T']):
                if x == 'B' or (x != 'I' and st is not None):
                    if st is not None: res.add((st, i))
                    st = i if x == 'B' else None
            return res
        tp = fp = fn = 0
        for p, y in zip(P, Yt):
            a, b = nspans(p), nspans(y); tp += len(a & b); fp += len(a - b); fn += len(b - a)
        pr = tp / max(tp + fp, 1); rc = tp / max(tp + fn, 1)
        print(f'[{mode}] n={len(Yt)} token_acc={tokacc:.4f} boundary_exact={exact:.4f} narrator P={pr:.4f} R={rc:.4f} F1={2*pr*rc/max(pr+rc,1e-9):.4f}', flush=True)

def decode(text, crf_out):
    """crf_out: (labels, marginals) -> structured result."""

def apply(path, model, out):
    crf = pickle.load(open(model, 'rb'))
    rows = []
    with open(path, encoding='utf-8', newline='') as f:
        r = csv.reader(f); hdr = next(r)
        for i, row in enumerate(r, 2):
            if row[4].strip() == 'No SANAD': rows.append((i, row))
    print('no-sanad rows', len(rows), flush=True)
    w = csv.writer(open(out, 'w', encoding='utf-8-sig', newline=''))
    w.writerow(hdr + ['src_row', 'confidence', 'status'])
    B = 2000; stats = collections.Counter()
    for s in range(0, len(rows), B):
        chunk = rows[s:s + B]; seqs = []; metas = []
        for i, row in chunk:
            text = re.sub(r'</?(?:MATN|SANAD|NAR|IDF)>', ' ', row[0])
            toks = tokenize(text)
            seqs.append(tok_feats([t[0] for t in toks[:MAXTOK]])); metas.append((text, toks))
        labs = [list(l) for l in crf.predict(seqs)]; marg = crf.predict_marginals(seqs)
        for (i, row), (text, toks), lab, mg in zip(chunk, metas, labs, marg):
            if 'B' not in lab:
                w.writerow(row + [i, 1.0 if lab and all(m['M'] > .9 for m in mg) else 0.5, 'no_chain']); stats['no_chain'] += 1; continue
            k = lab.index('M') if 'M' in lab else None
            if k is None:                       # chain fills the whole window: can't place boundary
                w.writerow(row + [i, 0.0, 'boundary_not_found']); stats['boundary_not_found'] += 1; continue
            # narrators strictly before boundary
            spans, st = [], None
            for j in range(k + 1):
                x = lab[j] if j < k else 'T'
                if x == 'B' or (x != 'I' and st is not None):
                    if st is not None:
                        e = j
                        while e > st and toks[e-1][0] in PUNCT: e -= 1
                        spans.append((st, e))
                    st = j if x == 'B' else None
            if not spans:
                w.writerow(row + [i, 0.5, 'no_chain']); stats['no_chain'] += 1; continue
            names = [text[toks[a][1]:toks[b-1][2]].strip() for a, b in spans]
            s_start = toks[spans[0][0]][1]; s_end = toks[spans[-1][1]-1][2]
            m_start = toks[k][1]
            tagged = text[:s_start].strip() + ' <SANAD> ' + ' '.join(
                ('<NAR> %s </NAR>' % text[toks[a][1]:toks[b-1][2]]) if True else '' for a, b in spans) + ' </SANAD> <MATN> ' + text[m_start:].strip() + ' </MATN>'
            # keep original separators between narrators
            parts, prev = [], s_start
            for (a, b), nm in zip(spans, names):
                parts.append(text[prev:toks[a][1]]); parts.append('<NAR> ' + nm + ' </NAR>'); prev = toks[b-1][2]
            parts.append(text[prev:s_end])
            tagged = text[:s_start].strip() + ' <SANAD> ' + ''.join(parts).strip() + ' </SANAD> <MATN> ' + text[m_start:].strip() + ' </MATN>'
            conf = min(min(mg[j].values() and max(mg[j].values()) for j in range(min(k + 2, len(mg)))), 1.0)
            matn = text[m_start:].strip()
            status = 'fixed' if conf >= 0.9 else 'low_confidence'
            stats[status] += 1
            w.writerow([tagged, row[1], row[2], matn, repr(names), len(names), i, round(conf, 4), status])
        print(s + len(chunk), dict(stats), flush=True)
    print('done', dict(stats))

if __name__ == '__main__':
    if sys.argv[1] == 'train': train(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else: apply(sys.argv[2], sys.argv[3], sys.argv[4])
