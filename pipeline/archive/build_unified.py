import sys, csv, ast, re, hashlib, collections, time
sys.path.insert(0, '<WORKDIR>')
csv.field_size_limit(10**9)
S = r'<ROOT>/Sanadset/'
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
TAG = re.compile(r'<[^>]+>')
def clean_name(n): return re.sub(r'\s+', ' ', TAG.sub('', n)).strip()
CONF = {'unique', 'context', 'relative_father', 'alias_patch', 'unique+backoff', 'context+backoff'}
# --- parsed no-SANAD rows (small fields only)
ns = {}
with open(S + 'nosanad_parsed_v3.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        ns[int(x[0])] = (x[8], ast.literal_eval(x[5]) if x[8] == 'parsed' else [], x[6], x[9], x[10], x[11])
log('no-SANAD rows', len(ns))
# --- linked info for the no-SANAD portion; orig portion is streamed in order
lk_ns = {}
with open(S + 'sanadset_linked_final.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[0] == 'nosanad': lk_ns[int(x[1])] = (x[5], x[6], x[7])
log('linked no-SANAD chains', len(lk_ns))
lk_f = open(S + 'sanadset_linked_final.csv', encoding='utf-8-sig', newline=''); lk_r = csv.reader(lk_f); next(lk_r)
src = open(S + 'sanadset.csv', encoding='utf-8', newline=''); sr = csv.reader(src); next(sr)
out = open(S + 'hadith_unified.csv', 'w', encoding='utf-8-sig', newline=''); w = csv.writer(out)
w.writerow(['row_id','Book','Num_hadith','Matn','Narrators','Sanad_Length','Rijal_ids','Link_conf','Link_method','chain_source','no_chain_reason','inherits_chain_from_row','n_confident_links','qc_flags'])
seen = set(); C = collections.Counter(); F = collections.Counter()
for i, row in enumerate(sr, 2):
    H, book, num, matn, sanad, slen = row; flags = []
    names = []; ids = []; cf = []; mt = []; chain_source = 'none'; reason = ''; donor = ''
    if sanad.strip() != 'No SANAD':
        lk = next(lk_r); assert lk[0] == 'orig' and int(lk[1]) == i, (i, lk[:2])
        try: names = [clean_name(n) for n in ast.literal_eval(sanad)]
        except Exception: names = []; flags.append('sanad_unparseable')
        ids = ast.literal_eval(lk[5]); cf = ast.literal_eval(lk[6]); mt = ast.literal_eval(lk[7]); chain_source = 'original'
        if slen.strip().isdigit() and int(slen) != len(names): flags.append('orig_length_mismatch')
        if '<IDF>' in sanad: flags.append('idf_in_names')
        if '<SANAD>' not in H: flags.append('chain_without_sanad_tag')
    else:
        st, nms, pm, lsrc, rsn, dnr = ns[i]
        if st == 'parsed':
            names = [clean_name(n) for n in nms]; matn = pm; chain_source = 'parsed_' + ('gold' if lsrc == 'llm_gold' else 'model'); lkk = lk_ns[i]
            ids = ast.literal_eval(lkk[0]); cf = ast.literal_eval(lkk[1]); mt = ast.literal_eval(lkk[2])
        else: reason = rsn; donor = dnr
    if H.count('<SANAD>') > 1 or H.count('<MATN>') > 1: flags.append('multi_hadith_row')
    if len(matn.strip()) < 15: flags.append('matn_very_short')
    if not matn.strip(): flags.append('matn_empty')
    if len(matn) > 5000: flags.append('matn_very_long')
    if re.search(r'</?(?:SANAD|NAR|MATN|IDF)>', matn): flags.append('tags_in_matn')
    hk = hashlib.md5(H.encode()).digest()
    if hk in seen: flags.append('duplicate_row')
    else: seen.add(hk)
    if len(names) >= 15: flags.append('chain_len_ge15')
    if names:
        if len(names) != len(ids): flags.append('link_length_mismatch')
        if any(a is not None and a == b for a, b in zip(ids, ids[1:])): flags.append('adjacent_same_narrator')
        nconf = sum(1 for m, c in zip(mt, cf) if m in CONF and c >= 0.8)
        if nconf == len(names): C['fully_confident_chains'] += 1
        elif nconf == 0: flags.append('no_confident_link')
        else: pass
    else: nconf = 0
    for fl in flags: F[fl] += 1
    C[chain_source] += 1
    w.writerow([i, book, num, matn.strip(), repr(names), len(names), repr(ids), repr(cf), repr(mt), chain_source, reason, donor, nconf, ';'.join(flags)])
    if i % 100000 == 0: log('rows', i)
log('DONE'); print(dict(C)); print('QC FLAGS:'); [print(f'  {k:28s} {v:8d}') for k, v in F.most_common()]
