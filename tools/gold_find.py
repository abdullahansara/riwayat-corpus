"""Search narrators by name.  python tools/gold_find.py "حجاج بن محمد" ["another query" ...]
Matches narrator_name.norm containing ALL query tokens (diacritics/hamza/ta-marbuta normalised).
Shows id, standard name, death year, tradition, number of source datasets, number of chain mentions."""
import sqlite3, sys, os, re, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
db = os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
DIAC = re.compile('[ً-ْٰـٓ-ٕ‏‎]'); KEEP = re.compile('[^ء-ي ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
LIM = int(os.environ.get('LIM', 8))
for q in sys.argv[1:]:
    toks = [('بن' if t == 'ابن' else t) for t in norm(q).split()]
    toks_alt = [t for t in toks]
    where = ' AND '.join(["(' '||x.norm||' ') LIKE ?"] * len(toks) + ['length(x.norm) <= ?']); args = ['% ' + t + ' %' for t in toks] + [len(norm(q)) + 22]
    rows = c.execute(f'''SELECT n.id, n.std_name, n.death_year, n.tradition, n.n_sources,
        (SELECT count(*) FROM chain_mention m WHERE m.narrator_id=n.id) AS mentions
        FROM narrator n WHERE n.id IN (SELECT x.narrator_id FROM narrator_name x WHERE {where})
        ORDER BY (n.std_name LIKE ? ) DESC, mentions DESC LIMIT ?''', args + [norm(q).split()[0] + '%', LIM]).fetchall()
    print(f'-- {q}  ({len(rows)} shown)')
    for r in rows: print(f'   {r[0]} {r[1][:60]} | d.{r[2]} | {r[3][:6]} | src{r[4]} | {r[5]} mentions')
