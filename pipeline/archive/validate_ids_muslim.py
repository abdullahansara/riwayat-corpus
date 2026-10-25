import sqlite3, json, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
HM = '<ROOT>/HadithMaster/'
canon = json.load(open(HM + 'node_to_canonical.json'))
mm = json.load(open('<ROOT>/MIDS_SahihMuslim/mids_to_kg_v2.json', encoding='utf-8'))
db = sqlite3.connect(HM + 'hadith_master.db'); c = db.cursor()
kg2h = {}
for hid, src in c.execute("select id, source_ids from hadith where tradition='sunni'"):
    k = json.loads(src).get('kg')
    if k: kg2h[k] = hid
tot = 0; cat = collections.Counter(); prec_num = prec_den = rec_num = rec_den = 0; ex = []
for h, v in mm.items():
    if not v.get('exact_region'): continue
    hid = kg2h.get(v['kg'])
    if not hid: cat['no hadith row for this kg id'] += 1; continue
    ours = [r[0] for r in c.execute('select narrator_id from chain_mention where hadith_id=? and narrator_id is not null', (hid,))]
    mids = {canon.get(f'mids:{i}') for s in v['mids_sanads'] for i in s}; mids.discard(None)
    if not ours or not mids: cat['no ids on one side'] += 1; continue
    O = set(ours); tot += 1
    inter = O & mids; prec_num += len(inter); prec_den += len(O); rec_num += len(inter); rec_den += len(mids)
    if O == mids: cat['EXACT: same set of narrators'] += 1
    elif O <= mids: cat['ours is a subset (MIDS has extra: usually referential expansion)'] += 1
    elif mids <= O: cat['ours has extra narrators'] += 1
    else: cat['both differ'] += 1
    if O != mids and len(ex) < 6: ex.append((h, hid, len(O), len(mids), len(inter)))
log(f'Sahih Muslim hadith compared (MIDS exact-text units with our chains): {tot}')
for k, n in cat.most_common(): print(f'   {n:5d} {n/max(tot,1):6.1%}  {k}')
log(f'narrator-id precision (our ids found in MIDS set): {prec_num/prec_den:.3f} | recall (MIDS persons found in our ids): {rec_num/rec_den:.3f}')
print('examples (mids unit, our hadith, our #ids, MIDS #ids, shared):', ex)
