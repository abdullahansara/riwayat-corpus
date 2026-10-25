import sys, json, importlib.util, collections
HERE = '<WORKDIR>/'
sys.path.insert(0, HERE)
import pycrfsuite
def load(name, fn):
    sp = importlib.util.spec_from_file_location(name, HERE + fn); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
er = load('er', 'extend_rule.py'); ll = er.ll; sc = er.sc; N = sc.norm
H = '<ROOT>/HadithKG/'
WS = json.load(open(H + 'parser_v6_wordstats.json', encoding='utf-8'))
TRANSW = {'حدثنا', 'حدثني', 'اخبرنا', 'اخبرني', 'انبانا', 'ثنا', 'ثني', 'نا', 'انا', 'سمعت', 'عن', 'قال', 'قالا', 'قالوا', 'كما', 'وحدثنا', 'وحدثني', 'ح'}
def nb(w):
    c = WS.get(w)
    if not c: return 'U'
    n = c[0] + c[1]; return '%d%s' % (int(8 * c[0] / n), 'h' if n >= 50 else 'l')
def feats(toks):
    n = len(toks); nt = [N(t) for t in toks]; nbs = [nb(w) for w in nt]; out = []; q = c = False
    for i, t in enumerate(toks):
        w = nt[i]; f = ['b', 'w=' + w, 'nb=' + nbs[i], 'q=%d' % q, 'c=%d' % c, 'p=%d' % (t in sc.PUNCT), 'tw=%d' % (w in TRANSW)]
        if t not in sc.PUNCT:
            ld = sc.DIAC.findall(t); f.append('ld=' + (ld[-1] if ld else '-'))
        for o in (-2, -1, 1, 2):
            j = i + o; f.append('w%+d=%s' % (o, nt[j] if 0 <= j < n else '#')); f.append('nb%+d=%s' % (o, nbs[j] if 0 <= j < n else '#'))
        f.append('bg-=' + (nt[i - 1] if i else '<s>') + '|' + w); f.append('bg+=' + w + '|' + (nt[i + 1] if i + 1 < n else '</s>'))
        f.append('ptw=%d' % (i > 0 and nt[i - 1] in TRANSW)); f.append('pos=%d' % min(i, 12))
        out.append(f)
        if t in ('"', '“', '”', '«'): q = True
        if t == ':': c = True
    return out
tg = pycrfsuite.Tagger(); tg.open(H + 'parser_v6.crfsuite')
def predict(text, rule):
    toks = sc.tokenize(text)[:200]; lab = list(tg.tag(feats([t[0] for t in toks])))
    if rule:
        last = max((j for j, x in enumerate(lab) if x in ('B', 'I')), default=-1)
        lab = [x if (j <= last) else 'M' for j, x in enumerate(lab)]          # rules expect everything after the chain to be 'M'
        lab = er.drop_prophet(toks, er.extend_labels(toks, list(lab)))
        if not er.names_from(text, toks, lab):
            l2 = er.late_start_labels(toks)
            if l2 is not None: lab = er.drop_prophet(toks, l2)
    names = []; st = None
    for j in range(len(lab) + 1):
        x = lab[j] if j < len(lab) else 'T'
        if x == 'B' or (x != 'I' and st is not None):
            if st is not None:
                e = j
                while e > st and toks[e - 1][0] in sc.PUNCT: e -= 1
                if e > st: names.append(text[toks[st][1]:toks[e - 1][2]])
            st = j if x == 'B' else None
    return names
ids = [l.split('\t')[0] for l in open(HERE + 'eval_labels.tsv', encoding='utf-8') if l.strip()]
rows = ll.load_rows(ids); gold = ll.read_labels(HERE + 'eval_labels.tsv', rows)
for rule in (False, True):
    tp = fp = fn = ex = 0; wrong = []
    for i, g in gold.items():
        p = predict(rows[i][3], rule); gk = [ll.key(x) for x in g]; pk = [ll.key(x) for x in p]
        A, B = set(enumerate(gk)), set(enumerate(pk)); tp += len(A & B); fp += len(B - A); fn += len(A - B)
        if gk == pk: ex += 1
        else: wrong.append((i, g, p))
    P = tp / (tp + fp); R = tp / (tp + fn)
    print(f"v6 {'+ extension rules' if rule else 'plain'}: chain exact {ex/len(gold):.3f} | P {P:.3f} R {R:.3f} F1 {2*P*R/(P+R):.3f}")
    if rule:
        kinds = collections.Counter()
        for i, g, p in wrong:
            gk = [ll.key(x) for x in g]; pk = [ll.key(x) for x in p]
            miss = [x for x in gk if x not in pk]; extra = [x for x in pk if x not in gk]
            kinds['missed narrators only' if miss and not extra else 'extra narrators only' if extra and not miss else 'both']+=1
        print('error kinds:', dict(kinds))
        for i, g, p in wrong[:10]:
            gk = [ll.key(x) for x in g]; pk = [ll.key(x) for x in p]
            print(f'  #{i}  MISSED: {[x[:16] for x in gk if x not in pk][:3]}   EXTRA: {[x[:16] for x in pk if x not in gk][:3]}')

bad = 0; tot = 0; ex = []
for i in list(gold)[:40]:
    text = rows[i][3]; toks = sc.tokenize(text)[:200]; lab = list(tg.tag(feats([t[0] for t in toks])))
    st = None
    for j in range(len(lab) + 1):
        x = lab[j] if j < len(lab) else 'T'
        if x == 'B' or (x != 'I' and st is not None):
            if st is not None:
                tot += 1; seg = [t[0] for t in toks[st:j]]
                if seg[-1] in sc.PUNCT or any(w in sc.PUNCT for w in seg[:-1]): bad += 1; ex.append(' '.join(seg)[:60])
            st = j if x == 'B' else None
print(f'predicted narrator spans containing/ending with punctuation: {bad} of {tot}'); print(ex[:6])
