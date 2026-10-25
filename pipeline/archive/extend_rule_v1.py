import re, importlib.util
here = r'<WORKDIR>/'
spec = importlib.util.spec_from_file_location('ll', here + 'llm_labels.py'); ll = importlib.util.module_from_spec(spec); spec.loader.exec_module(ll)
sc = ll.sc
N = lambda t: sc.norm(t)
TRANS = {'حدثنا','حدثني','اخبرنا','اخبرني','انبانا','انبا','اخبرنيه','ثنا','ثني','نا','انا','سمعت','سمعنا','قرات','حدثناه','ثناه'}
SAY = {'قال','قالا','قالوا','فقال','وقال','وقالا','يقول','فقالا'}
SEP = set('،,:.؛;"“”«»')
def pred_labels(crf, toks):
    return list(crf.predict([sc.tok_feats([t[0] for t in toks])])[0])
def extend_labels(toks, lab, max_name=10):
    """If the model ends the chain but a [say-word] + transmission verb + name follows, extend."""
    lab = list(lab); n = len(toks)
    k = lab.index('M') if 'M' in lab else n
    changed = True
    while changed and k < n:
        changed = False
        j = k
        while j < n and (toks[j][0] in SEP or N(toks[j][0]) in SAY): j += 1
        if j < n and N(toks[j][0]) in TRANS and j > k - 0:
            m = j + 1
            while m < n and N(toks[m][0]) in TRANS: m += 1      # حدثنا حدثنا
            s = m
            while m < n and m - s < max_name and toks[m][0] not in SEP and N(toks[m][0]) not in SAY and N(toks[m][0]) not in TRANS and not re.search(r'\d', toks[m][0]): m += 1
            if m > s:
                for x in range(k, s): lab[x] = 'T'
                lab[s] = 'B'
                for x in range(s + 1, m): lab[x] = 'I'
                # follow ", عن <name>" links that continue the chain
                while True:
                    j2 = m
                    while j2 < n and toks[j2][0] in SEP: j2 += 1
                    if j2 < n and j2 > m - 0 and N(toks[j2][0]) in ('عن', 'عنه') and j2 + 1 < n:
                        s2 = j2 + 1; m2 = s2
                        while m2 < n and m2 - s2 < max_name and toks[m2][0] not in SEP and N(toks[m2][0]) not in SAY and N(toks[m2][0]) not in TRANS and N(toks[m2][0]) != 'عن' and not re.search(r'\d', toks[m2][0]): m2 += 1
                        if m2 == s2: break
                        for x in range(m, s2): lab[x] = 'T'
                        lab[s2] = 'B'
                        for x in range(s2 + 1, m2): lab[x] = 'I'
                        m = m2
                    else: break
                for x in range(m, n): lab[x] = 'M'
                k = m; changed = True
    return lab
def names_from(text, toks, lab):
    k = lab.index('M') if 'M' in lab else len(lab); names, st = [], None
    for j in range(k + 1):
        x = lab[j] if j < k else 'T'
        if x == 'B' or (x != 'I' and st is not None):
            if st is not None:
                e = j
                while e > st and toks[e-1][0] in sc.PUNCT: e -= 1
                names.append(text[toks[st][1]:toks[e-1][2]])
            st = j if x == 'B' else None
    return names
def predict_chain_ext(crf, text, use_rule=True):
    toks = sc.tokenize(text)[:sc.MAXTOK]
    lab = pred_labels(crf, toks)
    if use_rule: lab = extend_labels(toks, lab)
    return names_from(text, toks, lab)
if __name__ == '__main__':
    import pickle, sys
    ids = [l.split('\t')[0] for l in open(here + 'eval_labels.tsv', encoding='utf-8') if l.strip()]
    rows = ll.load_rows(ids); gold = ll.read_labels(here + 'eval_labels.tsv', rows)
    for pk in ('v3.pkl', 'v4.pkl'):
        crf = pickle.load(open(here + pk, 'rb'))
        for rule in (False, True):
            tp = fp = fn = ex = 0; bad = []
            for i, g in gold.items():
                p = predict_chain_ext(crf, rows[i][3], rule)
                gk = [ll.key(x) for x in g]; pk_ = [ll.key(x) for x in p]
                a, b = set(enumerate(gk)), set(enumerate(pk_)); tp += len(a & b); fp += len(b - a); fn += len(a - b)
                if gk == pk_: ex += 1
                else: bad.append(i)
            P = tp / (tp + fp); R = tp / (tp + fn)
            print(pk, 'rule' if rule else 'plain', 'exact', ex / len(gold), 'P %.3f R %.3f F1 %.3f' % (P, R, 2*P*R/(P+R)), bad if rule else '')
