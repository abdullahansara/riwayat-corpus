import csv, re, pickle, collections, importlib.util
csv.field_size_limit(10**9)
here = r'<WORKDIR>/'
spec = importlib.util.spec_from_file_location('er', here + 'extend_rule.py'); er = importlib.util.module_from_spec(spec); spec.loader.exec_module(er)
ll = er.ll; sc = er.sc
S = r'<ROOT>/Sanadset/'
nrm = lambda n: re.sub(r'^ل[\u064B-\u0652]*ل', 'ال', n)
rows = []
with open(S + 'nosanad_parsed.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r); rows = list(r)
# hand labels (gold) override the model
gold = {}
for fn in ('eval_labels.tsv', 'train_labels.tsv'):
    ids = [l.split('\t')[0] for l in open(here + fn, encoding='utf-8') if l.strip()]
    rr = ll.load_rows(ids); gold.update(ll.read_labels(here + fn, rr))
crf = pickle.load(open(here + 'v4.pkl', 'rb'))
w = csv.writer(open(S + 'nosanad_parsed_v2.csv', 'w', encoding='utf-8-sig', newline=''))
w.writerow(['src_row', 'Book', 'Num_hadith', 'Original_text', 'Sanad_parsed', 'Sanad_normalized', 'Matn', 'Sanad_Length', 'status', 'label_source'])
stats = collections.Counter(); B = 2000
for s in range(0, len(rows), B):
    chunk = rows[s:s + B]
    toks_l = [sc.tokenize(x[3])[:sc.MAXTOK] for x in chunk]
    labs = crf.predict([sc.tok_feats([t[0] for t in tk]) for tk in toks_l])
    for x, toks, lab in zip(chunk, toks_l, labs):
        text = x[3]; src = 'model'
        if x[0] in gold:
            names = gold[x[0]]; src = 'llm_gold'
            lab = None
        else:
            lab = er.extend_labels(toks, list(lab)); names = er.names_from(text, toks, lab)
        if not names:
            w.writerow([x[0], x[1], x[2], text, 'No SANAD', 'No SANAD', text, 0, 'no_chain', src]); stats['no_chain'] += 1; continue
        if lab is None:                                       # locate matn start for gold rows
            r = ll.tokens_labels(text, names)
            lab = r[1] if r else None
        k = lab.index('M') if lab and 'M' in lab else None
        matn = text[toks[k][1]:].strip() if k is not None and k < len(toks) else ''
        if k is None: stats['no_boundary'] += 1
        w.writerow([x[0], x[1], x[2], text, repr(names), repr([nrm(n) for n in names]), matn, len(names), 'parsed', src]); stats['parsed_' + src] += 1
    if (s // B) % 10 == 0: print(s + len(chunk), dict(stats), flush=True)
print('done', dict(stats))
