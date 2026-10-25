"""Claude re-parse of risky chains.  The agents re-read the chain and give the exact list of transmitters (and say whether the matn start is right).
  python pipeline/fix_42_reparse.py build N OUTDIR [--risk-min R] [--seed S] [--exclude-dir D ...]   # item chunks (40 hadith each) from labels/chain_risk.db, highest risk first (or random above R)
  python pipeline/fix_42_reparse.py compare OUTDIR_OUT [OUTDIR_OUT2]                                    # agreement between the agents' lists and the database (and between two independent runs)
  python pipeline/fix_42_reparse.py pilot  OUTDIR_OUT [N]                                               # N would-be rewrites for an eye check
  python pipeline/fix_42_reparse.py apply  OUTDIR_OUT                                                   # rewrite the transmitter list of the hadith whose agent list differs from the database
Item: text (first 1400 chars) with the marker ⟦MATN⟧ where the database starts the matn, and the current mentions.  Agent answer per hadith (one JSON line):
  {id, transmitters:[{text, branch}], matn_ok: true|false, matn_start_phrase, note}      text = exact substring of the hadith text, in order; branch = 1, 2 ... (a new branch starts after a ح transfer)
Apply rules: every transmitter text must be found in order in the text before the matn (else the hadith is skipped); mentions that match a transmitter (+-3 chars) are kept with their ID;
other old mentions of the main chains are deleted (full row stored in surgery_log step fix_42 kind mention_row), new ones inserted unresolved (id_method claude_reparse_unresolved); pos / chain_no renumbered;
matn start changed only when matn_ok is false and the phrase is found; gold hadith never change."""
from paths import *
from labels_lib import find, plain
import sqlite3, sys, json, glob, os, re, random, collections
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
SPEC_MARK = '⟦MATN⟧'
if MODE == 'build':
    N = int(sys.argv[2]); OUTD = sys.argv[3]; seed = int(sys.argv[sys.argv.index('--seed') + 1]) if '--seed' in sys.argv else 1
    rmin = float(sys.argv[sys.argv.index('--risk-min') + 1]) if '--risk-min' in sys.argv else 0.0
    excl = set()
    for i, a in enumerate(sys.argv):
        if a == '--exclude-dir':
            for f in glob.glob(os.path.join(sys.argv[i + 1], 'chunk_*.json')):
                for it in json.load(open(f, encoding='utf-8')): excl.add(it['id'])
    gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
    rdb = sys.argv[sys.argv.index('--risk-db') + 1] if '--risk-db' in sys.argv else 'labels/chain_risk.db'; r = sqlite3.connect(rdb); rows = [(h, k) for h, k in r.execute('select hadith_id,risk from risk where risk>=? order by risk desc', (rmin,)) if h not in gold and h not in excl]
    random.seed(seed)
    if '--random' in sys.argv: random.shuffle(rows)
    c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); items = []; sel = []
    for h, k in rows:                         # gate: skip texts whose matn marker would fall beyond the 1400-char window (truncated chain, agents answer confidently anyway)
        ms0 = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()
        if ms0 and ms0[0] is not None and ms0[0] <= 1250: sel.append(h)
        if len(sel) >= N: break
    for h in sel:
        text, ms, book, trad = c.execute('select text,matn_start,book,tradition from hadith where id=?', (h,)).fetchone()
        ments = [{'i': i, 'surface': s, 'start': a} for i, (a, s) in enumerate(c.execute('select start,surface from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<? order by start', (h, ms + 3)))]
        marked = text[:ms] + SPEC_MARK + text[ms:]
        items.append({'id': h, 'book': book, 'tradition': trad, 'text': marked[:1400], 'database_mentions': ments})
    os.makedirs(OUTD, exist_ok=True)
    for k in range(0, len(items), 40): json.dump(items[k:k + 40], open(os.path.join(OUTD, f'chunk_{k // 40:04d}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(items), 'hadith in', (len(items) + 39) // 40, 'chunks ->', OUTD)
else:
    OD = sys.argv[2]; CD = re.sub(r'_out\d*$', '', OD)
    def load(od):
        L = {}
        for f in glob.glob(os.path.join(od, 'chunk_*.jsonl')):
            for l in open(f, encoding='utf-8'):
                if l.strip():
                    try: o = json.loads(l); L[o['id']] = o
                    except Exception: pass
        return L
    A = load(OD); items = {}
    for f in glob.glob(os.path.join(CD, 'chunk_*.json')):
        for it in json.load(open(f, encoding='utf-8')): items[it['id']] = it
    c = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply'))
    def spans_of(h, o):
        text = c.execute('select text from hadith where id=?', (h,)).fetchone()[0]; ms = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()[0]
        pos = 0; out = []
        if o.get('ok') is True and not o.get('transmitters'): return 'OK'
        for t in o.get('transmitters', []):
            r = find(text[:ms + 700][pos:], t['text'])
            if not r: return None
            a, b = pos + r[0], pos + r[1]; pos = b; out.append((a, b, int(t.get('branch') or 1)))
        return out
    close = lambda a, B: any(abs(a - b) <= 3 for b in B)
    if MODE == 'compare':
        B = load(sys.argv[3]) if len(sys.argv) > 3 else None; n = same_db = located = same_ab = 0; nab = 0
        for h, o in A.items():
            sp = spans_of(h, o)
            if sp is None or sp == 'OK': continue
            located += 1
            ms = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()[0]
            db = [r[0] for r in c.execute('select start from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<?', (h, ms + 3))]
            ag = [a for a, b, k in sp]; same_db += (len(db) == len(ag) and all(close(a, db) for a in ag)); n += 1
            if B and h in B:
                spb = spans_of(h, B[h])
                if spb is not None and spb != 'OK': nab += 1; same_ab += (len(spb) == len(sp) and all(close(a, [x[0] for x in sp]) for a, b, k in spb))
        print(f'agent lists located in the text: {located}/{len(A)}; agent list = database list: {same_db / max(1, n):.1%} ({same_db}/{n})' + (f'; two independent agent runs identical: {same_ab / max(1, nab):.1%} ({same_ab}/{nab})' if B else ''))
    else:
        B2d = sys.argv[3] if MODE == 'apply' and len(sys.argv) > 3 else (sys.argv[4] if MODE == 'pilot' and len(sys.argv) > 4 else None); B2 = load(B2d) if B2d else None
        gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
        todo = []; skip = collections.Counter()
        for h, o in A.items():
            if h in gold: skip['gold'] += 1; continue
            sp = spans_of(h, o)
            if sp == 'OK': skip['agent says database list is right'] += 1; continue
            if sp is None: skip['transmitter text not found'] += 1; continue
            if not sp: skip['empty list'] += 1; continue
            if B2 is not None:
                sb = spans_of(h, B2[h]) if h in B2 else None
                if sb is None or sb == 'OK' or len(sb) != len(sp) or not all(abs(x[0] - y[0]) <= 3 for x, y in zip(sp, sb)): skip['second run differs'] += 1; continue
            ms = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()[0]
            old = c.execute('select rowid,start,end,surface,narrator_id from chain_mention where hadith_id=? and start is not null and start<?', (h, ms + 3)).fetchall()
            if len(old) == len(sp) and all(close(a, [r[1] for r in old]) for a, b, k in sp): skip['same as database'] += 1; continue
            todo.append((h, sp, old, o))
        print('would rewrite', len(todo), dict(skip))
        if MODE == 'pilot':
            random.seed(3)
            for h, sp, old, o in random.sample(todo, min(int(sys.argv[3]) if len(sys.argv) > 3 else 12, len(todo))):
                text = c.execute('select text from hadith where id=?', (h,)).fetchone()[0]; ms = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()[0]
                print('\n', h, '| chain:', text[:min(ms, 420)].replace('\n', ' ')); print('   DB    :', [r[3].strip()[:28] for r in old]); print('   AGENT :', [text[a:b].strip()[:28] for a, b, k in sp], '| branches', sorted({k for a, b, k in sp}))
        else:
            INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)'
            cols = [r[1] for r in c.execute('pragma table_info(chain_mention)')]; n = 0
            for h, sp, old, o in todo:
                text, ms, fl = c.execute('select text,matn_start,flags from hadith where id=?', (h,)).fetchone()
                keep = {}
                for a, b, k in sp:
                    m = next((r for r in old if abs(r[1] - a) <= 3), None)
                    if m: keep[a] = m
                kept_ids = {m[0] for m in keep.values()}
                for r in old:
                    if r[0] in kept_ids: continue
                    row = c.execute('select * from chain_mention where rowid=?', (r[0],)).fetchone()
                    c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_42','mention_row',?,?,NULL)", (r[0], json.dumps(dict(zip(cols, row)), ensure_ascii=False)))
                    c.execute('delete from chain_mention where rowid=?', (r[0],))
                for a, b, k in sp:
                    if a in keep:
                        c.execute('update chain_mention set chain_no=?, start=?, end=?, surface=? where rowid=?', (k, a, b, text[a:b], keep[a][0]))
                    else:
                        cur = c.execute(INS, (h, 0, a, b, text[a:b], None, 'claude_reparse_unresolved', 0.0, 'claude_reparse', k, None, None))
                        c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_42','mention_inserted',?,?,NULL)", (cur.lastrowid, h))
                for k in {x[2] for x in sp}:
                    rows = c.execute('select rowid from chain_mention where hadith_id=? and coalesce(chain_no,1)=? and start is not null order by start', (h, k)).fetchall()
                    c.execute('update chain_mention set pos=pos+100000 where hadith_id=? and coalesce(chain_no,1)=?', (h, k))
                    c.executemany('update chain_mention set pos=? where rowid=?', [(i + 1, r[0]) for i, r in enumerate(rows)])
                fl2 = ((fl or '') + ' claude_reparsed').strip()
                if o.get('matn_ok') is False and o.get('matn_start_phrase'):
                    r = find(text, o['matn_start_phrase'])
                    if r and r[0] > max(b for a, b, k in sp) - 3:
                        c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_42','matn_start',?,?,?)", (h, ms, r[0])); c.execute('update hadith set matn_start=? where id=?', (r[0], h)); fl2 += ' claude_matn_start'
                c.execute('update hadith set flags=?, n_narrators=(select count(*) from chain_mention where hadith_id=? and coalesce(chain_no,1)=1) where id=?', (fl2, h, h)); n += 1
                if n % 2000 == 0: c.commit()
            c.commit(); print('applied', n)
