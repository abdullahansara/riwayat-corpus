import csv, json, re, collections, openpyxl, random, time
csv.field_size_limit(10**9)
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
D = '<ROOT>/MIDS_SahihMuslim/'
# ---- SemanticHadith narrator ids per Muslim hadith, and names
sh_ids = {}; sh_name = {}
nar = {}
with open('<ROOT>/SemanticHadithV2/sh_chains_ids.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[1] != 'SM': continue
        ids = json.loads(x[5]); nm = json.loads(x[4]); sh_ids[int(x[2])] = [i for i in ids if i]
        for i, n in zip(ids, nm):
            if i and n: sh_name[i] = n
# ---- MIDS persons per hadith, names
def rows(fn):
    ws = openpyxl.load_workbook(D + fn, read_only=True).worksheets[0]; it = ws.iter_rows(values_only=True); h = next(it)
    for r in it:
        if r and r[0] is not None: yield dict(zip(h, r))
mp = collections.defaultdict(set)
for r in rows('3_Hadith_SahihMuslim_Isnad=Edges for Graph.xlsx'):
    h = int(r['HadithNo']); mp[h].add(str(r['sourceNarratorID'])); mp[h].add(str(r['targetNarratorID']))
mname = {k: v[0] for k, v in json.load(open(D + 'mids_nodes.json', encoding='utf-8')).items()}
pairs = json.load(open('<ROOT>/SemanticHadithV2/sh_muslim_to_mids.json'))
P = [(int(n), v[0]) for n, v in pairs.items() if v[2] == 1 and v[1] in ('full', 'head+tail')]      # clean 1-to-1 text matches only
log('clean SH<->MIDS pairs:', len(P))
nsh = collections.Counter(); nm_ = collections.Counter(); C = collections.Counter()
for n, h in P:
    S = set(sh_ids.get(n, [])); M = mp.get(h, set())
    for s in S: nsh[s] += 1
    for m in M: nm_[m] += 1
    for s in S:
        for m in M: C[(s, m)] += 1
best = {}
for (s, m), c in C.items():
    if c < 2: continue
    j = c / (nsh[s] + nm_[m] - c)
    if s not in best or j > best[s][1]: best[s] = (m, j, c)
conf = {s: v for s, v in best.items() if v[1] >= 0.7}
log('SH narrators:', len(nsh), '| with a crosswalk candidate:', len(best), '| confident (Jaccard >= 0.7):', len(conf))
mentions = sum(nsh.values()); cm = sum(nsh[s] for s in conf)
log(f'share of SH narrator occurrences covered by the confident crosswalk: {cm/mentions:.1%}')
# distribution of Jaccard
bins = collections.Counter(min(int(v[1] * 10), 9) / 10 for v in best.values())
log('best-Jaccard distribution:', dict(sorted(bins.items())))
# validation: map SH set -> MIDS ids and compare with MIDS persons
res = collections.Counter()
for n, h in P:
    S = [s for s in set(sh_ids.get(n, []))]; M = mp.get(h, set())
    if not S or not M: continue
    mapped = {conf[s][0] for s in S if s in conf}; unm = [s for s in S if s not in conf]
    if unm: res['has SH narrators with no confident crosswalk'] += 1; continue
    if mapped == M: res['EXACT: mapped SH set == MIDS set'] += 1
    elif mapped <= M: res['MIDS has extra narrators'] += 1
    elif M <= mapped: res['SH has extra narrators'] += 1
    else: res['both differ'] += 1
tot = sum(res.values()); log('validation on hadith where every SH narrator has a crosswalk entry:', tot)
for k, v in res.most_common(): print(f'   {v:5d}  {v/tot:5.1%}  {k}')
random.seed(3); top = sorted(conf.items(), key=lambda kv: -nsh[kv[0]])[:14] + random.sample(list(conf.items()), 8)
print('\nSAMPLE of crosswalk (SH narrator <-> MIDS person, Jaccard, #hadith):')
for s, (m, j, c) in top: print(f'   {sh_name.get(s, "?")[:34]:36s} <-> {mname.get(m, "?")[:34]:36s} J={j:.2f} n={c}')
json.dump({s: {'mids_id': v[0], 'jaccard': round(v[1], 3), 'n': v[2]} for s, v in conf.items()}, open('<ROOT>/SemanticHadithV2/crosswalk_sh_to_mids.json', 'w'))
