from paths import *
import csv, json, sqlite3, re, ast, collections, time, os, sys, importlib.util, gc
csv.field_size_limit(10**9)
HERE = PIPE
sys.path.insert(0, HERE)
import pycrfsuite
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
HM = OUT + ''; H = SRC + 'HadithKG/'; S = SRC + 'Sanadset/'; TQ = SRC + 'ThaqalaynData_clone/'
PARSER = sys.argv[1] if len(sys.argv) > 1 else 'parser_v8'
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else None
def load(name, fn):
    sp = importlib.util.spec_from_file_location(name, HERE + fn); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
sc = load('sc', 'sanad_crf.py'); N = sc.norm
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
# ---------------- narrator lookups
canon = json.load(open(HM + 'node_to_canonical.json'))
mdb = sqlite3.connect(HM + 'hadith_master.db')
name2n = collections.defaultdict(list)
for nid, nn in mdb.execute('select narrator_id, norm from narrator_name'):
    if nn: name2n[nn].append(nid)
nsrc = dict(mdb.execute('select id, n_sources from narrator').fetchall()); log('narrator names indexed:', len(name2n))
def clean_name_key(s):
    t = norm(s).split()
    if t and len(t[0]) > 2 and t[0][0] == 'و' and t[0][1:]: t[0] = t[0][1:]
    return ' '.join(t)
def lookup(surface):
    k = clean_name_key(surface); c = list(dict.fromkeys(name2n.get(k, [])))
    if not c: return None, 0.0, [], 'unresolved'
    if len(c) == 1: return c[0], 0.85, [], 'name_lookup_unique'
    c.sort(key=lambda n: -nsrc.get(n, 0)); return c[0], 0.35, c[1:4], 'name_lookup_ambiguous'
# ---------------- parser (fallback for hadith with no chain from any source)
WS = json.load(open(H + PARSER + '_wordstats.json', encoding='utf-8'))
TRANSW = {'حدثنا', 'حدثني', 'اخبرنا', 'اخبرني', 'انبانا', 'ثنا', 'ثني', 'نا', 'انا', 'سمعت', 'عن', 'قال', 'قالا', 'قالوا', 'كما', 'وحدثنا', 'وحدثني', 'ح'}
def nb(w):
    c = WS.get(w)
    if not c: return 'U'
    n = c[0] + c[1]; return '%d%s' % (int(8 * c[0] / n), 'h' if n >= 50 else 'l')
def feats(toks):
    n = len(toks); nt = [N(t) for t in toks]; nbs = [nb(w) for w in nt]; out = []; q = c = False
    for i, t in enumerate(toks):
        w = nt[i]; f = ['b', 'w=' + w, 'nb=' + nbs[i], 'q=%d' % q, 'c=%d' % c, 'p=%d' % (t in sc.PUNCT), 'tw=%d' % (w in TRANSW)]
        if t not in sc.PUNCT:
            ld = sc.DIAC.findall(t); f.append('ld=' + (ld[-1] if ld else '-'))
        for o in (-2, -1, 1, 2):
            j = i + o; f.append('w%+d=%s' % (o, nt[j] if 0 <= j < n else '#')); f.append('nb%+d=%s' % (o, nbs[j] if 0 <= j < n else '#'))
        f.append('bg-=' + (nt[i - 1] if i else '<s>') + '|' + w); f.append('bg+=' + w + '|' + (nt[i + 1] if i + 1 < n else '</s>'))
        f.append('ptw=%d' % (i > 0 and nt[i - 1] in TRANSW)); f.append('pos=%d' % min(i, 12))
        out.append(f)
        if t in ('"', '“', '”', '«'): q = True
        if t == ':': c = True
    return out
tg = pycrfsuite.Tagger(); tg.open(H + PARSER + '.crfsuite')
def parse_text(text):
    toks = sc.tokenize(text)[:200]
    if not toks: return [], None
    lab = tg.tag(feats([t[0] for t in toks])); spans = []; st = None
    for j in range(len(lab) + 1):
        x = lab[j] if j < len(lab) else 'T'
        if x == 'B' or (x != 'I' and st is not None):
            if st is not None:
                e = j
                while e > st and toks[e - 1][0] in sc.PUNCT: e -= 1
                if e > st: spans.append((toks[st][1], toks[e - 1][2]))
            st = j if x == 'B' else None
    spans = [(a, b) for a, b in spans if norm(' '.join(t[0] for t in toks if a <= t[1] < b)) not in ('قال', 'عن', 'حدثنا', 'اخبرنا', 'حدثني', 'اخبرني', 'ثنا', 'سمعت', 'وقال', 'قالا', 'قالوا', 'ح')]
    fm = next((j for j, x in enumerate(lab) if x == 'M'), None)
    return spans, (toks[fm][1] if fm is not None else None)

_DI = re.compile('[ً-ْٰـ]'); _TRN = str.maketrans('أإآى', 'اااي')
def _n(x): return re.sub('[^ء-ي ]', ' ', _DI.sub('', x).translate(_TRN))
_FILL = set('عن قال قالا قالوا حدثنا حدثني اخبرنا اخبرني اخبرنى حدثنى ثنا انبانا سمعت وعن وقال و في ان انه رحمه الله رضي رضى عنه عنها عليه السلام صلى وسلم واله تعالى ايضا ثم عنهم عنهما قراءة عليه بن ابن'.split())
_TW = {'قال', 'عن', 'حدثنا', 'اخبرنا', 'حدثني', 'اخبرني', 'ثنا', 'سمعت', 'وعنه', 'عنه', 'وقال'}
def shia_ok(d):
    ct = d['chain_text']; sp = d['spans']; rest = []; pos = 0
    for a, b in sp: rest.append(ct[pos:a]); pos = b
    rest.append(ct[pos:])
    left = [w for w in _n(' '.join(rest)).split() if w not in _FILL and not w.isdigit()]
    if len(left) >= 3 or any(re.search(r'(?:^|\s)(?:بن|ابن)(?:\s)', _n(r)) for r in rest): return False
    return not any(_n(ct[a:b]).strip() in _TW for a, b in sp)
# ---------------- helpers
def tag_text(text, spans, ids):
    ok = sorted((a, b, i) for (a, b), i in zip(spans, ids) if a is not None)
    out = []; pos = 0
    for a, b, i in ok:
        if a < pos or b > len(text): return None
        out.append(text[pos:a]); out.append('<N id="%s">' % (i or '?') + text[a:b] + '</N>'); pos = b
    out.append(text[pos:]); return ''.join(out)
def find_spans(text, names):
    spans = []; pos = 0
    for n in names:
        n = n.strip(); i = text.find(n, pos)
        if i < 0: spans.append((None, None)); continue
        spans.append((i, i + len(n))); pos = i + len(n)
    return spans
def tag_offsets(Hs):
    parts = re.split(r'(<[^>]+>)', Hs); out = []; pos = 0; nar = []; cur = None; ms = me = None
    for p in parts:
        if p.startswith('<') and p.endswith('>'):
            t = p.strip('<>').strip()
            if t == 'NAR': cur = pos
            elif t == '/NAR' and cur is not None: nar.append((cur, pos)); cur = None
            elif t == 'MATN': ms = pos
            elif t == '/MATN': me = pos
        else: out.append(p); pos += len(p)
    text = ''.join(out); trimmed = []
    for a, b in nar:
        seg = text[a:b]; a2 = a + (len(seg) - len(seg.lstrip())); b2 = b - (len(seg) - len(seg.rstrip())); trimmed.append((a2, b2))
    return text, trimmed, ms, me
# ---------------- DB
db = sqlite3.connect(HM + 'hadith_master.db'); c = db.cursor()
c.executescript('''
DROP TABLE IF EXISTS hadith; DROP TABLE IF EXISTS chain_mention; DROP TABLE IF EXISTS reference_chain;
CREATE TABLE hadith(id TEXT PRIMARY KEY, tradition TEXT, book TEXT, number TEXT, source_ids TEXT, text TEXT, text_tagged TEXT, matn_start INT, matn_end INT, chain_source TEXT, chain_tier TEXT, n_narrators INT, flags TEXT);
CREATE TABLE chain_mention(hadith_id TEXT, pos INT, start INT, end INT, surface TEXT, narrator_id TEXT, id_method TEXT, id_confidence REAL, id_source_ref TEXT, alternatives TEXT, flags TEXT);
CREATE TABLE reference_chain(source TEXT, unit TEXT, sanad_no INT, narrator_ids TEXT, hadith_id TEXT);
''')
hid_n = [0]; HB = []; MB = []; stat = collections.Counter(); tier_ct = collections.Counter()
def add(tradition, book, number, srcids, text, spans, ids, meths, confs, refs, alts, flags, chain_source, tier, ms, me):
    hid_n[0] += 1; hid = 'H%07d' % hid_n[0]; flags = list(flags)
    tagged = tag_text(text, spans, ids) if spans and any(a is not None for a, _ in spans) else None
    if spans and tagged is None: flags.append('tag_overlap_or_range')
    HB.append((hid, tradition, book, str(number), json.dumps(srcids), text, tagged, ms, me, chain_source, tier, len(ids), ';'.join(flags)))
    for p, ((a, b), nid, m, cf, rf, al) in enumerate(zip(spans, ids, meths, confs, refs, alts), 1):
        sf = text[a:b] if a is not None else None
        MB.append((hid, p, a, b, sf, nid, m, cf, rf, json.dumps(al) if al else None, None if a is not None else 'span_not_located'))
    stat['hadith'] += 1; tier_ct[tier] += 1
    if len(HB) >= 20000: flush()
def flush():
    c.executemany('INSERT INTO hadith VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', HB); c.executemany('INSERT INTO chain_mention VALUES(?,?,?,?,?,?,?,?,?,?,?)', MB); db.commit(); HB.clear(); MB.clear()
# ---------------- alignment + Sanadset side tables
al = {}; san_covered = set(); cat = {}
with open(S + 'align_sanadset_kg.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[2]:
            san_covered.add(int(x[0]))
            if x[4] in ('full', 'head+tail') and x[5] == '1': al.setdefault(int(x[2]), int(x[0]))
with open(S + 'chain_agreement.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r: cat[int(x[0])] = x[2]
log('aligned kg->sanadset:', len(al), '| sanadset rows covered by a kg hadith:', len(san_covered))
parsed = {}                 # sanadset row -> parsed chain info (our no-SANAD parse)
with open(S + 'nosanad_parsed_v3.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[8] == 'parsed': parsed[int(x[0])] = {'text': x[3], 'names': ast.literal_eval(x[4]), 'matn': x[6], 'src': x[9]}
with open(S + 'sanadset_linked_final.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r:
        if x[0] == 'nosanad' and int(x[1]) in parsed:
            parsed[int(x[1])].update({'ids': ast.literal_eval(x[5]), 'conf': ast.literal_eval(x[6]), 'meth': ast.literal_eval(x[7])})
log('parsed no-SANAD chains loaded:', len(parsed))
def itq_canon(i): return canon.get(f'itq:{i}') if i is not None else None
# ---------------- PHASE K: hadith-kg hadith (priority 1)
con = sqlite3.connect('file:' + SRC + 'HadithKG/hadith-kg.db?mode=ro', uri=True)
books = dict(con.execute('select id, name from books').fetchall())
con2 = sqlite3.connect('file:' + SRC + 'HadithKG/hadith-kg.db?mode=ro', uri=True)
cur_main = con2.execute('select id, book_id, no_inbook, nass, matn_start, matn_end from hadiths' + (f' limit {LIMIT}' if LIMIT else ''))
done_k = 0
while True:
    ch = cur_main.fetchmany(4000)
    if not ch: break
    q = ','.join('?' * len(ch)); ids_ = [r[0] for r in ch]; M = collections.defaultdict(list)
    for h, a, b, rid in con.execute(f'select hadith_id, start, end, rawi_id from hadith_rawis where hadith_id in ({q}) order by hadith_id, seq', ids_): M[h].append((a, b, rid))
    for hid, bid, no, nass, ms, me in ch:
        if not nass: stat['kg_no_text'] += 1; continue
        book = books.get(bid, ''); sp = M.get(hid, []); srow = al.get(hid)
        pre = [m for m in sp if ms is not None and m[1] <= ms + 5]
        if pre:
            cp = cat.get(srow); tier = 'A' if cp in ('identical', 'same_chain_name_variants') else 'B'; fl = [] if tier == 'A' or srow is None else ['sources_disagree'] if cp not in (None,) else []
            spans = [(a, b) for a, b, _ in pre]; ids = []; meths = []; confs = []; refs = []
            for a, b, rid in pre:
                nid = canon.get(f'kg:{rid}') if rid else None
                ids.append(nid); meths.append('source_annotation_kg' if nid else 'unresolved'); confs.append(0.97 if tier == 'A' else 0.9 if nid else 0.0); refs.append(f'kg:{rid}' if rid else None)
            add('sunni', book, no, {'kg': hid, 'sanadset_row': srow}, nass, spans, ids, meths, confs, refs, [None] * len(ids), fl, 'kg_annotation', tier, ms, me); continue
        if srow in parsed and parsed[srow].get('ids'):
            P = parsed[srow]; text = P['text']; names = P['names']; spans = find_spans(text, names)
            ids = [itq_canon(a) for a in P['ids']]; meths = ['linker_' + m for m in P['meth']]; confs = P['conf']
            add('sunni', book, no, {'kg': hid, 'sanadset_row': srow}, text, spans, ids, meths, confs, [f'itq:{a}' if a else None for a in P['ids']], [None] * len(ids), ['text_from_sanadset'], 'our_parse_sanadset', 'C', None, None); continue
        spans, mstart = parse_text(nass)
        if spans:
            res = [lookup(nass[a:b]) for a, b in spans]
            add('sunni', book, no, {'kg': hid, 'sanadset_row': srow}, nass, spans, [r_[0] for r_ in res], [r_[3] for r_ in res], [r_[1] for r_ in res], [None] * len(res), [r_[2] for r_ in res], ['parser_only'], 'parser_' + PARSER, 'C', mstart, None)
        else:
            add('sunni', book, no, {'kg': hid, 'sanadset_row': srow}, nass, [], [], [], [], [], [], ['no_chain'], 'none', 'none', None, None)
    done_k += len(ch)
    if (done_k // 4000) % 25 == 0: log('kg hadith assembled', done_k, dict(stat))
flush(); log('PHASE K done', dict(tier_ct)); gc.collect()
# ---------------- PHASE S: Sanadset rows with no hadith-kg counterpart
uni = open(S + 'hadith_unified.csv', encoding='utf-8-sig', newline=''); ur = csv.reader(uni); next(ur)
src = open(S + 'sanadset.csv', encoding='utf-8', newline=''); sr = csv.reader(src); next(sr)
nS = 0
for x, row in zip(ur, sr):
    rid = int(x[0])
    if rid in san_covered: continue
    nS += 1
    if LIMIT and nS > LIMIT // 4: break
    book, num, chain_source = x[1], x[2], x[9]
    if chain_source == 'original':
        text, nar, ms, me = tag_offsets(row[0]); names = ast.literal_eval(x[4]); ids_i = ast.literal_eval(x[6]); cf = ast.literal_eval(x[7]); mt = ast.literal_eval(x[8])
        spans = nar if len(nar) == len(names) else find_spans(text, names)
        fl = [] if len(nar) == len(names) else ['spans_by_name_search']
        add('sunni', book, num, {'sanadset_row': rid}, text, spans, [itq_canon(a) for a in ids_i], ['linker_' + m for m in mt], cf, [f'itq:{a}' if a else None for a in ids_i], [None] * len(names), fl, 'sanadset_tags', 'B', ms, me)
    elif chain_source.startswith('parsed') and rid in parsed and parsed[rid].get('ids'):
        P = parsed[rid]; text = P['text']; names = P['names']; spans = find_spans(text, names)
        add('sunni', book, num, {'sanadset_row': rid}, text, spans, [itq_canon(a) for a in P['ids']], ['linker_' + m for m in P['meth']], P['conf'], [f'itq:{a}' if a else None for a in P['ids']], [None] * len(names), [], 'our_parse_sanadset', 'C', None, None)
    else:
        text, _, ms, me = tag_offsets(row[0]); text = text if text.strip() else row[3]
        add('sunni', book, num, {'sanadset_row': rid}, text, [], [], [], [], [], [], ['no_chain:' + (x[10] or '')], 'none', 'none', None, None)
flush(); log('PHASE S done', dict(tier_ct))
# ---------------- PHASE T: Thaqalayn (Shi'i)
tp = TQ + 'thaqalayn_hadith.jsonl'
if os.path.exists(tp):
    with open(tp, encoding='utf-8') as f:
        for nT, line in enumerate(f):
            if LIMIT and nT > LIMIT // 4: break
            d = json.loads(line); text = d['chain_text'] + ' ' + d['matn']; tag_ids = [canon.get(f'thq:{i}') for i in d['narrator_ids']]
            if shia_ok(d):
                ids = tag_ids
                add('shia', d['book'], d['kid'].split(':', 1)[-1], {'thaqalayn': d['kid']}, text, [tuple(s) for s in d['spans']], ids, ['source_annotation_thaqalayn' if i else 'unresolved' for i in ids], [0.9 if i else 0.0 for i in ids], [f'thq:{i}' for i in d['narrator_ids']], [None] * len(ids), [], 'thaqalayn_annotation', 'B', d['matn_start'], len(text)); continue
            spans, mstart = parse_text(text[:d['matn_start']] if d['matn_start'] else text)
            ids = []; meths = []; confs = []; refs = []; alts = []
            for a, b in spans:
                hit = next((k for k, (x, y) in enumerate(d['spans']) if x < b and a < y and _n(d['chain_text'][x:y]).strip() not in _TW), None)
                if hit is not None and tag_ids[hit]: ids.append(tag_ids[hit]); meths.append('thaqalayn_id_on_reparsed_span'); confs.append(0.7); refs.append('thq:' + d['narrator_ids'][hit]); alts.append(None)
                else:
                    nid, cf_, al_, m_ = lookup(text[a:b]); ids.append(nid); meths.append(m_); confs.append(cf_); refs.append(None); alts.append(al_)
            add('shia', d['book'], d['kid'].split(':', 1)[-1], {'thaqalayn': d['kid']}, text, spans, ids, meths, confs, refs, alts, ['thaqalayn_tagging_unreliable', 'reparsed'], 'parser_' + PARSER, 'C', d['matn_start'], len(text))
    flush(); log('PHASE T done', dict(tier_ct))
else: log('Thaqalayn file missing: skipped')
# ---------------- reference chains: MIDS (Sahih Muslim, full multi-isnad) and SemanticHadith
mm = json.load(open(SRC + 'MIDS_SahihMuslim/mids_to_kg_v2.json', encoding='utf-8')); kgh = {}
for (hid_,) in []: pass
for r_ in mdb.execute('select 1'): pass
try:
    for h, v in mm.items():
        for sn, s_ in enumerate(v['mids_sanads'], 1):
            c.execute('INSERT INTO reference_chain VALUES(?,?,?,?,?)', ('mids', h, sn, json.dumps([canon.get(f'mids:{i}') for i in s_]), None))
except Exception as e: log('reference chain error', e)
with open(SRC + 'SemanticHadithV2/sh_chains_ids.csv', encoding='utf-8-sig', newline='') as f:
    r = csv.reader(f); next(r)
    for x in r: c.execute('INSERT INTO reference_chain VALUES(?,?,?,?,?)', ('semantichadith', f'{x[1]}-{x[2]}', 1, json.dumps([canon.get('sh:' + i.lstrip(':')) if i else None for i in json.loads(x[5])]), None))
db.commit()
c.executescript('CREATE INDEX IF NOT EXISTS ix_cm_h ON chain_mention(hadith_id); CREATE INDEX IF NOT EXISTS ix_cm_n ON chain_mention(narrator_id); CREATE INDEX IF NOT EXISTS ix_h_book ON hadith(book, number);'); db.commit()
log('FINAL: hadith', c.execute('select count(*) from hadith').fetchone()[0], '| mentions', c.execute('select count(*) from chain_mention').fetchone()[0], '| tiers', dict(tier_ct))
