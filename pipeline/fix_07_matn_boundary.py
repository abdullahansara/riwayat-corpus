"""Surgery step 07 - matn boundary.
 rule: matn starts right after the last chain mention, skipping delimiters and speech/complementiser words (قال, أن, أنه ...).
 eval  : how often the rule reproduces the stored matn_start on tier A (where two annotations agree)
 apply : (1) hadith with no matn_start -> infer it (flag matn_start_inferred)
         (2) matn_start located inside the chain (chain mentions after it) -> move it behind the last mention (flag matn_start_moved)
         (3) a new isnad starting within 120 chars of the matn (حدثنا/أخبرنا ...) -> flag possible_second_hadith (no text is changed)
"""
from paths import *
import sqlite3, re, sys, collections, random
MODE = sys.argv[1] if len(sys.argv) > 1 else 'eval'
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
SKIPCH = set(' \t\r\n،,:;.؛-–—"«»()[]*‏‎')
SPEECH = {'قال', 'قالت', 'قالا', 'قالوا', 'يقول', 'يقولون', 'فقال', 'وقال', 'فقالت', 'وقالت', 'ان', 'انه', 'انها', 'ان', 'إن', 'أن', 'أنه', 'أنها', 'إنه', 'ل', 'انهم', 'أنهم'}
VERB = re.compile(r'(?:^|\s)(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انبا|ثنا|ثني|اخبرناه|حدثناه)(?:\s|$)')
def plain(s): return DIAC.sub('', s).translate(str.maketrans('أإآٱ', 'اااا'))
FORMULA = {plain(x) for x in ('رسول', 'الله', 'النبي', 'نبي', 'ﷺ', 'صلى', 'عليه', 'وسلم', 'وآله', 'قال', 'قالت', 'يقول', 'سمعت', 'عن', 'رضي', 'عنه', 'عنها', 'عنهما', 'انه', 'ان', 'أنه', 'أن', 'عليهم', 'السلام', 'ع', 'ص', 'صلي', 'وسلم')}
def rule(text, last_end):
    r = rule1(text, last_end)
    # attribution formula ending in a colon within 90 chars: the matn starts after the colon
    w = text[r:r + 90]; k = max(w.find(':'), w.find('：'))
    if k > 0:
        toks = [plain(t) for t in re.split(r'[\s،,:.؛"«»()\[\]]+', w[:k]) if plain(t)]
        if toks and all(t in FORMULA for t in toks): 
            j = r + k + 1
            while j < len(text) and (text[j] in SKIPCH or DIAC.match(text[j])): j += 1
            return j
    return r
def rule1(text, last_end):
    i = last_end
    while True:
        while i < len(text) and (text[i] in SKIPCH or DIAC.match(text[i])): i += 1
        j = i
        while j < len(text) and not (text[j] in SKIPCH): j += 1
        w = plain(text[i:j])
        if w in SPEECH or w in {plain(x) for x in SPEECH}: i = j; continue
        return i
if MODE == 'eval':
    random.seed(2); rows = c.execute("""SELECT h.text, h.matn_start, (SELECT max(end) FROM chain_mention m WHERE m.hadith_id=h.id AND m.end IS NOT NULL) FROM hadith h WHERE h.chain_tier='A' AND h.matn_start IS NOT NULL LIMIT 120000""").fetchall()
    d = collections.Counter(); n = 0
    for text, ms, le in rows:
        if le is None: continue
        n += 1; diff = ms - rule(text, le)
        d['exact' if diff == 0 else '+-3' if abs(diff) <= 3 else '+-10' if abs(diff) <= 10 else 'matn_later_than_rule' if diff > 0 else 'matn_earlier_than_rule'] += 1
    print(f'tier A hadith tested {n:,}:', {k: f'{v/n:.1%}' for k, v in d.items()})
else:
    c.executescript('CREATE TABLE IF NOT EXISTS surgery_log(step TEXT, kind TEXT, key TEXT, old TEXT, new TEXT);')
    stat = collections.Counter(); upd = []; flags = []
    for hid, text, ms, tier, le, n_after in c.execute("""SELECT h.id, h.text, h.matn_start, h.chain_tier, (SELECT max(end) FROM chain_mention m WHERE m.hadith_id=h.id AND m.end IS NOT NULL),
            (SELECT count(*) FROM chain_mention m WHERE m.hadith_id=h.id AND h.matn_start IS NOT NULL AND m.start>=h.matn_start) FROM hadith h WHERE h.chain_tier!='none'""").fetchall():
        if le is None: continue
        new = None
        if ms is None: new = rule(text, le); stat['inferred'] += 1; flag = 'matn_start_inferred'
        elif n_after or ms < le: new = rule(text, le); stat['moved'] += 1; flag = 'matn_start_moved'
        if new is not None and new < len(text): upd.append((new, flag, hid)); flags.append(('fix_07', 'matn_start', hid, ms, new))
        if VERB.search(plain(text[(new if new is not None else ms or 0):(new if new is not None else ms or 0) + 120])): stat['possible_second_hadith'] += 1; upd.append((None, 'possible_second_hadith', hid))
    for u in upd:
        if u[0] is not None: c.execute("UPDATE hadith SET matn_start=?, flags=trim(coalesce(flags,'')||' '||?) WHERE id=?", u)
        else: c.execute("UPDATE hadith SET flags=trim(coalesce(flags,'')||' '||?) WHERE id=?", (u[1], u[2]))
    c.executemany('INSERT INTO surgery_log VALUES(?,?,?,?,?)', flags); db.commit()
    print('result', dict(stat), '| committed')
