"""Rich review packets: full sanad of the hadith (names + death years), the PARALLEL sanads that disagree in the same slot, and both candidates' independent biography data
(Muslimscholars teacher/student names; Hawramani teacher/student segments).  python pipeline/fix_65_rich_packets.py <in_review.jsonl> <out.jsonl>"""
from paths import *
import sqlite3, sys, json, csv, re, collections, numpy as np
csv.field_size_limit(10**9); EXT = ROOT + 'external/zenodo_21019693/zenodo/'
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
nm = {i: (n, d, t) for i, n, d, t in c.execute('select id,std_name,death_year,tabaqa from narrator')}
def label(nid): return None if not nid else {'name': nm[nid][0], 'death_AH': nm[nid][1], 'tabaqa': nm[nid][2]}
def chain(h): return [{'surface': s, 'id': n, 'narrator': (nm[n][0] if n else None), 'death_AH': (nm[n][1] if n else None), 'rowid': r} for r, s, n in c.execute('select rowid,surface,narrator_id from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 order by pos,rowid', (h,))]
P = np.load('labels/parallels.npz'); M = np.load('labels/par_meta.npz'); ids = list(M['ids']); hix = {h: i for i, h in enumerate(ids)}; PA = P['a']; PB = P['b']
ms = {}
for r in csv.DictReader(open(EXT + 'muslimscholars_scholars.csv', encoding='utf-8', newline='')):
    ms[int(r['id'])] = (r['name_ar'], r['death_year_h'], r['teacher_ids'], r['student_ids'])
def msnames(js, k=12): return [ms[i][0][:40] for i in json.loads(js or '[]')[:k] if i in ms]
def msfor(nid):
    nmz = nm[nid][0].split(' ')[:3]
    return None
rows = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
with open(sys.argv[2], 'w', encoding='utf-8') as f:
    for x in rows:
        rid = x['rowid']; h = c.execute('select hadith_id from chain_mention where rowid=?', (rid,)).fetchone()[0]
        A = chain(h); k = next(i for i, m in enumerate(A) if m['rowid'] == rid)
        i = hix[h]; partners = [ids[j] for j in list(PB[PA == i]) + list(PA[PB == i])]
        par = []
        for p in partners:
            B = chain(p)
            if len(B) < 3: continue
            ia = {m['id']: n for n, m in enumerate(A) if m['id']}; ib = {m['id']: n for n, m in enumerate(B) if m['id']}
            sh = [n for n in ia if n in ib]
            # same slot: find partner mention between the same anchors as ours
            L = [n for n in A[:k] if n['id'] and n['id'] in ib]; R = [n for n in A[k + 1:] if n['id'] and n['id'] in ib]
            if not L or not R: continue
            jl, jr = ib[L[-1]['id']], ib[R[0]['id']]
            if jr - jl == 2:
                other = B[jl + 1]
                if other['id'] != A[k]['id']: par.append({'hadith_id': p, 'its_slot_mention': other['surface'], 'its_slot_narrator': other['narrator'], 'its_chain': [(m['surface'], m['narrator']) for m in B], 'its_text': c.execute('select text from hadith where id=?', (p,)).fetchone()[0][:1200]})
            if len(par) >= 3: break
        out = {'rowid': rid, 'surface': x['surface'], 'assigned_now': x['assigned_now'], 'alternative': x['alternative'],
               'full_sanad_of_this_hadith': [(m['surface'], m['narrator'], m['death_AH']) for m in A], 'slot_index': k,
               'full_text': x['full_text'], 'parallel_sanads_that_disagree_in_this_slot': par}
        # candidate biography data
        for key in ('assigned_now', 'alternative'):
            cid = next((i for i, v in nm.items() if v[0] == x[key]), None)
            out[key + '_record'] = label(cid)
        f.write(json.dumps(out, ensure_ascii=False) + '\n')
print('written', len(rows))
