"""Surgery step 10 - keep the isnad out of the matn.
The matn is text[matn_start:matn_end].  Two things are repaired (the text itself is never changed):
  (1) EMBEDDED isnad: a chain that starts inside the matn (Bukhari's trailing "وقال X : حدثنا ...", a second hadith appended to the entry ...):
        matn_end is moved back to where that chain starts.  flag: matn_truncated_isnad
  (2) LEADING remnant: the matn starts with the tail of its own chain ("حدثنا X ، عن Y : ..."):
        matn_start is moved behind the first colon that ends that chain.  flag: matn_start_after_isnad
A chain start = a transmission verb (حدثنا حدثني أخبرنا أخبرني أنبأنا ثنا ثني ...) followed by a name-like phrase (<= 7 words) and then
عن / قال / another verb.  The ambiguous words أنا / نا (I / we) are not used as verbs.
  python pipeline/fix_10_matn_sanad.py pilot [N] [tier]   show N random decisions (default tier C) for manual review; nothing written
  python pipeline/fix_10_matn_sanad.py apply
"""
from paths import *
import sqlite3, sys, re, random, collections
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = re.compile('[ً-ْٰـ]')
HON = re.compile(r'\((?:رضي|عليه|عليها|عليهم|صلى|ص|ع|رحمه)[^)]{0,30}\)|(?:رضي الله عن(?:ه|ها|هم|هما)|رحمه الله|رحمهما الله|عليه السلام|عليها السلام|عليهم السلام|عليهما السلام|صلى الله عليه و?(?:على )?(?:اله )?وسلم)')
def plain_map(text):
    """plain text (no vowel marks, hamza forms merged) and index map plain->original"""
    keep = [i for i, ch in enumerate(text) if not DIAC.match(ch)]
    pl = ''.join(text[i] for i in keep).translate(str.maketrans('أإآٱ', 'اااا'))
    pl = HON.sub(lambda m: ' ' * len(m.group()), pl)
    return pl, keep
V = r'(?:حدثنا|حدثن[يى]|حدثنيه|حدثنى?ه|اخبرنا|اخبرن[يى]|اخبرنيه|انبانا|انبان[يى]|انبانيه|انبا|ثنا|ثن[يى]|اخبرناه|حدثناه|نبانا)'
STOPNAME = {'في', 'قال', 'قوله', 'ان', 'انه', 'انها', 'يقول', 'قالا', 'قالوا', 'قالت', 'ثم', 'كان', 'كانت', 'فقال', 'فقلت', 'قلت', 'سمعت', 'سمع', 'رضي', 'عن', 'ح', 'وح', 'ص', 'يعني', 'هو', 'به', 'بها', 'بهذا', 'بذلك', 'لي', 'لنا', 'ايضا', 'مثله', 'نحوه', 'بمثله', 'ولم', 'لم', 'ما', 'قد', 'ثنا', 'نا', 'انا', 'عنه', 'عنها', 'عنهم', 'عنهما', 'حينيذ', 'حينئذ', 'بنحوه', 'نحوه', 'بمعناه', 'بنحو', 'بلفظه', 'مثل', 'بمثل', 'زاد', 'وزاد', 'بهذا'}
FILLER = {'به', 'بذلك', 'بهذا', 'بها', 'ايضا', 'أيضا', 'جميعا', 'مرة', 'حينئذ', 'حينيذ'}
PREFIX_FILL = r'(?:[\s:،,.؛"«\-]|اجازه|اجازة|املاء|إملاء|قراءه|قراءة|قراه|سماعا|حينئذ|حينيذ|باسناده|بإسناده|بأسانيده|ح|وح|قال|وقال)*'
ANON = {'رجل', 'رجلا', 'بعض', 'بعضهم', 'شيخ', 'امراة', 'امرأة', 'غير', 'من', 'والله', 'هذا', 'هذه', 'ذلك', 'اناس', 'ناس', 'قوم', 'اهل', 'احد', 'احدا', 'نحن', 'له', 'بحديث', 'حديثا', 'الحديث', 'فلانا', 'فلان', 'اصحابنا', 'اصحاب'}
PUNCT = '،,:.؛"«»()[]-–—/'
print('loading registry names ...', flush=True)
NAMES = {r[0] for r in c.execute("SELECT norm FROM narrator_name WHERE norm IS NOT NULL AND length(norm)<=60 AND (type!='observed' OR observed_count>=3)")}
def valid_phrase(w):
    """w = list of plain tokens (punctuation stripped). True if it looks like a narrator name"""
    if not w or w[0] in ANON or w[0] in STOPNAME: return False
    if 'بن' in w[1:6] or 'ابن' in w[:2] or w[0] in ('ابو', 'ابي', 'ابا', 'ام') and len(w) >= 2: return True
    for L in range(min(4, len(w)), 0, -1):
        p = ' '.join(w[:L])
        if p in NAMES or (p.startswith('و') and p[1:] in NAMES): return True
    return False
def tok_clean(t): return t.strip(PUNCT)
def chain_run(pl, start, first_ok=False):
    """contiguous isnad run beginning at plain offset `start` -> (end_offset, n_links, n_strong_links, name_spans) or (None, 0, 0, [])"""
    seg = pl[start:]; raw = seg.split(); pos = []; p = 0
    for t in raw:
        q = seg.index(t, p); pos.append(start + q); p = q + len(t)
    toks = [tok_clean(t) for t in raw]
    i = 0; links = 0; strong = 0; last_end = 0; spans = []
    def take_name(j):
        k = j; w = []
        while k < len(toks) and len(w) < 7:
            t = toks[k]
            if t == '':                      # separator token
                if w: k += 1; break
                k += 1; continue
            if t in STOPNAME or (w and t in ANON) or re.fullmatch(r'[A-Za-z]+-?\d*', t): break
            w.append(t); k += 1
            if raw[k - 1].endswith(tuple(PUNCT)) and len(w) >= 1: break
        if w:
            if k < len(toks) and toks[k] in ('هو', 'يعني'):                     # "محمد هو ابن أبي الحسين"
                k += 1; m = 0
                while k < len(toks) and m < 4 and toks[k] and toks[k] not in STOPNAME and not re.fullmatch('و?ف?' + V, toks[k]):
                    k += 1; m += 1
                    if raw[k - 1].endswith(tuple(PUNCT)): break
            while k + 0 < len(toks) and (toks[k] == '' or (toks[k].startswith('و') and len(toks[k]) > 2 and toks[k] not in STOPNAME and not re.fullmatch('و?ف?' + V, toks[k]) and toks[k][1:] not in ('قال', 'عن', 'ح'))) and k < len(toks):
                kk = k + 1 if toks[k] == '' else k
                if kk >= len(toks) or not toks[kk].startswith('و') or toks[kk] in STOPNAME: break
                k = kk + 1; m = 0                                                  # co-narrator after "و"
                while k < len(toks) and m < 3 and toks[k] and toks[k] not in STOPNAME and not re.fullmatch('و?ف?' + V, toks[k]) and not raw[k - 1].endswith(tuple(PUNCT)):
                    k += 1; m += 1
            return (k, w)
        return (j, [])
    while i < len(toks):
        t = toks[i]
        if t == '' or t in ('ح', 'وح', 'جميعا', 'اجازه', 'اجازة', 'املاء', 'إملاء', 'قراءه', 'قراءة', 'حينئذ', 'حينيذ', 'باسناده', 'بإسناده', 'سماعا'): i += 1; continue
        if t in ('قال', 'وقال', 'قالا', 'قالوا', 'فقال') and links: i += 1; continue
        is_v = bool(re.fullmatch('و?ف?' + V, t)) or (first_ok and not links and t in ('نا', 'انا')) or (links and t in ('نا', 'انا') and i > 0 and raw[i - 1].endswith(('،', ',')) or links and t in ('نا', 'انا') and i > 0 and toks[i - 1] == '')
        if is_v or t in ('عن', 'وعن', 'فعن'):
            j = i + 1
            while j < len(toks) and toks[j] in FILLER: j += 1
            k, w = take_name(j)
            if not w and not links and i < 4 and is_v: i = max(j, i + 1); continue      # stray 'حدثنا ،' at the start
            if not w or w[0] in ANON or len(w) > 4 and not valid_phrase(w): break
            ok = valid_phrase(w) or valid_phrase([w[0][2:]] + w[1:] if w[0].startswith('ال') else w)
            if not ok and not links and not (is_v or True): break
            ns_ = next((x for x in range(j, k) if toks[x] != ''), j); ne_ = max((x for x in range(j, k) if toks[x] != ''), default=j)
            spans.append((pos[ns_], pos[ne_] + len(raw[ne_].rstrip(PUNCT))))
            links += 1; strong += 1 if ok else 0; i = k; last_end = i; continue
        break
    if links == 0: return None, 0, 0, []
    return (pos[last_end] if last_end < len(pos) else len(pl)), links, strong, spans
LEAD_IN = re.compile(r'(?:و?(?:قال|زاد|رواه|روى|وزاد|ورواه)\s+(?:[^\s،,:.]+\s+){0,6}[^\s،,:.]+\s*[:،,]\s*)$')
PRE_SKIP = {'زاد', 'وزاد', 'قال', 'وقال', 'ح', 'ثم', 'قالا', 'قالوا', 'و'}
def to_orig(ms, keep, text, a, b):
    st = ms + keep[min(a, len(keep) - 1)]; en = ms + keep[min(max(b - 1, 0), len(keep) - 1)] + 1
    while en < len(text) and DIAC.match(text[en]): en += 1
    return st, en
def pre_name_spans(pl, a, b):
    """narrator names written before the first verb of a leading chain remnant: 'NAME ، وزاد X : NAME2 ، قالا :' """
    seg = pl[a:b]; out = []
    for m in re.finditer(r'[^،,:؛\-–]+', seg):
        toks = m.group().split(); lead = 0
        while lead < len(toks) and toks[lead] in PRE_SKIP: lead += 1
        w = [tok_clean(t) for t in toks[lead:] if tok_clean(t)]
        if w and len(w) <= 7 and valid_phrase(w):
            st = a + m.start() + len(' '.join(m.group().split()[:lead])) + (1 if lead else 0) + (len(m.group()) - len(m.group().lstrip()))
            out.append((st, a + m.end() - (len(m.group()) - len(m.group().rstrip()))))
    return out
def analyse(text, ms, me, extras=None):
    """returns the list of actions [('start', pos), ('end', pos)]; when `extras` (a dict) is given it receives
       extras['remnant'] = [(start, end), ...] narrator spans of a leading remnant (text offsets),
       extras['chains']  = [[(start, end), ...], ...]  chains found inside the cut-off part"""
    seg = text[ms:me]; pl, keep = plain_map(seg); act = []
    if extras is not None: extras['remnant'] = []; extras['chains'] = []
    # (1) leading remnant: a run of >= 2 links at the very beginning of the matn
    m0 = re.match(PREFIX_FILL, pl); st0 = m0.end()
    mv = re.search(r'(?:^|(?<=[\s:،,.؛]))(?:و?ف?' + V + r'|و?عن|انا|نا)\s', pl[:45])
    if mv and not re.match(r'(?:و?ف?' + V + r'|و?عن|انا|نا)\s', pl[st0:]) and len(pl[st0:st0 + mv.start()].split()) <= 4 and mv.start() >= st0:
        st0 = mv.start()
    end, n, st_, sp = chain_run(pl, st0, True)
    lead_end = 0; pre = []
    if not (end is not None and (st_ >= 2 or st_ >= 1 and n >= 3)):
        head = pl[st0:st0 + 260]; ht = head.split(); offs = []; p = 0
        for t in ht:
            q = head.index(t, p); offs.append(st0 + q); p = q + len(t)
        COMMON = {'في', 'من', 'على', 'ان', 'لا', 'ما', 'هذا', 'هذه', 'كان', 'كانت', 'الي', 'الى', 'او', 'انه', 'انها', 'ذلك', 'كل', 'يا', 'اذا', 'لم', 'قد', 'هل'}
        for i in range(1, min(len(ht), 26)):
            if tok_clean(ht[i - 1]) in COMMON: break
            if not (ht[i - 1].endswith(('،', ',', ':', '-', '–')) or tok_clean(ht[i - 1]) == '' or tok_clean(ht[i - 1]) in ('قالا', 'قالوا', 'قال', 'ثم', 'ح')): continue
            t0 = tok_clean(ht[i])
            if not (re.fullmatch('و?ف?' + V, t0) or t0 in ('عن', 'وعن', 'نا', 'انا')): continue
            e3, n3, s3, sp3 = chain_run(pl, offs[i], True)
            if e3 is not None and n3 >= 2 and s3 >= 1:
                end, n, st_, sp = e3, n3 + 1, s3 + 1, sp3; pre = pre_name_spans(pl, st0, offs[i]); break
    if end is not None and (st_ >= 2 or st_ >= 1 and n >= 3):
        e2 = end; tail = re.match(r'[\s،,]*(?:قال|قالا|قالوا)?\s*[:،]?\s*(?:في قول[هـ]?\s*[:]?\s*)?', pl[e2:]); e2 += tail.end() if tail else 0
        if e2 < len(pl) - 20:
            act.append(('start', ms + keep[min(e2, len(keep) - 1)])); lead_end = e2
            if extras is not None: extras['remnant'] = [to_orig(ms, keep, text, a_, b_) for a_, b_ in pre + sp]
    # (2) embedded runs of >= 2 links later on; the first one fixes the cut, every one is kept as a supplementary chain
    cut = None; scan = lead_end; endpos = len(pl)
    while True:
        found = None
        for m in re.finditer(r'(?:^|(?<=[\s.،,:؛)(]))و?ف?' + V + r'\s', pl[scan:]):
            vpos = scan + m.start() + (1 if pl[scan + m.start()] in ' .،,:؛)(' else 0)
            if vpos < lead_end + 8 and not act and cut is None: continue
            end2, n2, s2, sp2 = chain_run(pl, vpos)
            if end2 is None or not (s2 >= 2 or s2 >= 1 and n2 >= 3): continue
            s0 = vpos
            back = re.search(r'(?:(?:و?عن)\s+(?:[^\s،,:.]+\s+){0,4}[^\s،,:.]+\s*[،,]\s*(?:قال\s*:\s*)?)+$', pl[max(lead_end, vpos - 90):vpos])
            if back: s0 = max(lead_end, vpos - 90) + back.start()
            mm = LEAD_IN.search(pl[max(lead_end, s0 - 90):s0])
            if mm: s0 = max(lead_end, s0 - 90) + mm.start()
            if cut is None and s0 <= lead_end + 12: continue
            found = (s0, end2, sp2); break
        if not found: break
        s0, end2, sp2 = found
        if cut is None: cut = s0; act.append(('end', ms + keep[min(s0, len(keep) - 1)]))
        if extras is not None: extras['chains'].append([to_orig(ms, keep, text, a_, b_) for a_, b_ in sp2])
        scan = max(end2, scan + 1)
        if extras is None: break
    return act
import importlib.util, json
sp_ = importlib.util.spec_from_file_location('d2', PIPE + 'fix_02_disambiguate.py')
_argv = sys.argv; sys.argv = [_argv[0], 'noop']; d2 = importlib.util.module_from_spec(sp_); sp_.loader.exec_module(d2); sys.argv = _argv
THR = {1: 10.0, 2: 7.0, 3: 6.0}                    # margins with >= 99 % measured precision (fix_02 evaluation)
CAL = [(25, 0.998), (15, 0.997), (12, 0.996), (10, 0.994), (7, 0.99), (6, 0.93), (5, 0.88), (3, 0.85), (1, 0.70), (-99, 0.49)]
def calib(m): return next(v for lo, v in CAL if m >= lo)
def resolve(surfaces, prev_id=None):
    """narrator IDs for the names of one chain: asserted when the margin passes the per-length threshold, else a guess"""
    n = len(surfaces); ids = [None] * n; res = [None] * n
    for sweep in (0, 1):
        for i, sf in enumerate(surfaces):
            if ids[i] is not None: continue
            prev = ids[i - 1] if i > 0 else prev_id; nxt = ids[i + 1] if i + 1 < n else None
            mem = [x for j, x in enumerate(ids) if j != i and x]
            r = d2.rank(sf, prev, nxt, None, None, n - 1 - i, mem)
            if not r: continue
            margin = (r[0][0] - r[1][0]) if len(r) > 1 else 99.0
            k = min(len(d2.norm(sf).split()), 3) or 1
            if margin >= THR[k]: ids[i] = r[0][1]; res[i] = ('asserted', r[0][1], margin, [x[1] for x in r[1:4]])
            elif sweep == 1: res[i] = ('guess', r[0][1], margin, [x[1] for x in r[1:4]])
    return res
sel = ''
if MODE == 'pilot': sel = " AND chain_tier='C'" if (len(sys.argv) < 4 or sys.argv[3] == 'C') else " AND chain_tier='%s'" % sys.argv[3]
rows = db.cursor().execute("SELECT id, chain_tier, text, matn_start, matn_end FROM hadith WHERE chain_tier!='none' AND matn_start IS NOT NULL" + sel)   # own cursor: the writer below must not reset it
P = lambda s_: DIAC.sub('', s_).replace('\n', ' ')
nm = lambda x: (c.execute('select std_name,death_year from narrator where id=?', (x,)).fetchone() or ('?', None)) if x else ('-', None)
def show(text, spans, rs):
    return ' | '.join("%s=%s:%s" % (P(text[x:y])[:22], 'A' if r and r[0] == 'asserted' else 'g' if r else '?', nm(r[1])[0][:18] if r else '-') for (x, y), r in zip(spans, rs))
if MODE == 'pilot':
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 60; random.seed(int(__import__('os').environ.get('SEED', 17))); hits = []; seen = 0
    for hid, tier, text, ms, me in rows:
        me = me or len(text); seen += 1; ex = {}
        a_ = analyse(text, ms, me, ex)
        if a_: hits.append((hid, ms, me, a_, text, ex))
    print('hadith scanned %s | with an isnad inside the matn: %s (%.1f%%)' % (format(seen, ','), format(len(hits), ','), 100 * len(hits) / max(seen, 1)))
    nrem = sum(len(h[5]['remnant']) for h in hits); nch = sum(len(h[5]['chains']) for h in hits); nnm = sum(len(x) for h in hits for x in h[5]['chains'])
    print('narrators recovered into the main chain from leading remnants: %s | supplementary chains: %s with %s narrators' % (format(nrem, ','), format(nch, ','), format(nnm, ',')))
    random.shuffle(hits)
    for hid, ms, me, a_, text, ex in hits[:N]:
        ns, ne = ms, me
        for kind, pos in a_:
            if kind == 'start': ns = pos
            else: ne = pos
        print('## %s  matn %d-%d -> %d-%d' % (hid, ms, me, ns, ne))
        if ns != ms: print('     LEADING REMOVED :', P(text[ms:ns])[:100])
        if ex['remnant']: print('     -> into main chain:', show(text, ex['remnant'], resolve([text[x:y] for x, y in ex['remnant']])))
        print('     MATN NOW STARTS :', P(text[ns:ns + 55]))
        if ne != me:
            print('     KEPT MATN ENDS  :', P(text[max(ns, ne - 40):ne]))
            for k, spans in enumerate(ex['chains'], 2): print('     -> chain %d:' % k, show(text, spans, resolve([text[x:y] for x, y in spans])))
else:
    cols = [r[1] for r in c.execute('PRAGMA table_info(chain_mention)')]
    for col, typ in (('chain_no', 'INTEGER DEFAULT 1'), ('guess_narrator_id', 'TEXT'), ('guess_confidence', 'REAL')):
        if col not in cols: c.execute('ALTER TABLE chain_mention ADD COLUMN %s %s' % (col, typ))
    c.executescript('CREATE TABLE IF NOT EXISTS surgery_log(step TEXT, kind TEXT, key TEXT, old TEXT, new TEXT);')
    stat = collections.Counter(); todo = []
    for hid, tier, text, ms, me in rows:
        me = me or len(text); ex = {}; a_ = analyse(text, ms, me, ex)
        if a_: todo.append((hid, text, ms, me, a_, ex))
    print('hadith to repair:', len(todo), flush=True)
    INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,id_source_ref,alternatives,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
    def ov(a, b):
        o = min(a[1], b[1]) - max(a[0], b[0]); return o > 0 and o >= 0.5 * min(a[1] - a[0], b[1] - b[0])
    def rows_for(hid, text, spans, chain_no, pos0, existing, prev_id, flag):
        out = []; res = resolve([text[x:y] for x, y in spans], prev_id)
        for (x, y), r in zip(spans, res):
            if any(e[0] is not None and ov((x, y), e) for e in existing): stat['skipped_already_tagged'] += 1; continue
            pos0 += 1
            if r and r[0] == 'asserted': out.append((hid, pos0, x, y, text[x:y], r[1], 'matn_chain_extracted', 0.95, None, json.dumps(r[3]), flag, chain_no, None, None))
            elif r: out.append((hid, pos0, x, y, text[x:y], None, 'candidates_only', 0.0, None, json.dumps(r[3]), flag, chain_no, r[1], calib(r[2]))); stat['guess_only'] += 1
            else: out.append((hid, pos0, x, y, text[x:y], None, 'unresolved', 0.0, None, None, flag, chain_no, None, None)); stat['unresolved'] += 1
        return out
    for k, (hid, text, ms, me, a_, ex) in enumerate(todo):
        ns, ne = ms, me; fl = []
        for kind, pos in a_:
            if kind == 'start': ns = pos; fl.append('matn_start_after_isnad'); stat['start_moved'] += 1
            else: ne = pos; fl.append('matn_truncated_isnad'); stat['end_cut'] += 1
        existing = c.execute('SELECT start,end FROM chain_mention WHERE hadith_id=? AND start IS NOT NULL', (hid,)).fetchall()
        main = c.execute('SELECT pos,narrator_id FROM chain_mention WHERE hadith_id=? AND coalesce(chain_no,1)=1 ORDER BY pos DESC LIMIT 1', (hid,)).fetchone()
        added = 0
        if ex['remnant']:
            new = rows_for(hid, text, ex['remnant'], 1, main[0] if main else 0, existing, main[1] if main else None, 'from_matn_remnant')
            c.executemany(INS, new); added = len(new); stat['remnant_narrators_added'] += added
        for cn, spans in enumerate(ex['chains'], 2):
            new = rows_for(hid, text, spans, cn, 0, existing, None, 'supplementary_chain'); c.executemany(INS, new); stat['supplementary_chain_narrators'] += len(new)
        c.execute("INSERT INTO surgery_log VALUES('fix_10','matn_range',?,?,?)", (hid, '%d-%d' % (ms, me), '%d-%d' % (ns, ne)))
        c.execute("UPDATE hadith SET matn_start=?, matn_end=?, n_narrators=n_narrators+?, flags=trim(coalesce(flags,'')||' '||?) WHERE id=?", (ns, ne, added, ' '.join(fl), hid))
        if k % 20000 == 0: db.commit(); print('  %s/%s' % (format(k, ','), format(len(todo), ',')), dict(stat), flush=True)
    db.commit(); print('committed', len(todo), 'hadith |', dict(stat))
