from paths import *
"""Helpers: map hand-labelled narrator lists onto tokens; score a model against them."""
import csv, re, ast, importlib.util, pickle, sys
csv.field_size_limit(10**9)
here = rPIPE
spec = importlib.util.spec_from_file_location('sc', here + 'sanad_crf.py'); sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
PARSED = rSRC + 'Sanadset/nosanad_parsed.csv'

def load_rows(ids):
    ids = set(map(str, ids)); out = {}
    with open(PARSED, encoding='utf-8-sig', newline='') as f:
        r = csv.reader(f); next(r)
        for row in r:
            if row[0] in ids: out[row[0]] = row
    return out

def read_labels(path, rows):
    lab = {}
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line.strip(): continue
        i, v = line.split('\t', 1)
        lab[i] = ast.literal_eval(rows[i][4]) if v.strip() == '=' else ([] if v.strip() == '-' else [x.strip() for x in v.split(';') if x.strip()])
    return lab

def key(s):
    s = re.sub(r'[0-9\u0660-\u0669]', '', sc.norm(s)); s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'^[وفل]', '', s)

def tokens_labels(text, narrators):
    """-> (tokens, labels) or None if a narrator can't be located."""
    toks = [t[0] for t in sc.tokenize(text)][:sc.MAXTOK]; nt = [sc.norm(t) for t in toks]
    labs = ['T'] * len(toks); cur = 0; last = 0
    for n in narrators:
        nn = [sc.norm(t) for t in sc.TOK.findall(n)]
        if not nn: continue
        found = None
        for i in range(cur, len(toks) - len(nn) + 1):
            if (nt[i] == nn[0] or nt[i].endswith(nn[0])) and nt[i+1:i+len(nn)] == nn[1:]:
                found = i; break
        if found is None: return None
        labs[found] = 'B'
        for j in range(found + 1, found + len(nn)): labs[j] = 'I'
        cur = found + len(nn); last = cur
    for j in range(last, len(toks)): labs[j] = 'M'
    return toks, labs

def clean_text(h): return re.sub(r'</?(?:MATN|SANAD|NAR|IDF)>', ' ', h)

def predict_chain(crf, text):
    toks = sc.tokenize(text)[:sc.MAXTOK]
    lab = list(crf.predict([sc.tok_feats([t[0] for t in toks])])[0])
    k = lab.index('M') if 'M' in lab else len(lab)
    names, st = [], None
    for j in range(k + 1):
        x = lab[j] if j < k else 'T'
        if x == 'B' or (x != 'I' and st is not None):
            if st is not None:
                e = j
                while e > st and toks[e-1][0] in sc.PUNCT: e -= 1
                names.append(text[toks[st][1]:toks[e-1][2]])
            st = j if x == 'B' else None
    return names

def score(crf, rows, gold):
    tp = fp = fn = exact = n = 0; bad = []
    for i, g in gold.items():
        p = predict_chain(crf, rows[i][3])
        gk = [key(x) for x in g]; pk = [key(x) for x in p]
        m = sum(a == b for a, b in zip(gk, pk)) if True else 0
        a, b = set(enumerate(gk)), set(enumerate(pk))   # position-aware
        tp += len(a & b); fp += len(b - a); fn += len(a - b); n += 1
        if gk == pk: exact += 1
        else: bad.append(i)
    P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1)
    return dict(rows=n, exact_chain=round(exact / n, 3), P=round(P, 3), R=round(R, 3), F1=round(2*P*R/max(P+R, 1e-9), 3)), bad

if __name__ == '__main__':
    crf = pickle.load(open(here + sys.argv[1], 'rb'))
    ids = [l.split('\t')[0] for l in open(here + 'eval_labels.tsv', encoding='utf-8') if l.strip()]
    rows = load_rows(ids); gold = read_labels(here + 'eval_labels.tsv', rows)
    unmatched = [i for i, g in gold.items() if tokens_labels(rows[i][3], g) is None]
    print('labels not locatable in text:', unmatched)
    s, bad = score(crf, rows, gold); print(s); print('wrong rows', bad)
