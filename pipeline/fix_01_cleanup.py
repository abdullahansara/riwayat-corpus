"""Surgery step 01 - safe cleanups found by the audit and the 100-chain gold set.
Dry run by default; pass --apply to write.  All changes are logged in table `surgery_log`.

 A  delete over-long junk name forms (parser spans stored as names)
 B  strip corrupt index prefixes from narrator standard names ("[ 132 ] - ..."), fill empty standard names
 C  strip trailing honorifics (عليه السلام, ع, ﷺ, رضي الله عنه ...) from mention surfaces and shorten the span
 D  strip trailing "في قوله" from mention surfaces
 E  Tabari / Ibn Abi Hatim tafsir: "ابن زيد" is Abd al-Rahman b. Zayd b. Aslam
"""
from paths import *
import sqlite3, re, sys, collections
APPLY = '--apply' in sys.argv
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
c.executescript('CREATE TABLE IF NOT EXISTS surgery_log(step TEXT, kind TEXT, key TEXT, old TEXT, new TEXT);')
log = lambda *a: print(*a, flush=True)
DIAC = 'ً-ْٰـٓ-ٕ‏‎'
def norm(s):
    s = re.sub('[' + DIAC + ']', '', str(s or '')).translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', s)).strip()
SEQ = {'step': 'fix_01'}

# ---- A: junk name forms
n = c.execute("SELECT count(*) FROM narrator_name WHERE type='observed' AND (length(norm)>110 OR (length(norm)-length(replace(norm,' ','')))>=14)").fetchone()[0]
log(f'A: over-long observed name forms to delete: {n:,}')
if APPLY:
    c.execute("INSERT INTO surgery_log SELECT 'fix_01','delete_name_form',narrator_id,form,NULL FROM narrator_name WHERE type='observed' AND length(norm)>110 LIMIT 5000")
    c.execute("DELETE FROM narrator_name WHERE type='observed' AND (length(norm)>110 OR (length(norm)-length(replace(norm,' ','')))>=14)")

# ---- B: corrupt standard names
PRE = re.compile(r'^\s*\[\s*[\d٠-٩]+\s*\]\s*[-–—]?\s*')
rows = c.execute("SELECT id, std_name FROM narrator WHERE std_name LIKE '[%' OR std_name LIKE ' %' OR std_name IS NULL OR trim(std_name)=''").fetchall()
fix = []; empty = []
for nid, s in rows:
    if s is None or not s.strip(): empty.append(nid); continue
    t = PRE.sub('', s).strip()
    if t != s and t: fix.append((t, nid, s))
log(f'B: standard names with index prefix to fix: {len(fix):,} | empty standard names: {len(empty):,} | example: {fix[:2]}')
fill = []
for nid in empty:
    r = c.execute("SELECT form FROM narrator_name WHERE narrator_id=? AND type IN ('full','variant','kunya') AND length(form)>3 ORDER BY (type='full') DESC, length(form) DESC LIMIT 1", (nid,)).fetchone()
    if r: fill.append((r[0], nid))
log(f'   fillable from alternative names: {len(fill):,}')
if APPLY:
    for t, nid, s in fix: c.execute("INSERT INTO surgery_log VALUES('fix_01','std_name',?,?,?)", (nid, s, t))
    c.executemany('UPDATE narrator SET std_name=? WHERE id=?', [(t, nid) for t, nid, s in fix]); c.executemany("UPDATE narrator SET std_name=?, std_name_source='filled_from_alt_name' WHERE id=?", fill)

# ---- C/D: honorific and "في قوله" suffixes on mention surfaces
HON = re.compile(r'(?:\s*[\(\[]?\s*(?:عليه|عليها|عليهما|عليهم)\s*(?:ا[ً-ْ]*ل[ً-ْ]*س[ً-ْ]*ل[ً-ْ]*ا?[ً-ْ]*م[ً-ْ]*)\s*[\)\]]?'
                 r'|\s*[\(\[]\s*ع\s*[\)\]]|\s*صلى الله عليه[^،,]*|\s*ﷺ|\s*رضي الله (?:عنه|عنها|عنهم|عنهما))+\s*$')
QWL = re.compile(r'\s*(?:فِي|في)\s*(?:قَوْلِهِ|قوله)\s*$')
chg = []; hon = qwl = 0
for rid, surf, st, en, hid in c.execute("SELECT m.rowid, m.surface, m.start, m.end, m.hadith_id FROM chain_mention m WHERE m.surface LIKE '%السلام%' OR m.surface LIKE '%سلاَم%' OR m.surface LIKE '%ع )%' OR m.surface LIKE '%ﷺ%' OR m.surface LIKE '%رضي الله%' OR m.surface LIKE '%قوله' OR m.surface LIKE '%قَوْلِهِ'").fetchall():
    new = surf; new = HON.sub('', new) if HON.search(new) else new
    if new != surf: hon += 1
    q = QWL.sub('', new)
    if q != new: qwl += 1; new = q
    new = new.strip()
    if new and new != surf: chg.append((rid, surf, new, st, en))
log(f'C/D: honorific suffixes stripped: {hon:,} | "في قوله" stripped: {qwl:,} | surfaces changed: {len(chg):,}')
for r in chg[:3]: log('   ', repr(r[1][-45:]), '->', repr(r[2][-35:]))
if APPLY:
    for rid, old, new, st, en in chg:
        if st is not None and en is not None and en - st == len(old): c.execute('UPDATE chain_mention SET surface=?, end=? WHERE rowid=?', (new, st + len(new), rid))
        else: c.execute('UPDATE chain_mention SET surface=? WHERE rowid=?', (new, rid))
        c.execute("INSERT INTO surgery_log VALUES('fix_01','surface',?,?,?)", (rid, old, new))

# ---- E: Tabari-style "ابن زيد"
tid = 'N0002046'
rows = c.execute("""SELECT m.rowid, m.narrator_id, m.surface FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id
   WHERE h.book IN ('جامع البيان عن تأويل آي القرآن','تفسير ابن أبي حاتم') AND (m.narrator_id IS NULL OR m.narrator_id!=?)""", (tid,)).fetchall()
rows = [r for r in rows if norm(r[2]) in ('ابن زيد', 'عن ابن زيد')]
log(f'E: Tafsir "ابن زيد" mentions to re-point to {tid}: {len(rows):,}; currently: {collections.Counter(r[1] for r in rows).most_common(3)}')
if APPLY:
    for rid, old, s in rows: c.execute("INSERT INTO surgery_log VALUES('fix_01','narrator_id',?,?,?)", (rid, old, tid))
    c.executemany("UPDATE chain_mention SET narrator_id=?, id_method='surgery_tafsir_ibn_zayd', id_confidence=0.95 WHERE rowid=?", [(tid, r[0]) for r in rows])

if APPLY: db.commit(); log('committed')
else: log('dry run only - nothing written (use --apply)')
