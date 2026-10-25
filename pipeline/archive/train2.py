import sys, json, random, re, collections, time, pickle
sys.path.insert(0, '<WORKDIR>')
import pycrfsuite
import importlib.util
spec = importlib.util.spec_from_file_location('sc', '<WORKDIR>/sanad_crf.py')
sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
random.seed(11); t0 = time.time(); MAXTOK = 160; CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 300
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
N = sc.norm
TRANSW = {'حدثنا', 'حدثني', 'اخبرنا', 'اخبرني', 'انبانا', 'ثنا', 'ثني', 'نا', 'انا', 'سمعت', 'عن', 'قال', 'قالا', 'قالوا', 'كما', 'وحدثنا', 'وحدثني'}
def feats(toks):
    n = len(toks); nt = [N(t) for t in toks]; out = []; q = c = False
    for i, t in enumerate(toks):
        w = nt[i]; f = ['b', 'w=' + w, 'q=%d' % q, 'c=%d' % c, 'p=%d' % (t in sc.PUNCT), 'pos=%d' % min(i, 30)]
        if t not in sc.PUNCT:
            ld = sc.DIAC.findall(t); f.append('ld=' + (ld[-1] if ld else '-')); f.append('s3=' + w[-3:])
        for o in (-2, -1, 1, 2):
            j = i + o; f.append('w%+d=%s' % (o, nt[j] if 0 <= j < n else ('<s>' if j < 0 else '</s>')))
        f.append('bg-=' + (nt[i - 1] if i else '<s>') + '|' + w); f.append('bg+=' + w + '|' + (nt[i + 1] if i + 1 < n else '</s>'))
        f.append('tw=%d' % (w in TRANSW)); f.append('ptw=%d' % (i > 0 and nt[i - 1] in TRANSW))
        out.append(f)
        if t in ('"', '“', '”', '«'): q = True
        if t == ':': c = True
    return out
def seq_from(d):
    t = d['text']; toks = sc.tokenize(t); sp = sorted(d['spans']); ms = d['matn_start']
    T = []; L = []; k = 0
    for tok, a, b in toks:
        while k < len(sp) and sp[k][1] <= a: k += 1
        if k < len(sp) and sp[k][0] <= a < sp[k][1]: lab = 'B' if a == sp[k][0] or (T and L[-1] in ('T', 'M') ) else 'I'
        elif a >= ms: lab = 'M'
        else: lab = 'T'
        T.append(tok); L.append(lab)
    # fix: first token of a span must be B
    prevspan = -1
    for i, (tok, a, b) in enumerate(toks):
        kk = next((j for j, s in enumerate(sp) if s[0] <= a < s[1]), -1)
        if kk >= 0: L[i] = 'B' if kk != prevspan else 'I'
        prevspan = kk if kk >= 0 else -1
    if 'M' not in L: return None
    firstM = L.index('M')
    if firstM > MAXTOK - 5: return None
    return T[:MAXTOK], L[:MAXTOK]
VERBS = ['حَدَّثَنَا', 'أَخْبَرَنَا', 'حَدَّثَنِي', 'ثنا']
def augment(T, L):
    T = list(T); L = list(L); r = random.random()
    if r < 0.30:      # drop the commas / colons between narrators (no punctuation)
        k = L.index('M') if 'M' in L else len(L)
        keep = [i for i in range(len(T)) if not (i < k and T[i] in ('،', ',') )]
        T = [T[i] for i in keep]; L = [L[i] for i in keep]
    elif r < 0.55:    # doubled opening verb
        i = next((j for j, l in enumerate(L) if l == 'B'), None)
        if i is not None and i > 0: T.insert(i - 1, T[i - 1]); L.insert(i - 1, 'T')
    elif r < 0.80:    # leading 'كما حدثني' / 'قال :' / 'وقال'
        pre = random.choice([['كَمَا'], ['قَالَ', ':'], ['وَقَالَ'], ['كَمَا', 'حَدَّثَنِي']]); T = pre + T; L = ['T'] * len(pre) + L
    else:             # leading integer id (e.g. '432 حدثنا')
        pre = [str(random.randint(1, 3000))]; T = pre + T; L = ['T'] + L
    return T[:MAXTOK], L[:MAXTOK]
# ---------------- load + sample
by = collections.defaultdict(list); test = []
with open('<ROOT>/HadithKG/parser_corpus_tierA.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        (test if d['kid'] % 20 == 0 else by[d['book']]).append(d)
train = []
for b, L_ in by.items():
    random.shuffle(L_); train += L_[:CAP]
random.shuffle(test); test = test[:5000]
log('books', len(by), 'train hadith', len(train), 'test', len(test))
tr = pycrfsuite.Trainer(verbose=False); nseq = 0
for d in train:
    s = seq_from(d)
    if not s: continue
    tr.append(feats(s[0]), s[1]); nseq += 1
    if random.random() < 0.40:
        T2, L2 = augment(*s); tr.append(feats(T2), L2); nseq += 1
log('sequences', nseq)
tr.set_params({'c1': 0.05, 'c2': 0.05, 'max_iterations': 80, 'feature.possible_transitions': True, 'feature.minfreq': 3})
tr.train('<ROOT>/HadithKG/parser_v5.crfsuite'); log('trained')
tg = pycrfsuite.Tagger(); tg.open('<ROOT>/HadithKG/parser_v5.crfsuite')
# ---------------- held-out Tier A
def spans_of(L):
    res, st = set(), None
    for i, x in enumerate(list(L) + ['T']):
        if x == 'B' or (x != 'I' and st is not None):
            if st is not None: res.add((st, i))
            st = i if x == 'B' else None
    return res
tp = fp = fn = ex = bex = n = 0
for d in test:
    s = seq_from(d)
    if not s: continue
    p = tg.tag(feats(s[0])); n += 1
    a, b = spans_of(p), spans_of(s[1]); tp += len(a & b); fp += len(a - b); fn += len(b - a)
    ex += (a == b); bex += (('M' in p and p.index('M')) == s[1].index('M'))
P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1)
log(f'HELD-OUT Tier A ({n} hadith): chain exact {ex/n:.3f} | matn-start exact {bex/n:.3f} | narrator P {P:.3f} R {R:.3f} F1 {2*P*R/(P+R):.3f}')
