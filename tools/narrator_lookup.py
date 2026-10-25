"""Read-only narrator search tool for Claude agents (deep narrator identification).
  python tools/narrator_lookup.py chain H0485407          # the hadith text, its chain mentions and the current assignments
  python tools/narrator_lookup.py name "عبد الرحمن بن سلمة" [N]   # registry narrators whose names contain all the words (id, name, death, uses, tradition, name forms)
  python tools/narrator_lookup.py info N0001234            # one narrator: forms, death, tabaqa, top teachers and students (with counts)
  python tools/narrator_lookup.py pair N0001 N0002         # how often A narrates from B (and B from A) in the corpus, with a sample hadith id
  python tools/narrator_lookup.py with N0001 [N]           # the narrators that most often appear next to N0001 in chains
  python tools/narrator_lookup.py text "كلمات" [N]         # hadith whose text contains the words (find the same chain elsewhere)"""
import sqlite3, sys, re, json, os
DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'HadithMaster', 'hadith_master.db')
c = sqlite3.connect('file:' + DB + '?mode=ro', uri=True)
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
norm = lambda s: re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
nm = lambda i: (lambda r: f'{i} {r[0]} (d.{r[1]})' if r else str(i))(c.execute('select std_name,death_year from narrator where id=?', (i,)).fetchone())
a = sys.argv[1:]
if a[0] == 'chain':
    t, ms, me = c.execute('select text,matn_start,matn_end from hadith where id=?', (a[1],)).fetchone()
    print('TEXT:', t[:2500]); print('MATN starts at', ms)
    for pos, s, e, nid, meth, g in c.execute('select pos,surface,end,narrator_id,id_method,guess_narrator_id from chain_mention where hadith_id=? and coalesce(chain_no,1)=1 order by pos', (a[1],)):
        print(f' #{pos} "{(s or "").strip()}" -> current: {nm(nid) if nid else ("(weak guess) " + nm(g) if g else "none")} [{meth}]')
elif a[0] == 'name':
    ws = norm(a[1]).split(); n = int(a[2]) if len(a) > 2 else 15
    q = ' and '.join(["norm like ?"] * len(ws)); ids = {}
    for nid, in c.execute(f'select distinct narrator_id from narrator_name where {q} limit 400', [f'%{w}%' for w in ws]): ids[nid] = 1
    cnt = dict(c.execute(f"select narrator_id,count(*) from chain_mention where narrator_id in ({','.join('?' * len(ids))}) group by 1", list(ids)).fetchall()) if ids else {}
    exact = {i for i, in c.execute('select distinct narrator_id from narrator_name where norm=?', (' '.join(ws),))}
    out = sorted(ids, key=lambda i: (i not in exact, -cnt.get(i, 0)))[:n]
    for i in out:
        r = c.execute('select std_name,death_year,tradition,tabaqa from narrator where id=?', (i,)).fetchone()
        if r: print(f'{i} | {r[0][:70]} | d.{r[1]} | uses {cnt.get(i, 0)} | {r[2]} | tabaqa {r[3]}')
elif a[0] == 'info':
    r = c.execute('select std_name,death_year,birth_year,tabaqa,tradition,city from narrator where id=?', (a[1],)).fetchone(); print(r)
    print('forms:', [x for x, in c.execute('select distinct norm from narrator_name where narrator_id=? limit 12', (a[1],))])
    print('teachers:', [(nm(t), n) for t, n in c.execute('select teacher,n_hadith from narrator_edge where student=? order by n_hadith desc limit 12', (a[1],))])
    print('students:', [(nm(s), n) for s, n in c.execute('select student,n_hadith from narrator_edge where teacher=? order by n_hadith desc limit 12', (a[1],))])
elif a[0] == 'pair':
    x, y = a[1], a[2]
    for s, t in ((x, y), (y, x)):
        r = c.execute('select n_hadith from narrator_edge where student=? and teacher=?', (s, t)).fetchone()
        print(f'{s} narrates from {t}: {r[0] if r else 0} hadith')
elif a[0] == 'with':
    n = int(a[2]) if len(a) > 2 else 15
    for oth, k in c.execute('select teacher,n_hadith from narrator_edge where student=? union all select student,n_hadith from narrator_edge where teacher=? order by 2 desc limit ?', (a[1], a[1], n)): print(nm(oth), k)
elif a[0] == 'text':
    n = int(a[2]) if len(a) > 2 else 5
    for h, t in c.execute('select id,substr(text,1,300) from hadith where text like ? limit ?', ('%' + a[1] + '%', n)): print(h, t.replace('\n', ' '))
