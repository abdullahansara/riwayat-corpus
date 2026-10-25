"""Phase 2 - give every chainless ('none' tier) hadith a defined matn and an explicit sanad status, from the Claude classification in labels/none_out.
status -> action:
  report_only    matn = whole report (start at matn_start_phrase, end at matn_end_phrase); flag no_sanad_in_source
  fragment       same boundaries; flag fragment
  referential    matn starts after the back-reference ("وبه", "وعنه", "وبإسناده" ...); flag referential_opening
  chain_present  narrators listed by the labeller are located in the text and inserted as chain mentions (chain_no 1, id_method claude_chain_*);
                 matn from the phrases; hadith moves to tier C with flag claude_chain
  python pipeline/fix_27_none_apply.py pilot [N] [seed]    # read-only eye check
  python pipeline/fix_27_none_apply.py apply               # writes; logged in surgery_log (step fix_27)"""
from paths import *
from labels_lib import find, plain
import sqlite3, sys, json, glob, random, re, collections
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'
L = {}
for f in glob.glob('labels/none_out/chunk_*.jsonl'):
    for l in open(f, encoding='utf-8'):
        if l.strip():
            try: o = json.loads(l)
            except Exception: continue
            L.setdefault(o['id'], o)
FLAG = {'report_only': 'no_sanad_in_source', 'fragment': 'fragment', 'referential': 'referential_opening', 'chain_present': 'claude_chain'}
c = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply'))
def decide(h, o):
    text, tier, fl = c.execute('select text,chain_tier,flags from hadith where id=?', (h,)).fetchone()
    if tier != 'none': return None
    pl = plain(text)
    s = find(text, o.get('matn_start_phrase', ''), plain_text=pl); e = find(text, o.get('matn_end_phrase', ''), last=True, plain_text=pl)
    ms = s[0] if s else 0; me = e[1] if e else len(text)
    if o['status'] == 'chain_present':
        # narrators must lie before the matn start; look for them in text order
        pos = 0; ments = []
        for nm in o.get('narrators', []):
            r = find(text[pos:], nm)
            if not r: continue
            ments.append((pos + r[0], pos + r[1])); pos += r[1]
        if not s or not ments or ments[-1][1] > ms + 3: return ('skip', 'chain_present: narrators not before matn start or matn start not found', None)
        return ('ok', (ms, me, ments), text)
    if me <= ms + 5: me = len(text)
    if ms >= me: return ('skip', 'empty matn', None)
    # a start phrase found far into the text for a plain status means the labeller skipped a long part: keep it only for referential openers
    if o['status'] != 'referential' and ms > 40: ms = 0
    return ('ok', (ms, me, []), text)
res = {}; skip = collections.Counter()
for h, o in L.items():
    d = decide(h, o)
    if not d: skip['not none tier any more'] += 1; continue
    if d[0] == 'skip': skip[d[1]] += 1; continue
    res[h] = (o['status'], d[1], d[2])
print('labels', len(L), 'applicable', len(res), dict(skip), collections.Counter(v[0] for v in res.values()))
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for st in ('report_only', 'fragment', 'referential', 'chain_present'):
        ids = [h for h, v in res.items() if v[0] == st]
        for h in random.sample(ids, min(ARG or 6, len(ids))):
            _, (ms, me, ments), text = res[h]
            print(st, h, '| matn:', text[ms:ms + 70].replace('\n', ' '), '...', text[max(ms, me - 40):me].replace('\n', ' '), '| before:', text[:ms][-40:].replace('\n', ' '), '| after:', text[me:me + 30].replace('\n', ' '), '| chain:', [text[a:b] for a, b in ments][:4])
elif MODE == 'apply':
    DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
    norm = lambda s: re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
    exact = collections.defaultdict(set)
    for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
    pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
    INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)'
    n = 0
    for h, (st, (ms, me, ments), text) in res.items():
        fl = c.execute('select flags,matn_start,matn_end,chain_tier from hadith where id=?', (h,)).fetchone()
        c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_27','none_tier',?,?,?)", (h, json.dumps([fl[1], fl[2], fl[3], fl[0]]), json.dumps([ms, me, 'C' if st == 'chain_present' else 'none', st])))
        flags = ((fl[0] or '') + ' ' + FLAG[st] + ' claude_labelled').strip()
        for i, (a, b) in enumerate(ments, 1):
            surf = text[a:b]; name = norm(surf); ow = sorted(exact.get(name) or [], key=lambda x: -pop.get(x, 0)); nid = gid = None; meth = 'claude_chain_unresolved'
            if len(ow) == 1 and len(name.split()) >= 3: nid, meth = ow[0], 'claude_chain_unique'
            elif ow and (len(ow) == 1 or pop.get(ow[0], 0) >= 3 * pop.get(ow[1], 0)): gid, meth = ow[0], 'claude_chain_candidates'
            c.execute(INS, (h, i, a, b, surf, nid, meth, 0.8 if nid else 0.0, 'claude_chain', gid, 0.3 if gid else None))
        c.execute('update hadith set matn_start=?, matn_end=?, flags=?, chain_tier=?, n_narrators=? where id=?', (ms, me, flags, 'C' if st == 'chain_present' else 'none', len(ments), h)); n += 1
        if n % 3000 == 0: c.commit()
    c.commit(); print('applied', n)
