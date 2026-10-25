from paths import *
import csv, json, sqlite3, re, ast, collections, time, os, gc
csv.field_size_limit(10**9)
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
H = SRC + 'HadithKG/'; OUTDIR = OUT + ''; os.makedirs(OUTDIR, exist_ok=True)
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
def year(s):
    m = re.search(r'(\d{1,4})\s*هـ', str(s or '')) or re.search(r'^\s*(\d{1,4})\s*$', str(s or ''))
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 1500 else None
nodes = {}          # key -> {'src','sid','name','attrs':{}, 'names':[(form,type)]}
def node(src, sid, name):
    k = f'{src}:{sid}'
    if k not in nodes: nodes[k] = {'src': src, 'sid': str(sid), 'name': name, 'attrs': {}, 'names': []}
    return nodes[k]
def addname(nd, form, typ):
    form = (form or '').strip()
    if form and form != '-' and len(norm(form)) >= 2: nd['names'].append((form, typ))
# ---------------- hadith-kg narrators
con = sqlite3.connect('file:' + SRC + 'HadithKG/hadith-kg.db?mode=ro', uri=True)
for rid, name, nick, tab, by in con.execute('select id, name, nickname, tabaka, birth_year from rawis'):
    nd = node('kg', rid, name); addname(nd, name, 'full'); addname(nd, nick, 'popular'); nd['attrs'].update({'tabaqa': tab, 'birth_year': by if isinstance(by, int) else year(by)})
log('kg narrators', sum(1 for k in nodes if k.startswith('kg:')))
# ---------------- Itqan profiles + AR-Sanad narrator table (same id space)
D = SRC + 'Rijal_Itqan/rijal/'
for g in ['companion', 'reliable', 'mostly_reliable', 'weak', 'abandoned', 'fabricator', 'unknown']:
    for k, p in json.load(open(D + f'profiles_{g}.json', encoding='utf-8')).items():
        nd = node('itq', p['id'], p['full_name']); addname(nd, p['full_name'], 'full'); addname(nd, p.get('kunya'), 'kunya'); addname(nd, p.get('laqab'), 'laqab')
        for v in (p.get('namings') or []): addname(nd, v, 'variant')
        nd['attrs'].update({'death_year': year(p.get('death')), 'tabaqa': p.get('tabaqat'), 'city': p.get('city'), 'nasab': p.get('nasab')})
        nd['teachers'] = p.get('teachers') or []; nd['students'] = p.get('students') or []
    gc.collect()
log('itqan profiles', sum(1 for k in nodes if k.startswith('itq:')))
with open(SRC + 'ARSanad/Narrators data.csv', encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        nd = node('itq', int(r['id']), r['name']); addname(nd, r['name'], 'full'); addname(nd, r['kunia'], 'kunya'); addname(nd, r['laqab'], 'laqab'); addname(nd, r['shuhra'], 'popular')
        try:
            for v in ast.literal_eval(r['namings']): addname(nd, v, 'variant')
        except Exception: pass
        a = nd['attrs']; a.setdefault('death_year', year(r['death_year'])); a['death_year'] = a['death_year'] or year(r['death_year']); a['birth_year'] = year(r['birth_year']) or a.get('birth_year')
        a['tabaqa'] = a.get('tabaqa') or r['tabaqa']; a['city'] = a.get('city') or r['living_city']; a['madhhab'] = r['mazhab']; a['death_city'] = r['death_city']; a['family'] = r['selat_karaba']; a['tribe_nisba'] = r['nasab']
        a['ar_sanad'] = 1
        for fld, key in (('narrated_from', 'teachers'), ('narrated_to', 'students')):
            try: nd.setdefault(key, []); nd[key] = list(set(nd[key]) | set(ast.literal_eval(r[fld])))
            except Exception: pass
log('after AR-Sanad merge: itqan-space nodes', sum(1 for k in nodes if k.startswith('itq:')))
# ---------------- SemanticHadith narrators (from the TTL)
def first(pat, txt):
    m = re.search(pat, txt); return m.group(1).replace('@ar', '').strip() if m else None
blk = []
def flush(b):
    if not b: return
    txt = ''.join(b); m = re.match(r'\s*:(HN\d+)\s+rdf:type\s+owl:NamedIndividual\s*,\s*:HadithNarrator', txt)
    if not m: return
    nd = node('sh', m.group(1), first(r':name\s+"([^"]*)"', txt)); addname(nd, nd['name'], 'full')
    for fld, typ in (('teknonym', 'kunya'), ('popularName', 'popular'), ('title', 'laqab'), ('lineage', 'nasab_nisba')): addname(nd, first(rf':{fld}\s+"([^"]*)"', txt), typ)
    nd['attrs'].update({'death_year': year(first(r':deathYear\s+"([^"]*)"', txt)), 'tabaqa': first(r':generation\s+"([^"]*)"', txt), 'city': first(r':deathPlace\s+"([^"]*)"', txt)})
with open(SRC + 'SemanticHadithV2/ttl/SemanticHadithKGV2.ttl', encoding='utf-8') as f:
    for line in f:
        if line.startswith('###'): flush(blk); blk = []
        else: blk.append(line)
flush(blk); log('SH narrators', sum(1 for k in nodes if k.startswith('sh:')))
# ---------------- MIDS
for k, v in json.load(open(SRC + 'MIDS_SahihMuslim/mids_nodes.json', encoding='utf-8')).items():
    nd = node('mids', k, v[0]); addname(nd, v[0], 'full'); nd['attrs']['tabaqa'] = v[1]
log('MIDS narrators', sum(1 for k in nodes if k.startswith('mids:')))
# ---------------- Thaqalayn (Shi'i) narrators, if the checkout is done
tp = SRC + 'ThaqalaynData_clone/repo/people/narrators/index.json'
if os.path.exists(tp):
    idx = json.load(open(tp, encoding='utf-8'))['data']
    for k, v in idx.items():
        t = v.get('titles') or {}; nd = node('thq', k, t.get('ar')); addname(nd, t.get('ar'), 'full'); addname(nd, t.get('en'), 'english')
        nd['attrs'].update({'narrations': v.get('narrations')}); nd['tradition'] = 'shia'
    log('Thaqalayn narrators', sum(1 for k in nodes if k.startswith('thq:')))
else: log('Thaqalayn people index not available yet (skipped)')
# ---------------- crosswalk edges
edges = []
for k, v in json.load(open(H + 'crosswalk_kg_to_itqan.json')).items(): edges.append((f'kg:{k}', f'itq:{v["itqan"]}', 'kg~itqan', v['jaccard']))
sh_to_mids = json.load(open(SRC + 'SemanticHadithV2/crosswalk_sh_to_mids.json'))
for k, v in sh_to_mids.items(): edges.append((f'sh:{k.lstrip(":")}', f'mids:{v["mids_id"]}', 'sh~mids', v['jaccard']))
# SH <-> kg : position-aligned mentions in the SH-validated hadith
shids = {}
with open(SRC + 'SemanticHadithV2/sh_chains_ids.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r: shids[(x[1], int(x[2]))] = [i.lstrip(':') if i else None for i in json.loads(x[5])]
recs = [json.loads(l) for l in open(H + 'gold_sh_validated.jsonl', encoding='utf-8')]
C = collections.Counter(); ns = collections.Counter(); nk = collections.Counter()
for i in range(0, len(recs), 3000):
    ch = recs[i:i + 3000]; ks = [d['kid'] for d in ch]; q = ','.join('?' * len(ks)); M = collections.defaultdict(list)
    for h, seq, rid in con.execute(f'select hadith_id, seq, rawi_id from hadith_rawis where hadith_id in ({q}) order by hadith_id, seq', ks): M[h].append(rid)
    for d in ch:
        a = shids.get((d['col'], d['num']), []); b = M.get(d['kid'], [])
        if len(a) != len(b): continue
        for s, k in zip(a, b):
            if s and k: C[(s, k)] += 1; ns[s] += 1; nk[k] += 1
bs = {}; bk = {}
for (s, k), c in C.items():
    j = c / (ns[s] + nk[k] - c)
    if s not in bs or j > bs[s][1]: bs[s] = (k, j, c)
    if k not in bk or j > bk[k][1]: bk[k] = (s, j, c)
n_shkg = 0
for s, (k, j, c) in bs.items():
    if bk.get(k, (None,))[0] == s and j >= 0.6 and c >= 3: edges.append((f'sh:{s}', f'kg:{k}', 'sh~kg', round(j, 3))); n_shkg += 1
log('crosswalk edges: kg~itqan', sum(1 for e in edges if e[2] == 'kg~itqan'), '| sh~mids', sum(1 for e in edges if e[2] == 'sh~mids'), '| sh~kg', n_shkg)
# ---------------- union-find -> canonical narrators
par = {k: k for k in nodes}
def find(x):
    while par[x] != x: par[x] = par[par[x]]; x = par[x]
    return x
bad = 0
for a, b, t, j in edges:
    if a in par and b in par:
        ra, rb = find(a), find(b)
        if ra != rb: par[ra] = rb
    else: bad += 1
# ---- second pass: merge still-unlinked nodes with an identical, unique full name (Sunni-side sources only; death years must not conflict)
srcs = collections.defaultdict(set)
for k in nodes: srcs[find(k)].add(nodes[k]['src'])
by = collections.defaultdict(lambda: collections.defaultdict(list))
for k, nd in nodes.items():
    if nd['src'] in ('kg', 'itq', 'sh') and nd['name']:
        nn = norm(nd['name'])
        if len(nn.split()) >= 3: by[nn][nd['src']].append(k)
n_name = 0; skipped_conflict = 0
for nn, d in by.items():
    if sum(1 for v in d.values() if v) < 2: continue
    if any(len(v) != 1 for v in d.values()): continue                      # name must be unique inside every source
    ks = [v[0] for v in d.values()]; roots = {find(k) for k in ks}
    if len(roots) == 1: continue
    if any(len(srcs[find(k)] - {nodes[k]['src']}) > 0 for k in ks): continue   # each node must still be unlinked to the others' sources
    yrs = [nodes[k]['attrs'].get('death_year') for k in ks if nodes[k]['attrs'].get('death_year')]
    if yrs and max(yrs) - min(yrs) > 3: skipped_conflict += 1; continue
    for k in ks[1:]: par[find(k)] = find(ks[0])
    n_name += 1
log('name-exact merges:', n_name, '| skipped (death years conflict):', skipped_conflict)
comp = collections.defaultdict(list)
for k in nodes: comp[find(k)].append(k)
log('canonical narrators:', len(comp), '| edges skipped (node missing):', bad, '| multi-source narrators:', sum(1 for v in comp.values() if len(v) > 1))
# ---------------- write master DB
PRIO = ['sh', 'itq', 'kg', 'mids', 'thq']
db = sqlite3.connect(OUTDIR + 'hadith_master.db'); c = db.cursor()
c.executescript('''
DROP TABLE IF EXISTS narrator; DROP TABLE IF EXISTS narrator_name; DROP TABLE IF EXISTS narrator_source_id; DROP TABLE IF EXISTS narrator_edge_seed;
CREATE TABLE narrator(id TEXT PRIMARY KEY, std_name TEXT, std_name_source TEXT, tradition TEXT, death_year INT, birth_year INT, tabaqa TEXT, city TEXT, death_city TEXT, madhhab TEXT, tribe_nisba TEXT, family TEXT, n_sources INT);
CREATE TABLE narrator_name(narrator_id TEXT, form TEXT, norm TEXT, type TEXT, source TEXT, observed_count INT DEFAULT 0);
CREATE TABLE narrator_source_id(narrator_id TEXT, source TEXT, source_id TEXT, source_name TEXT);
CREATE TABLE narrator_edge_seed(student TEXT, teacher TEXT, source TEXT);
CREATE INDEX ix_nn ON narrator_name(norm); CREATE INDEX ix_nid ON narrator_name(narrator_id); CREATE INDEX ix_sid ON narrator_source_id(source, source_id);
''')
order = sorted(comp.values(), key=lambda m: -len(m)); canon = {}; seen_names = 0
for n, members in enumerate(order, 1):
    nid = 'N%07d' % n; members.sort(key=lambda k: PRIO.index(nodes[k]['src']))
    best = next((nodes[k] for k in members if nodes[k]['name']), nodes[members[0]]); at = {}
    for k in members:
        for a, v in nodes[k]['attrs'].items():
            if v not in (None, '', '-') and a not in at: at[a] = v
        canon[k] = nid
    trad = 'shia' if any(nodes[k].get('tradition') == 'shia' for k in members) and not any(nodes[k]['src'] != 'thq' for k in members) else 'sunni_or_unknown'
    c.execute('INSERT INTO narrator VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (nid, best['name'], best['src'], trad, at.get('death_year'), at.get('birth_year'), str(at.get('tabaqa')) if at.get('tabaqa') else None, at.get('city'), at.get('death_city'), at.get('madhhab'), at.get('tribe_nisba'), at.get('family'), len({nodes[k]['src'] for k in members})))
    seen = set()
    for k in members:
        nd = nodes[k]; c.execute('INSERT INTO narrator_source_id VALUES(?,?,?,?)', (nid, nd['src'], nd['sid'], nd['name']))
        for form, typ in nd['names']:
            nn = norm(form)
            if (nn, typ) in seen: continue
            seen.add((nn, typ)); c.execute('INSERT INTO narrator_name(narrator_id,form,norm,type,source) VALUES(?,?,?,?,?)', (nid, form, nn, typ, nd['src']))
    if n % 40000 == 0: db.commit(); log('written narrators', n)
db.commit()
for k, nd in nodes.items():
    if nd['src'] != 'itq': continue
    for t in nd.get('teachers', []):
        tk = f'itq:{t}'
        if tk in canon: c.execute('INSERT INTO narrator_edge_seed VALUES(?,?,?)', (canon[k], canon[tk], 'itqan/arsanad'))
db.commit()
json.dump(canon, open(OUTDIR + 'node_to_canonical.json', 'w'))
tot = c.execute('select count(*) from narrator').fetchone()[0]; nm = c.execute('select count(*) from narrator_name').fetchone()[0]; ed = c.execute('select count(*) from narrator_edge_seed').fetchone()[0]
log(f'DONE: {tot} narrators | {nm} name forms | {ed} seed teacher-student edges')
