"""Surgery step 17 - add narrators the parser skipped.
Found by comparing the 100 gold chains with the old parse: 56 of 67 missed narrators were plain names sitting right after a transmission
verb or "عن" ("حدثنا أبو بكر ،", "ثنا النضر بن إسماعيل البجلي ،", "عن عائشة ،") in the stretch of text between two parsed mentions.
Rule: inside the main-chain region (before matn_start) look at each stretch not covered by a mention. Strip connector words from both ends
(verbs, عن, قال, و, honorifics ...). What is left becomes a new mention when it is 1-8 words, every word occurs in narrator names,
no word in the middle is a connector, it is preceded by a transmission verb / عن / سمعت and followed by a delimiter or connector.
New mentions get an asserted ID only when exactly one narrator owns that full name (registry forms); otherwise a weak guess (most popular owner).
Positions of the chain are renumbered in text order. flags: gap_filled.
  python pipeline/fix_17_fill_gaps.py pilot [N] [tier] [seed]
  python pipeline/fix_17_fill_gaps.py apply"""
from paths import *
import sqlite3, sys, re, random, collections, json
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
db = sqlite3.connect(OUT + 'hadith_master.db', timeout=120); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
HON = re.compile(r'\((?:رضي|عليه|عليها|عليهم|صلى|ص|ع|رحمه)[^)]{0,30}\)|(?:رضي الله عن(?:ه|ها|هم|هما)|رحمه الله|رحمهما الله|عليه السلام|عليها السلام|عليهم السلام|عليهما السلام|صلى الله عليه و?(?:على )?(?:اله )?وسلم|ﷺ|صلى الله عليه وسلم)')
def plain_map(text):
    keep = [i for i, ch in enumerate(text) if not DIAC.match(ch)]
    pl = ''.join(text[i] for i in keep).translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    return pl, keep
VERB = set('حدثنا حدثني حدثناه حدثنيه اخبرنا اخبرني اخبرناه اخبرنيه انبانا انبا انبانا نبانا ثنا ثني انا نا حدثتنا اخبرتنا اخبرنى حدثنى'.split())
LEAD = VERB | set('عن وعن سمعت سمعتا سمع قال وقال يقول قالا ثم فقال وحدثنا وحدثني واخبرنا واخبرني وانا ونا وثنا ان انه وان ح'.split())
CONN = LEAD | set('حدثه حدثهم اخبره اخبرهم قالوا قالت يقولان سمعته سمعنا انها فقالا فقالوا في فيما كتب الي كتابه اجازه اجازة قراءه قراءة عليه عليهم عليها قرات قرا قريء لي لنا له لها يعني يعنى هو وهو ثنا مثله بمثله نحوه بنحوه بهذا الاسناد بالاسناد بمعناه معناه زاد وزاد ذكر وذكر نحو بمثل حديث الحديث الله صلي رسول النبي عنه عنها عنهم عنهما رضي تعالي رحمه و ف'.split())
TITLES = set('الحافظ القاضي الاستاذ الشيخ الامام الفقيه قوله الفقيه المحدث الحاكم الاديب الزاهد الخطيب'.split())
VERBISH = set('سال ركب قام خرج راي كان قلت سمعت رايت دخل جاء جاءه اتي اتيت وقد حدث قدم قضي امر نهي ذكر وذكر قوله فيه فيها'.split())
REL = set('ابي ابيه ابوه اباه جدي جده عمي عمه خالي خالتي امه امي اخي اخيه ابنه ابني'.split())
NAMEWORDS = collections.Counter()
for (nn,) in c.execute("select norm from narrator_name where norm is not null and type!='observed' and length(norm)<60"):
    NAMEWORDS.update(set(nn.split()))
NAMEOK = {w for w, n in NAMEWORDS.items() if n >= 8} - CONN
exact = collections.defaultdict(set)
for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
def owners(name):
    n = re.sub(r'^و(?=[ء-ي]{3})', '', name)
    return exact.get(name) or exact.get(n) or set()
def propose(text, ms, ments):
    """ments: sorted (start,end) of main-chain mentions before ms. returns [(start,end)] in original offsets"""
    pl, keep = plain_map(text)
    blank = HON.sub(lambda m: ' ' * len(m.group()), pl)
    out = []; pos = 0
    bounds = [(s, e) for s, e in ments]
    gaps = []; cur = 0
    for s, e in bounds: gaps.append((cur, s)); cur = max(cur, e)
    gaps.append((cur, ms))
    # map original offsets -> plain index
    import bisect
    def pi(o): return bisect.bisect_left(keep, o)
    for a, b in gaps:
        pa, pb = pi(a), pi(b)
        seg = blank[pa:pb]
        if pb - pa > 400: continue
        toks = [(m.group(), pa + m.start(), pa + m.end()) for m in re.finditer(r'[ء-ي]+', seg)]
        if not toks: continue
        # strip connectors at both ends, remember the last stripped lead word
        i, j = 0, len(toks)
        while i < j and toks[i][0] in CONN: i += 1
        while j > i and toks[j - 1][0] in CONN: j -= 1
        if i >= j or j - i > 8: continue
        words = [t[0] for t in toks[i:j]]
        if any(w in CONN for w in words) or not all(w in NAMEOK or w in ('بن', 'ابن', 'ابو', 'ابي', 'ابا', 'بنت', 'ام') for w in words): continue
        if i == 0 and a == 0: continue                          # nothing before it: not clearly a narrator slot
        if i == 0 or toks[i - 1][0] not in LEAD: continue         # must follow a transmission verb / عن / سمعت
        # the stretch between the name and what follows must be a delimiter or connector
        after = seg[toks[j - 1][2] - pa:].strip() if False else ''
        s0 = keep[toks[i][1]]; e0 = keep[toks[j - 1][2] - 1] + 1
        while e0 < len(text) and DIAC.match(text[e0]): e0 += 1
        if any(x < e0 and s0 < y for x, y in bounds): continue
        name = ' '.join(words)
        if any(w in VERBISH for w in words): continue
        nxt = re.match(r'\s*([،,:.]|[ء-ي]+)', text[e0:e0 + 40])
        if nxt and not (nxt.group(1) in '،,:.' or plain_map(nxt.group(1))[0] in CONN or e0 >= ms - 2): continue
        if all(w in TITLES for w in words) or words[0] in ('بن', 'ابن') and len(words) < 3 or len(words) == 1 and words[0] in ('عبد', 'ابو', 'ابن', 'بن', 'ابي', 'ابا', 'ام', 'بنت'): continue
        if not owners(name):
            # unknown full name: accept only a genealogy-like phrase made of common name words
            if not (len(words) >= 3 and 'بن' in words[1:-1] and all(NAMEWORDS[w] >= 20 or w in ('بن', 'ابن', 'ابو', 'ابي') for w in words)): continue
        out.append((s0, e0))
    return out
if MODE in ('pilot', 'apply'):
    tiers = (sys.argv[3],) if MODE == 'pilot' and len(sys.argv) > 3 else ('A', 'B', 'C')
    ids = [r[0] for r in c.execute("select id from hadith where chain_tier in (%s) and matn_start is not null and (flags is null or (flags not like '%%gap_filled%%' and flags not like '%%gold_reviewed%%')) order by id" % ','.join("'%s'" % t for t in tiers))]
    import os
    if os.environ.get('SAMPLE'): random.seed(7); random.shuffle(ids); ids = ids[:int(os.environ['SAMPLE'])]
    if MODE == 'pilot':
        random.seed(int(sys.argv[4]) if len(sys.argv) > 4 else 1); random.shuffle(ids); N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        shown = 0
        for hid in ids:
            text, ms = c.execute('select text,matn_start from hadith where id=?', (hid,)).fetchone()
            ments = c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<? order by start', (hid, ms)).fetchall()
            if not ments: continue
            for s, e in propose(text, ms, ments):
                print(hid, '...', text[max(0, s - 40):s].replace('\n', ' '), '[[' + text[s:e] + ']]', text[e:e + 25].replace('\n', ' '), '| owners', len(owners(re.sub(r'\s+', ' ', plain_map(text[s:e])[0]).strip())))
                shown += 1
            if shown >= N: break

if MODE == 'apply':
    INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,alternatives,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)'
    n_h = n_m = 0
    for k, hid in enumerate(ids):
        text, ms, fl = c.execute('select text,matn_start,flags from hadith where id=?', (hid,)).fetchone()
        rows = c.execute('select rowid,pos,start,end,chain_no from chain_mention where hadith_id=?', (hid,)).fetchall()
        main = [r for r in rows if (r[4] or 1) == 1]
        if any(r[2] is None for r in main): continue
        ments = sorted((r[2], r[3]) for r in main if r[2] < ms)
        if not ments: continue
        props = propose(text, ms, ments)
        if not props: continue
        c.execute("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_17','positions',?,?,NULL)", (hid, json.dumps({r[0]: r[1] for r in rows})))
        for s0, e0 in props:
            surf = text[s0:e0]; name = re.sub(r'\s+', ' ', plain_map(surf)[0]).strip()
            nid = gid = None; conf = 0.0; meth = 'gap_filled_unresolved'
            if name in REL: meth = 'gap_relative_unresolved'
            else:
                ow = sorted(owners(name), key=lambda x: -pop.get(x, 0))
                if len(ow) == 1 and len(name.split()) >= 2: nid, conf, meth = ow[0], 0.8, 'gap_filled_unique'
                elif len(ow) == 1: gid, meth = ow[0], 'gap_filled_candidates'
                elif ow and pop.get(ow[0], 0) >= 3 * pop.get(ow[1], 0): gid, meth = ow[0], 'gap_filled_candidates'
            c.execute(INS, (hid, 900000, s0, e0, surf, nid, meth, conf, None, 'gap_filled', gid, 0.3 if gid else None)); n_m += 1
        main_ids = [r[0] for r in c.execute('select rowid from chain_mention where hadith_id=? and coalesce(chain_no,1)=1 order by start', (hid,))]
        c.execute('update chain_mention set pos=pos+100000 where hadith_id=? and coalesce(chain_no,1)=1', (hid,))
        c.executemany('update chain_mention set pos=? where rowid=?', [(i + 1, rid) for i, rid in enumerate(main_ids)])
        fl = (fl or '').split()
        if 'gap_filled' not in fl: fl.append('gap_filled')
        c.execute('update hadith set flags=?, n_narrators=(select count(*) from chain_mention where hadith_id=?) where id=?', (' '.join(fl), hid, hid)); n_h += 1
        if n_h % 5000 == 0: db.commit(); print(f'  {k:,}/{len(ids):,} hadith | changed {n_h:,} | mentions added {n_m:,}', flush=True)
    db.commit(); print('done: hadith', n_h, 'mentions added', n_m)
