"""Phase 1 - build chunk files for Claude labelling (read-only on the DB).
Each item holds the text (truncated at 2500 chars), the current matn boundary, the current chain mentions and, per mention, a short candidate list
(registry owners of the surface + the current guess + neighbour-edge candidates) so that a labeller can choose an ID without database access.
The labeller answers with phrases copied from the text (not offsets); labels_to_offsets() in fix_20 locates them.
  python pipeline/fix_19_label_sampler.py SIZE CHUNK_SIZE SEED OUTDIR [--exclude-file f]   e.g. 300 60 1 labels/pilot"""
from paths import *
import sqlite3, sys, re, json, random, collections, os
N, CH, SEED, OUTD = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
excl = set()
if '--exclude-file' in sys.argv:
    for l in open(sys.argv[sys.argv.index('--exclude-file') + 1], encoding='utf-8'): excl.add(json.loads(l)['id'])
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
random.seed(SEED)
gold = {json.loads(l)['hadith_id'] for l in open(os.path.join(os.path.dirname(PIPE.rstrip('/\\')), 'gold', 'gold_chains.jsonl'), encoding='utf-8')} if PIPE else set()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
# strata: (name, sql where, share)
STRATA = [('A', "chain_tier='A'", .18), ('B', "chain_tier='B'", .25), ('C', "chain_tier='C'", .25), ('none', "chain_tier='none'", .10),
          ('shia', "tradition='shia' and chain_tier!='none'", .07), ('gap', "flags like '%gap_filled%'", .07), ('inchain', "flags like '%matn_start_extended%' or flags like '%matn_start_inferred%'", .08)]
ids = []
if '--ids-file' in sys.argv:
    ids = [l.strip() for l in open(sys.argv[sys.argv.index('--ids-file') + 1]) if l.strip()]; random.shuffle(ids); STRATA = []
for name, where, share in STRATA:
    rows = [r[0] for r in c.execute(f"select id from hadith where ({where}) and id in (select id from hadith order by random() limit 4000) ").fetchall()]
    random.shuffle(rows); take = [h for h in rows if h not in gold and h not in excl and h not in ids][:round(N * share)]; ids += take
ids = ids[:N]; random.shuffle(ids)
print(len(ids), 'selected')
exact = collections.defaultdict(set)
for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
info = {i: ((n or '')[:70], d) for i, n, d in c.execute('select id,std_name,death_year from narrator')}
edge = collections.defaultdict(dict)
for s, t, n in c.execute('select student,teacher,n_hadith from narrator_edge where n_hadith>=2'): edge[s][t] = n
tedge = collections.defaultdict(dict)
for s, t, n in c.execute('select student,teacher,n_hadith from narrator_edge where n_hadith>=2'): tedge[t][s] = n
os.makedirs(OUTD, exist_ok=True)
items = []
for hid in ids:
    tid, trad, book, text, ms, me, tier, fl = c.execute('select id,tradition,book,text,matn_start,matn_end,chain_tier,flags from hadith where id=?', (hid,)).fetchone()
    mens = c.execute('select pos,start,end,surface,narrator_id,guess_narrator_id,chain_no from chain_mention where hadith_id=? and start is not null order by start limit 30', (hid,)).fetchall()
    ments = []
    for k, (pos, s, e, surf, nid, g, cn) in enumerate(mens):
        cand = []
        for x in [nid, g] + sorted(exact.get(norm(surf), ()), key=lambda x: -pop.get(x, 0))[:8]:
            if x and x not in cand: cand.append(x)
        prev = mens[k - 1][4] if k and mens[k - 1][4] else None; nxt = mens[k + 1][4] if k + 1 < len(mens) and mens[k + 1][4] else None
        if prev:
            for t, n in sorted(edge.get(prev, {}).items(), key=lambda x: -x[1])[:3]:
                if t not in cand and len(cand) < 10 and norm(surf) and set(norm(surf).split()) & set(norm(info[t][0]).split()): cand.append(t)
        ments.append({'i': k, 'surface': surf, 'start': s, 'cur_id': nid, 'cur_guess': g, 'cands': [{'id': x, 'name': info[x][0], 'died': info[x][1]} for x in cand if x in info]})
    items.append({'id': hid, 'tradition': trad, 'book': book, 'tier': tier, 'flags': fl, 'text': text[:2500], 'truncated': len(text) > 2500,
                  'cur_matn_start_text': text[ms:ms + 60] if ms is not None else None, 'cur_matn_end_text': text[max(0, (me or 0) - 60):me] if me else None, 'mentions': ments})
for k in range(0, len(items), CH):
    json.dump(items[k:k + CH], open(os.path.join(OUTD, f'chunk_{k // CH:03d}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
with open(os.path.join(OUTD, 'ids.jsonl'), 'w', encoding='utf-8') as f:
    for it in items: f.write(json.dumps({'id': it['id'], 'tier': it['tier']}) + '\n')
print(len(items), 'items in', (len(items) + CH - 1) // CH, 'chunks ->', OUTD)
