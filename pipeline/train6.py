from paths import *
import sys, json, random, re, collections, time, importlib.util
HERE = PIPE
sys.path.insert(0, HERE)
import pycrfsuite
def load(name, fn):
    sp = importlib.util.spec_from_file_location(name, HERE + fn); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
sc = load('sc', 'sanad_crf.py'); ll = load('ll', 'llm_labels.py')
random.seed(21); t0 = time.time(); MAXTOK = 200
CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 600; OUT = sys.argv[2] if len(sys.argv) > 2 else 'parser_v6'
H = SRC + 'HadithKG/'
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
N = sc.norm
GLOSS = {'وهو', 'هو', 'يعني', 'يريد', 'وهي', 'اي'}
def seq_from(d):
    text = d['text']; sp = sorted(map(tuple, d['spans'])); ms = d['matn_start']; me = d.get('matn_end') or len(text)
    toks = sc.tokenize(text)[:MAXTOK]
    if not toks or sp[-1][1] > toks[-1][2]: return None
    T = []; L = []; k = 0; prev = -1; gloss = False
    for tok, a, b in toks:
        while k < len(sp) and sp[k][1] <= a: k += 1
        if k < len(sp) and sp[k][0] <= a < sp[k][1]:
            if k != prev: lab = 'B'; gloss = False; prev = k
            elif gloss: lab = 'G'
            elif N(tok) in GLOSS: lab = 'G'; gloss = True
            elif tok in sc.PUNCT: lab = 'T'; gloss = True       # punctuation inside a span ends the name; the rest is gloss
            else: lab = 'I'
        else:
            prev = -1; gloss = False; lab = 'M' if ms <= a < me else 'T'
        T.append(tok); L.append(lab)
    # trailing punctuation/gloss never belongs to the name; make sure each span still starts with B
    if 'M' not in L or 'B' not in L: return None
    return T, L
def augment(T, L):
    T = list(T); L = list(L); r = random.random(); fm = L.index('M') if 'M' in L else len(L)
    if r < 0.30:
        keep = [i for i in range(len(T)) if not (T[i] in ('،', ',') and L[i] == 'T')]; T = [T[i] for i in keep]; L = [L[i] for i in keep]
    elif r < 0.55:
        i = next((j for j, l in enumerate(L) if l == 'B'), None)
        if i is not None and i > 0: T.insert(i - 1, T[i - 1]); L.insert(i - 1, 'T')
    elif r < 0.80:
        pre = random.choice([['كَمَا'], ['قَالَ', ':'], ['وَقَالَ'], ['كَمَا', 'حَدَّثَنِي'], ['قَالَ', 'قَالَ', ':']]); T = pre + T; L = ['T'] * len(pre) + L
    else:
        T = [str(random.randint(1, 3000))] + T; L = ['T'] + L
    return T[:MAXTOK], L[:MAXTOK]
TRANSW = {'حدثنا', 'حدثني', 'اخبرنا', 'اخبرني', 'انبانا', 'ثنا', 'ثني', 'نا', 'انا', 'سمعت', 'عن', 'قال', 'قالا', 'قالوا', 'كما', 'وحدثنا', 'وحدثني', 'ح'}
WS = {}
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
# ---------------- sample training pool (cap per book)
by = collections.defaultdict(list)
with open(H + 'parser_corpus_all.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line); by[d['book']].append(d)
train = []
for b, L_ in by.items():
    random.shuffle(L_); train += L_[:CAP]
del by; random.shuffle(train); log('books capped at', CAP, '-> train hadith', len(train))
seqs = []
for d in train:
    s = seq_from(d)
    if s: seqs.append(s)
del train; log('usable sequences', len(seqs), '| M-before-chain texts:', sum(1 for T_, L_ in seqs if L_.index('M') < L_.index('B')))

# ---- Thaqalayn quality filter: drop hadith whose narrator tagging is unreliable (transmission word tagged as narrator, or name text left outside the tags)
_DI = re.compile('[ً-ْٰـ]'); _TRN = str.maketrans('أإآى', 'اااي')
def _n(x): return re.sub('[^ء-ي ]', ' ', _DI.sub('', x).translate(_TRN))
_FILL = set('عن قال قالا قالوا حدثنا حدثني اخبرنا اخبرني اخبرنى حدثنى ثنا انبانا سمعت وعن وقال و في ان انه رحمه الله رضي رضى عنه عنها عليه السلام صلى وسلم واله تعالى ايضا ثم عنهم عنهما قراءة عليه بن ابن'.split())
_TW = {'قال', 'عن', 'حدثنا', 'اخبرنا', 'حدثني', 'اخبرني', 'ثنا', 'سمعت', 'وعنه', 'عنه', 'وقال'}
def shia_ok(d):
    ct = d['chain_text']; sp = d['spans']; rest = []; pos = 0
    for a, b in sp: rest.append(ct[pos:a]); pos = b
    rest.append(ct[pos:])
    left = [w for w in _n(' '.join(rest)).split() if w not in _FILL and not w.isdigit()]
    if len(left) >= 3 or any(re.search(r'(?:^|\s)(?:بن|ابن)(?:\s)', _n(r)) for r in rest): return False
    return not any(_n(ct[a:b]).strip() in _TW for a, b in sp)
# ---- Shi'i hadith (Thaqalayn): training part + held-out exam
import zlib
TH = SRC + 'ThaqalaynData_clone/thaqalayn_hadith.jsonl'
shia = collections.defaultdict(list); nheld = 0
with open(TH, encoding='utf-8') as f, open(H + 'exam_shia.jsonl', 'w', encoding='utf-8') as ex:
    for line in f:
        d = json.loads(line)
        if not shia_ok(d): continue
        if zlib.crc32(d['kid'].encode()) % 20 == 0: ex.write(line); nheld += 1
        else: shia[d['book']].append(d)
nsh = 0
for b, L_ in shia.items():
    random.shuffle(L_)
    for d in L_[:1500]:
        s_ = seq_from(d)
        if s_: seqs.append(s_); nsh += 1
log('(only clean Shi i hadith kept)  Shi i training sequences added:', nsh, '| held-out Shi i hadith:', nheld); del shia
cnt = collections.defaultdict(lambda: [0, 0])
for T_, L_ in seqs:
    for t, l in zip(T_, L_):
        if l == 'M' or t in sc.PUNCT: continue
        cnt[N(t)][0 if l in 'BI' else 1] += 1
WS.update({w: c for w, c in cnt.items()}); del cnt
json.dump(WS, open(H + OUT + '_wordstats.json', 'w', encoding='utf-8'), ensure_ascii=False); log('word stats', len(WS))
# hand-labelled hard rows (the 40 eval rows stay held out): labels B/I/T, everything after the chain = T
hids = [l.split('	')[0] for l in open(HERE + 'train_labels.tsv', encoding='utf-8') if l.strip()]
hrows = ll.load_rows(hids); hgold = ll.read_labels(HERE + 'train_labels.tsv', hrows); hand = []
for i, g in hgold.items():
    r_ = ll.tokens_labels(hrows[i][3], g)
    if r_ and 'B' in r_[1]: hand.append((r_[0][:MAXTOK], ['T' if x == 'M' else x for x in r_[1]][:MAXTOK]))
log('hand-labelled hard rows used for training:', len(hand))
tr = pycrfsuite.Trainer(verbose=True); n = 0
for _ in range(15):
    for T_, L_ in hand: tr.append(feats(T_), L_); n += 1
for T_, L_ in seqs:
    tr.append(feats(T_), L_); n += 1
    if random.random() < 0.35: T2, L2 = augment(T_, L_); tr.append(feats(T2), L2); n += 1
    if n % 40000 == 0: log('featurised', n)
del seqs; log('training sequences', n)
tr.set_params({'c1': 0.05, 'c2': 0.05, 'max_iterations': 100, 'feature.possible_transitions': True, 'feature.minfreq': 3, 'max_linesearch': 20})
tr.train(H + OUT + '.crfsuite'); log('trained')
tg = pycrfsuite.Tagger(); tg.open(H + OUT + '.crfsuite')
def spans_of(L):
    res, st = set(), None
    for i, x in enumerate(list(L) + ['T']):
        if x == 'B' or (x not in ('I',) and st is not None):
            if st is not None: res.add((st, i))
            st = i if x == 'B' else None
    return res
def evaluate(path, label, limit=None):
    tp = fp = fn = ex = bex = k = 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            if limit and k >= limit: break
            s = seq_from(json.loads(line))
            if not s: continue
            p = tg.tag(feats(s[0])); k += 1; a, b = spans_of(p), spans_of(s[1]); tp += len(a & b); fp += len(a - b); fn += len(b - a); ex += (a == b)
            bex += (('M' in p and p.index('M')) == s[1].index('M'))
    P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1)
    log(f'{label} ({k} hadith): chain exact {ex/k:.3f} | matn-start exact {bex/k:.3f} | narrator P {P:.3f} R {R:.3f} F1 {2*P*R/(P+R):.3f}')
evaluate(H + 'exam_heldout.jsonl', 'HELD-OUT hadith-kg', 8000)
evaluate(H + 'exam_independent_muslim.jsonl', 'INDEPENDENT Muslim (confirmed by MIDS)')
evaluate(H + 'exam_shia.jsonl', 'HELD-OUT Shi i (Thaqalayn)', 5000)
# ---- my hand-labelled hard rows (never trained on)
ids = [l.split('\t')[0] for l in open(HERE + 'eval_labels.tsv', encoding='utf-8') if l.strip()]
rows = ll.load_rows(ids); gold = ll.read_labels(HERE + 'eval_labels.tsv', rows)
tp = fp = fn = ex = 0
for i, g in gold.items():
    text = rows[i][3]; toks = sc.tokenize(text)[:MAXTOK]; p = tg.tag(feats([t[0] for t in toks])); names = []
    for a, b in sorted(spans_of(p)):
        e = b
        while e > a and toks[e - 1][0] in sc.PUNCT: e -= 1
        if e > a: names.append(text[toks[a][1]:toks[e - 1][2]])
    gk = [ll.key(x) for x in g]; pk = [ll.key(x) for x in names]
    A, B = set(enumerate(gk)), set(enumerate(pk)); tp += len(A & B); fp += len(B - A); fn += len(A - B); ex += (gk == pk)
P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1)
log(f'HAND-LABELLED HARD ROWS ({len(gold)}): chain exact {ex/len(gold):.3f} | P {P:.3f} R {R:.3f} F1 {2*P*R/(P+R):.3f}   (previous best: exact 0.70, F1 0.805; v6: 0.625 / 0.732)')
