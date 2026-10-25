import csv, re, pickle, collections, json, importlib.util
csv.field_size_limit(10**9)
here = r'<WORKDIR>/'
spec = importlib.util.spec_from_file_location('er', here + 'extend_rule.py'); er = importlib.util.module_from_spec(spec); spec.loader.exec_module(er)
ll = er.ll; sc = er.sc; N = er.N
S = r'<ROOT>/Sanadset/'
nrm = lambda n: re.sub(r'^ل[\u064B-\u0652]*ل', 'ال', n)
# --- original file: order, book, num, has chain
orig = []
with open(S + 'sanadset.csv', encoding='utf-8', newline='') as f:
    r = csv.reader(f); next(r)
    for row in r: orig.append([row[1], int(row[2]) if row[2].isdigit() else -1, row[4].strip() != 'No SANAD'])
book_n = collections.Counter(x[0] for x in orig); book_c = collections.Counter(x[0] for x in orig if x[2])
# --- no-SANAD rows
with open(S + 'nosanad_parsed.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r); rows = list(r)
gold = {}
for fn in ('eval_labels.tsv', 'train_labels.tsv'):
    ids = [l.split('\t')[0] for l in open(here + fn, encoding='utf-8') if l.strip()]
    gold.update(ll.read_labels(here + fn, ll.load_rows(ids)))
crf = pickle.load(open(here + 'v4.pkl', 'rb'))
res = {}; B = 2000; how = collections.Counter()
for s in range(0, len(rows), B):
    chunk = rows[s:s + B]; toks_l = [sc.tokenize(x[3])[:sc.MAXTOK] for x in chunk]
    labs = crf.predict([sc.tok_feats([t[0] for t in tk]) for tk in toks_l])
    for x, toks, lab in zip(chunk, toks_l, labs):
        text = x[3]
        if x[0] in gold and gold[x[0]]:
            names = gold[x[0]]; r_ = ll.tokens_labels(text, names); lab = r_[1] if r_ else None; src = 'llm_gold'
        else:
            src = 'model'
            lab = er.drop_prophet(toks, er.extend_labels(toks, list(lab))); names = er.names_from(text, toks, lab)
            if not names:
                l2 = er.late_start_labels(toks)
                if l2 is not None:
                    lab = er.drop_prophet(toks, l2); names = er.names_from(text, toks, lab); src = 'model_late_start'
        if names and lab is not None and 'M' in lab:
            k = lab.index('M'); matn = text[toks[k][1]:].strip() if k < len(toks) else ''
            res[x[0]] = (names, matn, src)
        elif names: res[x[0]] = (names, '', src)
        how[src if names else 'none'] += 1
print('parsed:', dict(how), flush=True)
# --- reason + donor, scanning the original order
REF = re.compile(r'^(?:و|ف)?(?:باسناده|باسنادهم|بهذا الاسناد|بهذا السند|بالاسناد|بالسند|بسنده|به|بمثله|بنحوه|عنه|عنها|عنهم|بهذا)\b')
SAYS = re.compile(r'^(?:ثم |و|ف)?(?:قال|قالا|قالوا|قلت|قالت|وقال|يقول|وسمعت|وسالت|وان|ان|وكان)\b')
STR = re.compile(r'\b(حدثنا|حدثني|اخبرنا|اخبرني|انبانا|ثنا|ثني)\b')
last = {}                      # book -> (src_row, num) of last row that has a chain
byrow = {x[0]: x for x in rows}
out = []; reasons = collections.Counter(); donors = collections.Counter()
for i, (b, num, has) in enumerate(orig, 2):
    k = str(i)
    if k not in byrow:
        if has: last[b] = (i, num)
        continue
    x = byrow[k]; text = x[3]
    if k in res:
        names, matn, src = res[k]
        out.append([k, b, x[2], text, repr(names), repr([nrm(n) for n in names]), matn, len(names), 'parsed', src, '', ''])
        last[b] = (i, num); continue
    t = N(text); w = t.split() or ['']
    d = last.get(b); donor = d[0] if d and 0 <= num - d[1] <= 40 and d[1] >= 0 else ''
    if book_n[b] >= 50 and book_c[b] / book_n[b] <= 0.05 and not donor: reason = 'book_has_no_chains'
    elif REF.match(w[0]) or (w[0].startswith('حديث') and len(w[0]) <= 6): reason = 'referential_opening'
    elif STR.search(' '.join(w[8:])): reason = 'chain_after_or_inside_text'
    elif SAYS.match(t) or t.startswith('"'): reason = 'continuation_fragment'
    else: reason = 'matn_only_or_other'
    reasons[reason] += 1; donors['has_donor' if donor else 'no_donor'] += 1
    out.append([k, b, x[2], text, 'No SANAD', 'No SANAD', text, 0, 'no_chain', reason, donor, ''])
print('remaining no-chain:', dict(reasons), dict(donors))
w = csv.writer(open(S + 'nosanad_parsed_v3.csv', 'w', encoding='utf-8-sig', newline=''))
w.writerow(['src_row', 'Book', 'Num_hadith', 'Original_text', 'Sanad_parsed', 'Sanad_normalized', 'Matn', 'Sanad_Length', 'status', 'label_source_or_reason', 'inherits_chain_from_row', 'reserved'])
w.writerows(out); print('rows written', len(out))
