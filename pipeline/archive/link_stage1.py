import sys, collections, time, pickle, math
sys.path.insert(0, '<WORKDIR>')
from link_lib import *
ANON = {'من','بعض','رجل','رجلا','عمن','شيخ','شيخا','رجال','احد','اهل','قوم','امراه','ناس','غير','فلان','انسان','ثقه','اصحاب','جماعه'}
REL = {'ابيه','ابوه','اباه','ابيها','ابي','جده','جدي','جدها','عمه','عمي','اخيه','امه','ابنه','عمها','خاله','ابوها','جدتها','ابيهم','اخوه','عمهم','جد','ابا','عنه','عنها'}
t0 = time.time(); P = load_profiles(); idx, first = build_index(P)
vocab = set(w for k in idx for w in k.split())
TOKS = {}
for i, p in P.items():
    ts = set()
    for fld in ('full_name', 'kunya', 'laqab', 'nasab'):
        v = p.get(fld)
        if v and v != '-': ts |= set(norm2(v).replace('ابن', 'بن').split())
    TOKS[i] = ts
ALIAS = {'الاصم': [64704], 'ابو العباس الاصم': [64704], 'ابو العباس محمد بن يعقوب': [64704], 'ابو العباس محمد بن يعقوب الاصم': [64704]}
def strict(key, c):
    kt = set(key.replace('ابن', 'بن').split())
    return [x for x in c if kt <= TOKS[x]]
def cands(key):
    c, l = cands0(key)
    if isinstance(l, str) or not c: return c, l
    if key in ALIAS: return ALIAS[key], 0
    f = strict(key, c)
    return (f, l) if f else ([], -1)
def cands0(key):
    t = key.split()
    if not t: return [], 'empty'
    if t[0] in ANON: return [], 'anon'
    if len(t) <= 2 and t[0] in REL: return [], 'rel'
    if key in ALIAS: return ALIAS[key], 0
    if key in idx: return sorted(idx[key]), 0
    # accusative -a ending and attached و/ف clitic on the first token
    t2 = [w[:-1] if (w.endswith('ا') and len(w) > 2 and w not in vocab and w[:-1] in vocab) else w for w in t]
    if len(t2[0]) > 2 and t2[0][0] in 'وف' and t2[0] not in vocab and t2[0][1:] in vocab: t2[0] = t2[0][1:]
    k2 = ' '.join(t2)
    if k2 != key and k2 in idx: return sorted(idx[k2]), 1
    for drop in range(1, min(4, len(t2) - 1)):
        k3 = ' '.join(t2[:len(t2) - drop])
        if len(t2) - drop >= 2 and k3 in idx: return sorted(idx[k3]), 1 + drop
    if len(t2) >= 3 and t2[0] in ('ابو', 'ابن', 'ام'):
        k3 = ' '.join(t2[1:])
        if k3 in idx: return sorted(idx[k3]), 5
    if len(t2) == 1 and t2[0] in idx: return sorted(idx[t2[0]]), 1
    return [], -1
key_id = {}; keys = []; kc = []; klev = []
def kid(raw):
    k = norm2(raw)
    if k not in key_id:
        key_id[k] = len(keys); keys.append(k); c, l = cands(k); kc.append(c); klev.append(l)
    return key_id[k]
chains = []     # (tag, src_row, book, num, [key ids], [raw names])
with open(S + 'sanadset.csv', encoding='utf-8', newline='') as f:
    r = csv.reader(f); next(r)
    for i, row in enumerate(r, 2):
        if row[4].strip() == 'No SANAD': continue
        try: names = ast.literal_eval(row[4])
        except Exception: continue
        chains.append(('orig', i, row[1], row[2], [kid(n) for n in names], names))
with open(S + 'nosanad_parsed_v3.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for row in r:
        if row[8] != 'parsed': continue
        names = ast.literal_eval(row[5])
        chains.append(('nosanad', int(row[0]), row[1], row[2], [kid(n) for n in names], names))
print('chains', len(chains), 'unique keys', len(keys), round(time.time() - t0), 's')
tot = sum(len(c[4]) for c in chains); cnt = collections.Counter(); lev = collections.Counter()
for c in chains:
    for k in c[4]:
        l = klev[k]; n = len(kc[k]); lev[l if isinstance(l, str) else 'name'] += 1
        if isinstance(l, str): continue
        cnt['0' if n == 0 else '1' if n == 1 else '2-5' if n <= 5 else '6-20' if n <= 20 else '>20'] += 1
print('mentions', tot, {k: f'{v/tot:.1%}' for k, v in lev.items()}); print({k: f'{v/tot:.1%}' for k, v in cnt.items()})
pickle.dump((chains, keys, kc, klev), open('link_stage1.pkl', 'wb'))
