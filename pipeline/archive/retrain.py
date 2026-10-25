import sys, pickle, random, time, importlib.util
here = r'<WORKDIR>/'
spec = importlib.util.spec_from_file_location('ll', here + 'llm_labels.py'); ll = importlib.util.module_from_spec(spec); spec.loader.exec_module(ll)
sc = ll.sc
REP = int(sys.argv[1]); out = sys.argv[2]
Hs = sc.load_train(r'<ROOT>/Sanadset/sanadset.csv', 20000); random.shuffle(Hs)
X, Y = [], []
for H in Hs:
    u = random.random(); mode = 'matn_only' if u < 0.12 else 'no_prefix' if u < 0.27 else 'full'
    s = sc.make_seq(H, mode)
    if s: X.append(sc.tok_feats(s[0])); Y.append(s[1])
ids = [l.split('\t')[0] for l in open(here + 'train_labels.tsv', encoding='utf-8') if l.strip()]
rows = ll.load_rows(ids); gold = ll.read_labels(here + 'train_labels.tsv', rows)
n = 0
for i, g in gold.items():
    r = ll.tokens_labels(rows[i][3], g)
    if r is None: print('unlocatable', i); continue
    for _ in range(REP): X.append(sc.tok_feats(r[0])); Y.append(r[1])
    n += 1
print('base', len(Hs), 'llm rows', n, 'x', REP, flush=True)
crf = sc.sklearn_crfsuite.CRF(algorithm='lbfgs', c1=0.05, c2=0.05, max_iterations=70, all_possible_transitions=True)
t0 = time.time(); crf.fit(X, Y); print('fit s', int(time.time() - t0), flush=True)
pickle.dump(crf, open(here + out, 'wb'))
