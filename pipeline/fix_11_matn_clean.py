"""Surgery step 11 - matn boundaries made canonical (the text itself is never changed).
The matn is text[matn_start:matn_end].  Case analysis of ~70 random matns + 60K measured boundaries showed four defect classes:
  R1 START   the source's matn field dropped the narrative frame, so the matn begins mid-clause
             ("قال : كان رسول الله ﷺ | يصلي على الخمرة", "فقال : إن | الشيطان يجري ...").  The matn is now everything after the last
             narrator of the isnad and its connector words (قال, أن, أنه, "رسول الله ﷺ قال" ...).  Only done when the text in between holds no
             isnad material (no transmission verb, no عن+name run) and is at most 60 words.  The old value is kept in matn_start_source.
  R2 TRIM    leading/trailing blanks and lone commas are removed from the range.
  R3 END     scholarly commentary glued to the matn ("هذا حديث صحيح ...", "رواه البخاري ...", "قال الشيخ : ...") is cut off at the sentence
             boundary in front of it.  Old value kept in matn_end_source.
  R4 END     a second isnad that follows the matn after a sentence boundary ("... ".  نا هشيم ، قال : انا داود ، عن الشعبي ...") is cut off.
  python pipeline/fix_11_matn_clean.py pilot R1|R3|R4 [N] [tier] [seed]   show N before/after cases (nothing written)
  python pipeline/fix_11_matn_clean.py apply [rules, e.g. R1,R2,R3,R4]"""
from paths import *
import sqlite3, sys, re, random, collections
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
HON = re.compile(r'\(\s*(?:عليه|عليها|عليهم|عليهما)\s+السلام\s*\)|\((?:رضي|عليه|عليها|عليهم|صلى|ص|ع|رحمه)[^)]{0,30}\)|(?:رضي الله عن(?:ه|ها|هم|هما)|رحمه الله|رحمهما الله|عليه السلام|عليها السلام|عليهم السلام|عليهما السلام|صلى الله عليه و?(?:على )?(?:اله )?وسلم)')
def plain_map(text):
    keep = [i for i, ch in enumerate(text) if not DIAC.match(ch)]
    pl = ''.join(text[i] for i in keep).translate(str.maketrans('أإآٱ', 'اااا'))
    pl = HON.sub(lambda m: ' ' * len(m.group()), pl)
    return pl, keep
VERB = r'(?:انشدنا|انشدني|انشدنيه|حدثتنا|حدثتني|حدثكم|حدثكما|اخبرتنا|اخبرتني|اخبركم|قرات|قراءه|ذكره|ذكرته|حدثنا|حدثني|حدثنيه|حدثنى|اخبرنا|اخبرني|اخبرنيه|انبانا|انبانيه|انبا|ابنا|ابني|نبانا|ثنا|ثني|اخبرناه|حدثناه|نا|انا|ثنى)'
CH_PREV = {'عن', 'وعن', 'حدثنا', 'حدثني', 'اخبرنا', 'اخبرني', 'ثنا', 'ثني', 'نا', 'انا', 'سمعت', 'ح', 'انبانا', 'سالت', 'و', 'حدثنيه', 'قالا', 'قلت', 'سمع', 'اخبره', 'حدثه'}
SKIP = re.compile(r'(?:[\s،,:.؛\-–—]+|و?ف?(?:قال|قالت|قالا|قالوا|يقول|تقول|يقولان)(?![^\s،,:])|(?:ان|انه|انها|انهم|ح|اي)(?![^\s،,:])'
                  r'|(?:ان\s+)?(?:رسول\s+الله|النبي)\s*ﷺ?\s*[،,]?\s*(?:قال|يقول|(?=:))(?![^\s،,:]))*')
NAMES = {r[0] for r in c.execute("SELECT norm FROM narrator_name WHERE norm IS NOT NULL AND length(norm)<=60 AND (type!='observed' OR observed_count>=3)")}
VERBAL = {'قال', 'قلت', 'قالت', 'فقال', 'كان', 'كانت', 'سئل', 'قيل', 'جاء', 'رايت', 'دخلت', 'ان', 'انه', 'في', 'من', 'ما', 'لا', 'يقول', 'اتى', 'خرج', 'مر', 'لما', 'اذا', 'ثم', 'على', 'الى', 'هذا'}
def name_like(seg):
    w = [t for t in seg.split() if t]
    if w and w[0] == 'و' : w = w[1:]
    if not w or len(w) > 7 or any(t in VERBAL for t in w): return False
    if len(w) >= 2 and 'بن' in w[1:5]: return True
    return ' '.join(w) in NAMES or (w[0].startswith('و') and ' '.join([w[0][1:]] + w[1:]) in NAMES)
def new_start_r1(text, ms, ments):
    ends = sorted([m for m in ments if m[2] is not None and m[2] <= ms and (m[3] or 1) == 1], key=lambda m: m[2])
    if not ends: return None, 'no_mention'
    pick = None
    for m in reversed(ends[-3:]):
        before, _ = plain_map(text[max(0, m[1] - 40):m[1]]) if m[1] else ('', [])
        toks = [t.strip('،,:.؛"«»()-–—') for t in before.split()]
        toks = [t for t in toks if t != ''] if before.rstrip()[-1:] not in '،,' else toks
        last = (toks[-1] if toks else '')
        if last in CH_PREV or before.rstrip()[-1:] in '،,' or (last == '' and not before.strip()): pick = m; break
    if pick is None: return None, 'no_chain_mention'
    if pick is not ends[-1]: return None, 'mention_in_gap'                   # a later mention (chain narrator or story figure) would end up inside the matn
    e = pick[2]
    while e < len(text) and (DIAC.match(text[e]) or 'ء' <= text[e] <= 'ي'): e += 1          # rest of a word the mention stopped inside (عنه|ا)
    if e >= ms: return None, 'same'
    mp = re.match(r'\s*\([^()]{1,45}\)', text[e:ms + 45])
    if mp: e += mp.end()                                          # "( عليه السلام )" belongs to the narrator
    if e >= ms: return None, 'same'
    gap = text[e:ms]; pl, keep = plain_map(gap)
    s = SKIP.match(pl).end()                                       # connector words and punctuation after the last narrator
    if s >= len(keep): return None, 'same'
    ns = e + keep[s]
    if ns >= ms: return None, 'same'
    body = pl[s:]; words = body.split()
    if re.match(r'(?:بن|ابن|ابي|ابو|الزهري|الاعمش)\s', body): return None, 'partial_mention'
    if len(words) > 60: return None, 'gap_too_long'
    if re.match(r'(?:يعني|عمن|من اهله|من اهلها)(?![ء-ي])', body) or re.search(r'^(?:\S+\s+){0,11}?\S*[،,]\s*(?:قال|قالت|قالا)\s*:', body): return None, 'chain_gloss'
    if re.search(r'(?:^|\s)اخبره\s*[،,]?\s*ان(?:\s|$)', body): return None, 'chain_gloss'
    mq = re.match(r'([^:،,]{1,70}?)\s*[:،,]', body)
    if mq and name_like(mq.group(1)): return None, 'speaker_name_first'
    if re.match(r'(?:سمعت|حدثت|سالت|اخبرت)\s+(?!رسول|النبي)', body[:40]) and ':' in body[:80]: return None, 'chain_verb_first'
    if re.search(r'^(?:\S+\s+){0,5}?\S+\s+(?:سمعه|سمعها|سمعته)\s+من', body): return None, 'chain_gloss'
    if re.match(r'(?:(?:جدي|ابي|عمي|خالي|اخي|ابوي|امي)\s*[:،,]|(?:قرئ|قريء|قراءه|قراءة|مولى|مولي|مولاه|خادم|كاتب|\[)(?![ء-ي]))', body): return None, 'chain_epithet'
    if re.match(r'(?:لنا|لي|اجازه|اجازة|روى\s+عن|اجاز)(?![ء-ي])', body) or re.search(r'(?:^|\s)(?:روى\s+عنه|روى\s+عن|يكنى|كنيته|وكنيته|ولد\s+سنه|توفي\s+سنه|مات\s+سنه)(?:\s|$)', body) or re.search(r'/\d+', body): return None, 'biography_or_artifact'
    if re.match(r'و?ف?(?:عن|' + VERB + r')\s', body): return None, 'isnad_in_gap'
    if re.search(r'(?:^|[\s،,.:])و?ف?' + VERB + r'(?:\s|$)', body) or re.search(r'(?:^|\s)(?:و?عن)\s+\S+(?:\s+\S+){0,3}\s+(?:بن|ابن|ابي|ابو)\s', body) or re.search(r'\sح\s', body):
        return None, 'isnad_in_gap'
    return ns, 'ok'
COM = re.compile(r'(?<=[.؟!»)"”])\s+(?:[،,]\s*)?(?=(?:'
                 r'(?:هذا|هذه)\s+(?:حديث|الحديث|اسناد|إسناد|الاسناد|خبر)\s+\S+|'
                 r'(?:اخرجه|اخرجاه|اخرجها|رواه|رواهما|ورواه|رويناه|روياه)\s+\S+|'
                 r'قال\s+(?:الشيخ|ابو\s+عيسى|البيهقي|الحاكم|الدارقطني|الترمذي|ابو\s+داود|النسائي|ابو\s+عبد\s+الله|الطبراني|ابن\s+حجر|الالباني|المصنف|الذهبي|الهيثمي)\b|'
                 r'وفي\s+الباب|لم\s+يروه\s+الا|تفرد\s+به|لا\s+نعرفه\s+الا|هذا\s+اسناد))')
def cut_r3(text, ms, me):
    seg = text[ms:me]; pl, keep = plain_map(seg)
    for m in COM.finditer(pl):
        p = m.start()
        if p < 12 or not pl[:p].strip(): continue
        prev = pl[:p].rstrip()
        if prev[-1:] not in '.؟!»")”': continue
        if prev.count('"') % 2 == 1: continue                      # still inside a quotation
        q = p
        while q > 0 and pl[q - 1].isspace(): q -= 1
        return ms + keep[q - 1] + 1 if q - 1 < len(keep) else None
    return None
ISN = re.compile(r'(?<=[.؟!»")”])\s+(?:و?(?:حدثنا|حدثني|اخبرنا|اخبرني|ثنا|نا|انبانا|حدثنيه))\s+(?:[^\s،,.:]+\s+){1,6}?[^\s،,.:]+\s*[،,]\s*(?:قال\s*:?\s*)?(?:و?(?:حدثنا|حدثني|اخبرنا|اخبرني|ثنا|نا|انا|انبانا)\s|عن\s|ان\s)')
def cut_r4(text, ms, me):
    seg = text[ms:me]; pl, keep = plain_map(seg)
    for m in ISN.finditer(pl):
        p = m.start()
        if p < 8 or pl[:p].count('"') % 2 == 1: continue
        if pl[:p].rstrip()[-1:] not in '.؟!»")”': continue
        q = p
        while q > 0 and pl[q - 1].isspace(): q -= 1
        return ms + keep[q - 1] + 1
    return None
LINKV = r'(?:' + VERB[3:-1].replace('|نا|انا','').replace('|انا|','|').replace('|نا','') + r'|سمعت|عن|وعن|اخبرني|حدثني)'
LINK = re.compile(r'[\s"«،,:\-]*(?:و?ف?(?:قال|قالا)\s*:?\s*)?(?:و?ف?' + LINKV + r')\s+((?:[^\s،,:.]+\s+){0,7}?[^\s،,:.]+)\s*(?:يقول\s*)?(?::|(?:قال|قالا|قالت)\s*[:،,]?|[،,](?=\s*(?:انه|انها|ان|عن|وعن|حدثنا|حدثني|اخبرنا|اخبرني|ثنا|سمعت|قال|قالت|قالا)(?![ء-ي])))')
def cut_r5(text, ms, me):
    """leading remnants of the matn's own chain: 'حدثنا X ، قال : ...', 'سمعت X ، حدثني Y ، عن Z : ...'"""
    seg = text[ms:me]; pl, keep = plain_map(seg); pos = 0; n = 0
    while n < 8:
        m = LINK.match(pl, pos)
        if not m: break
        nm = m.group(1).strip()
        if re.match(r'(?:رسول|النبي|الله|ربي|ربكم|اصحاب|الناس|قوم|رجل|امراه|والله|قوله|قول|سورة|ايه|هذا|هذه|حديث|كذا|ذلك)(?![ء-ي])', nm) or not (name_like(nm) or nm in ('ابي', 'ابيه', 'جدي', 'عمي', 'خالي', 'اخي', 'ابوه')): break
        pos = m.end(); n += 1
    if n == 0: return None
    pos = re.compile(r'[\s،,:.؛\-–—]*(?:و?ف?(?:قال|قالت|قالا|قالوا|يقول)(?![^\s،,:])[\s،,:]*)*').match(pl, pos).end()
    if len(pl) - pos < 8 or pos >= len(keep): return 'chain_only'
    return ms + keep[pos]
ISN2 = re.compile(r'(?:(?<=[.؟!»")”])|(?<=["”»]\s[،,])|(?<=["”»][،,]))\s+(?:و?(?:حدثنا|حدثني|اخبرنا|اخبرني|ثنا|نا|انبانا|حدثنيه|حدثناه|ثناه))\s+(?:[^\s،,.:]+\s+){0,6}?[^\s،,.:]+\s*[،,]\s*(?:مثله|مثل ذلك|نحوه|بمثله|بنحوه|بمعناه|بهذا|قال\s*:?\s*["«]|عن\s)')
def cut_r6(text, ms, me):
    seg = text[ms:me]; pl, keep = plain_map(seg)
    for m in ISN2.finditer(pl):
        p = m.start()
        if p < 8 or pl[:p].count('"') % 2 == 1: continue
        q = p
        while q > 0 and pl[q - 1].isspace(): q -= 1
        return ms + keep[q - 1] + 1
    return None
P = lambda s_: DIAC.sub('', s_).replace('\n', ' ')
if MODE == 'pilot':
    rule = sys.argv[2]; N = int(sys.argv[3]) if len(sys.argv) > 3 else 25; tier = sys.argv[4] if len(sys.argv) > 4 else 'C'; random.seed(int(sys.argv[5]) if len(sys.argv) > 5 else 1)
    rows = c.execute("SELECT id,text,matn_start,matn_end FROM hadith WHERE chain_tier=? AND matn_start IS NOT NULL", (tier,)).fetchall()
    random.shuffle(rows); shown = 0; stat = collections.Counter()
    for hid, text, ms, me in rows:
        me = me or len(text)
        if rule == 'R1':
            ments = c.execute('SELECT pos,start,end,chain_no FROM chain_mention WHERE hadith_id=? AND start IS NOT NULL', (hid,)).fetchall()
            ns, why = new_start_r1(text, ms, ments); stat[why] += 1
            if ns is None or shown >= N or len(P(text[ns:ms]).strip(' "«»')) < 3: continue
            shown += 1; print('##', hid, 'start %d -> %d' % (ms, ns))
            print('    CHAIN :', P(text[max(0, ns - 60):ns])); print('    ADDED :', P(text[ns:ms])); print('    OLD→  :', P(text[ms:ms + 50]))
        elif rule == 'R5':
            x = cut_r5(text, ms, me); stat['none' if x is None else 'chain_only' if x == 'chain_only' else 'cut'] += 1
            if x is None or shown >= N: continue
            shown += 1; print('##', hid, 'start %d -> %s' % (ms, x)); print('    OLD :', P(text[ms:ms + 110]))
            if x != 'chain_only': print('    NEW :', P(text[x:x + 80]))
        else:
            ne = {'R3': cut_r3, 'R4': cut_r4, 'R6': cut_r6}[rule](text, ms, me)
            stat['cut' if ne else 'none'] += 1
            if ne is None or shown >= N: continue
            shown += 1; print('##', hid, 'end %d -> %d (matn len %d)' % (me, ne, me - ms))
            print('    KEPT END:', P(text[max(ms, ne - 70):ne])); print('    CUT OFF :', P(text[ne:me])[:170])
        if shown >= N and sum(stat.values()) > 4000: break
    print(dict(stat))
else:
    rules = (sys.argv[2] if len(sys.argv) > 2 else 'R1,R2,R3,R4').split(',')
    cols = [r[1] for r in c.execute('PRAGMA table_info(hadith)')]
    for col in ('matn_start_source', 'matn_end_source'):
        if col not in cols: c.execute('ALTER TABLE hadith ADD COLUMN %s INTEGER' % col)
    c.execute('CREATE INDEX IF NOT EXISTS ix_cm_h ON chain_mention(hadith_id)')
    c.execute('CREATE TABLE IF NOT EXISTS surgery_log(step TEXT, kind TEXT, key TEXT, old TEXT, new TEXT)')
    ids = [r[0] for r in c.execute("SELECT id FROM hadith WHERE matn_start IS NOT NULL")]
    stat = collections.Counter(); K = 0
    for k in range(0, len(ids), 4000):
        for hid in ids[k:k + 4000]:
            text, ms, me, fl, ss, se = c.execute('SELECT text,matn_start,matn_end,flags,matn_start_source,matn_end_source FROM hadith WHERE id=?', (hid,)).fetchone()
            me0 = me if me is not None else len(text); ns, ne = ms, me0; add = []
            if 'R1' in rules:
                ments = c.execute('SELECT pos,start,end,chain_no FROM chain_mention WHERE hadith_id=? AND start IS NOT NULL', (hid,)).fetchall()
                x, why = new_start_r1(text, ns, ments); stat['R1_' + why] += 1
                if x is not None: ns = x; add.append('matn_start_extended')
            if 'R3' in rules:
                x = cut_r3(text, ns, ne)
                if x: ne = x; add.append('matn_commentary_cut'); stat['R3'] += 1
            if 'R4' in rules:
                x = cut_r4(text, ns, ne)
                if x: ne = x; add.append('matn_isnad_cut'); stat['R4'] += 1
            if 'R5' in rules:
                x = cut_r5(text, ns, ne)
                if x == 'chain_only': add.append('matn_isnad_only'); stat['R5_chain_only'] += 1
                elif x: ns = x; add.append('matn_leading_link_cut'); stat['R5'] += 1
            if 'R6' in rules:
                x = cut_r6(text, ns, ne)
                if x and x - ns >= 8: ne = x; add.append('matn_isnad_cut'); stat['R6'] += 1
            if 'R2' in rules:
                while ns < ne and (text[ns].isspace() or text[ns] in '،,'): ns += 1
                while ne > ns and text[ne - 1].isspace(): ne -= 1
            if (ns, ne) != (ms, me0):
                c.execute("INSERT INTO surgery_log VALUES('fix_11','matn_range',?,?,?)", (hid, '%s-%s' % (ms, me), '%s-%s' % (ns, ne)))
                c.execute("UPDATE hadith SET matn_start=?, matn_end=?, matn_start_source=COALESCE(matn_start_source,?), matn_end_source=COALESCE(matn_end_source,?), flags=trim(coalesce(flags,'')||' '||?) WHERE id=?",
                          (ns, ne, ms, me, ' '.join(add), hid)); stat['changed'] += 1
        db.commit(); print('  %d/%d' % (min(k + 4000, len(ids)), len(ids)), dict(stat), flush=True)
    print('committed', dict(stat))
