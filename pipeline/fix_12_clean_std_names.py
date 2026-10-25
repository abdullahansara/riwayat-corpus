"""Surgery step 12 - clean corrupt narrator.std_name values (biography text, rijal codes, page numbers, '/18' markers).
The name is cut at the first sign of commentary (، ويقال / وقيل / عن / وعنه / ولد / ...), leading numbers and code letters
are stripped. Original kept in surgery_log (step fix_12, kind std_name). Records whose name is empty or becomes empty (including pure rijal codes like '(تمييز)') are flagged 'junk_name'.
  python pipeline/fix_12_clean_std_names.py pilot [N]     print before/after
  python pipeline/fix_12_clean_std_names.py apply"""
from paths import *
import sqlite3, re, sys, random
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
DIAC = '[ً-ْٰـٓ-ٕ]'
CODES = r'(?:بخ|خ|م|د|ت|س|ق|ع|عخ|خت|بخ|مق|فق|ر|تمييز|4|ي)'
CUT = re.compile(r'\s*(?:[،,؛:*|]|\|\||\s(?:ويقال|وقيل|ويقال|وقد|ويعرف|وعنه|ولد|وسمع|روى|روي|صدوق|ثقة|مجهول|ضعيف|عن|وجزم|وأكثر|وهو|قال|وقال|يروي|له|ومنه|ذكره|وفاته|قيل|مقبول|وأما|لأبيه|وأخرج|وكان|المعروف بابن|تقدم|وثقه|متروك|متروكان)\s)')
def clean(s):
    s = s or ''
    s = re.sub(r'/\d+', ' ', s)                       # '/18' marker tokens
    LC = r'(?:ن|ك|ت|خ|م|د|س|ق|ع|ه|ز|ص|بخ|صح|ي|مق|فق|عخ|ر|كن|سي|مد|دس|تم|4)'
    s = re.sub(r'^[\s\[(]*(?:' + LC + r'[\s,،]*)+[\])]?\s*[:,،]\s*(?=[ء-ي])', '', s)
    s = re.sub(r'^\(\s*' + LC + r'\s*\)\s*[:\-]?\s*', '', s)
    s = re.sub(r'^[\s\d()\[\]\-–—.،:*]+', '', s)      # leading numbers, brackets
    for _ in range(3):
        s = re.sub(r'^(?:\(|\[)?\s*(?:' + CODES + r'\s*)+(?:\)|\])?\s*[-–—]*\s*(?=[ء-ي])', lambda m: m.group(0) if len(m.group(0).split()) > 3 else '', s) if re.match(r'^[\(\[]\s*(?:' + CODES + r'\s*)+[\)\]]', s) else s
        s = re.sub(r'^[\s\d()\[\]\-–—.،:*]+', '', s)
    m = CUT.search(s)
    if m and m.start() > 0: s = s[:m.start()]
    s = re.sub(r'\[[^\]]*\]?', ' ', s) if '[' in s else s            # bracketed kunya/codes
    s = re.sub(r'\([^)]*\)?', ' ', s) if '(' in s else s
    s = re.sub(r'[^ء-يً-ْ ]', ' ', s)                 # anything non-Arabic
    s = re.sub(r'\s+', ' ', s).strip()
    while True:
        t = re.sub(r'^(?:ت|خ|م|د|س|ق|ع|بخ|صح|ي|مق|فق|عخ|ر|كن|سي|مد|دس|تم)\s+', '', s)
        if t == s: break
        s = t
    return s
def bad(n):
    n = n or ''
    return (not n.strip()) or bool(re.search(r'[0-9A-Za-z/(\[{|*]', n)) or bool(re.search(r'،|ويقال|وقيل|وعنه', n))
rows = [(i, n) for i, n in c.execute('select id, std_name from narrator') if bad(n)]
print(len(rows), 'suspect std_names')
if sys.argv[1:2] == ['pilot']:
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    random.seed(5)
    for i, n in random.sample(rows, N): print(i, '|', (n or '')[:90], '\n     ->', clean(n)[:90])
elif sys.argv[1:2] == ['apply']:
    ch = junk = 0
    for i, n in rows:
        new = clean(n)
        if len(new.split()) == 0 or len(new) < 3 or new == 'تمييز':
            c.execute("INSERT OR IGNORE INTO narrator_flag VALUES(?,?)", (i, 'junk_name')); junk += 1; continue
        if new != n:
            c.execute("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_12','std_name',?,?,?)", (i, n, new))
            c.execute('UPDATE narrator SET std_name=? WHERE id=?', (new, i)); ch += 1
    db.commit(); print('changed', ch, 'flagged junk', junk)
