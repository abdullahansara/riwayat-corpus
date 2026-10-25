import re, csv, json, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
PATH = '<ROOT>/SemanticHadithV2/ttl/SemanticHadithKGV2.ttl'
narr = {}            # HN id -> name
seg = {}             # seg id -> narrator id
chain = {}           # chain id -> (hadith id, [segment ids], root segment)
hadith_chain = {}    # hadith id -> chain id
blk = []
def first(pat, txt):
    m = re.search(pat, txt); return m.group(1) if m else None
def flush(b):
    if not b: return
    txt = ''.join(b); m = re.match(r'\s*(\S+)\s+rdf:type\s+owl:NamedIndividual\s*,\s*([^;.\n,]+)', txt)
    if not m: return
    sid, cls = m.group(1), m.group(2).strip()
    if cls == ':HadithNarrator':
        nm = first(r':name\s+"([^"]*?)(?:@ar)?"\^\^', txt)
        narr[sid] = nm
    elif cls in (':NarratorChainSegment', ':RootNarratorChainSegment'):
        seg[sid] = first(r':refersToNarrator\s+(:\S+)', txt)
    elif cls == ':NarratorChain':
        segs = re.search(r':hasNarratorSegment\s+(.*?)(?:;|\.\s*$)', txt, re.S)
        segl = re.findall(r':[\w\-]+ChainSeg-\d+', segs.group(1)) if segs else []
        root = first(r':hasRootNarratorSegment\s+(:\S+)', txt)
        chain[sid] = (first(r':isPartOfHadith\s+(:\S+)', txt), segl, root)
    elif cls == ':Hadith':
        hadith_chain[sid] = first(r':hasNarratorChain\s+(:\S+)', txt)
with open(PATH, encoding='utf-8') as f:
    for line in f:
        if line.startswith('###'): flush(blk); blk = []
        else: blk.append(line)
flush(blk)
log('narrators', len(narr), 'segments', len(seg), 'chains', len(chain), 'hadith', len(hadith_chain))
rows = []; bad = 0
for h, c in hadith_chain.items():
    if c not in chain: bad += 1; continue
    _, segl, root = chain[c]
    order = sorted(segl, key=lambda s: int(re.search(r'-(\d+)$', s).group(1)))
    if root: order.append(root)
    names = [narr.get(seg.get(s)) for s in order]
    m = re.match(r':([A-Za-z]+)-HD(\d+)', h)
    rows.append((h.lstrip(':'), m.group(1) if m else '', int(m.group(2)) if m else -1, len(names), json.dumps(names, ensure_ascii=False)))
with open('<ROOT>/SemanticHadithV2/sh_chains.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['sh_hadith', 'collection', 'number', 'n_narrators', 'narrators_ar']); w.writerows(rows)
cnt = collections.Counter(r[1] for r in rows); mx = collections.defaultdict(int)
for r in rows: mx[r[1]] = max(mx[r[1]], r[2])
log('written', len(rows), 'unresolved', bad)
print({k: (v, mx[k]) for k, v in cnt.most_common()})
print('narrators per chain:', sorted(collections.Counter(min(r[3], 14) for r in rows).items()))
print('missing narrator names:', sum(1 for r in rows if 'null' in r[4]))
for r in rows[:3]: print(r)
