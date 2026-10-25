"""P1a: narrator records that are really placeholders ('عدة من أصحابنا', 'رجل', 'أبيه', 'أبي' = my father, 'بعض أصحابه') or connector junk ('و', 'رُوِيَ')
carry asserted IDs.  They are not people: take their mentions off the narrator layer (narrator_id/guess NULL) so fix_39 turns them into isnad nodes.
Named relatives ('أخيه الحسين', 'أبيه ميمون', 'جده شعيب') and anything non-placeholder are NOT touched (that is identity work for later phases).
  python pipeline/fix_47_placeholders.py list            candidate records
  python pipeline/fix_47_placeholders.py pilot [N] [seed]  random mentions with chain context, read by eye
  python pipeline/fix_47_placeholders.py apply           null the IDs (logged in surgery_log), drop their name forms; then run fix_39_isnad_nodes.py apply
"""
from paths import *
import sqlite3, sys, re, random, collections
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nrm(s): return re.sub(r'\s+', ' ', re.sub(r'[^ء-ي ]', ' ', re.sub(r'[A-Za-z]-?\d+', ' ', DIAC.sub('', s or '')).translate(TR))).strip()
THIRD = set('ابيه ابيها ابوه اباه ابيهم ابيهما ابيك جده جدها جدهم جدهما عمه عمها عمهم خاله خالها امه امها امهم اخيه اخوه اخيها ابنه ابنها ابائه ابايه اجداده ابايهم'.split())
FIRST = set('ابي ابانا ابى جدي عمي عمى خالي امي اخي ابني'.split())
ANON1 = set('رجل رجلا رجال رجلين رجلان امراه امراة نساء شيخ شيخا اشياخ شيوخ الثقه ثقه ناس قوم من عمن ممن فلان فلانا بعضهم غيره وغيره احدهما'.split())
CONNECTOR = set('و روي'.split())
ANONP = ('بعض اصحابنا', 'عده من اصحابنا', 'بعض اصحابه', 'غير واحد', 'رجل من', 'عده من', 'بعض اهل', 'اصحابنا', 'اصحاب', 'بعض رجاله', 'بعض مشايخنا', 'بعض اصحاب')
EXCLUDE = {'N0095514', 'N0032991'}      # 'غيرة' (a name), 'ابنة رزينة' (a named daughter): ة normalises to ه
def kind(std):
    n = nrm(std); w = n.split()
    if not w: return None
    if len(w) == 1 and w[0] in CONNECTOR: return 'connector'
    if len(w) == 1 and (w[0] in THIRD or w[0] in FIRST): return 'relative'
    if len(w) == 1 and w[0] in ANON1: return 'anonymous'
    if len(w) == 2 and w[0] in THIRD and w[1] in ('او', 'مرسلا', 'رفعه'): return 'relative'
    for p in ANONP:
        if n == p or (n.startswith(p + ' ') and len(w) <= 5 and 'بن' not in w): return 'anonymous'
    return None
cand = {}
for nid, std in c.execute('select id,std_name from narrator'):
    k = kind(std)
    if k and nid not in EXCLUDE: cand[nid] = (k, std)
print('candidate records', len(cand), collections.Counter(v[0] for v in cand.values()), flush=True)
if MODE == 'list':
    for nid, (k, std) in sorted(cand.items()): print(nid, k, std)
elif MODE == 'pilot':
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 40; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    ids = list(cand); random.shuffle(ids); rows = []
    for nid in ids:
        rows += [(nid,) + r for r in c.execute('select hadith_id,pos,chain_no,surface,id_method from chain_mention where narrator_id=? limit 3', (nid,))]
        if len(rows) > 600: break
    for nid, h, pos, cn, surf, meth in random.sample(rows, min(N, len(rows))):
        ch = c.execute('select surface from chain_mention where hadith_id=? and coalesce(chain_no,1)=? order by pos', (h, cn or 1)).fetchall()
        print(f'{nid} {cand[nid][0]:9s} {h} #{pos + 1}/{len(ch)} [{meth}]  ' + ' | '.join(s[0] if s[0] else '?' for s in ch[max(0, pos - 2):pos + 3]))
else:
    tot = 0
    for nid, (k, std) in cand.items():
        rows = c.execute('select rowid,id_method,guess_narrator_id from chain_mention where narrator_id=?', (nid,)).fetchall()
        meth = {'relative': 'linker_relative_father', 'anonymous': 'linker_anonymous', 'connector': 'fix_47_connector'}[k]
        for rid, om, g in rows:
            c.execute("insert into surgery_log values('fix_47','placeholder_mention',?,?,?)", (str(rid), f'{nid}|{om}|{g}', 'NULL|' + meth))
        c.execute("update chain_mention set narrator_id=NULL, guess_narrator_id=NULL, guess_confidence=NULL, id_method=?, id_confidence=NULL, "
                  "flags=trim(coalesce(flags,'')||' placeholder_record') where narrator_id=?", (meth, nid))
        for r in c.execute('select form,norm,type,source,observed_count from narrator_name where narrator_id=?', (nid,)).fetchall():
            c.execute("insert into surgery_log values('fix_47','placeholder_name_form',?,?,'deleted')", (nid, '|'.join(str(x) for x in r)))
        c.execute('delete from narrator_name where narrator_id=?', (nid,)); tot += len(rows)
    db.commit(); print('applied: records', len(cand), 'mentions', tot)
