from paths import *
import os, json, collections, time, sys
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
ROOT = SRC + 'ThaqalaynData_clone/repo/'
OUT = SRC + 'ThaqalaynData_clone/'
# ---- narrator index (id -> Arabic title, counts)
idx = json.load(open(ROOT + 'people/narrators/index.json', encoding='utf-8'))['data'] if os.path.exists(ROOT + 'people/narrators/index.json') else {}
if isinstance(idx, list): idx = {str(i): v for i, v in enumerate(idx)}
log('narrators in index:', len(idx))
rec = open(OUT + 'thaqalayn_hadith.jsonl', 'w', encoding='utf-8'); st = collections.Counter(); per_book = collections.Counter(); chain_len = collections.Counter()
for dp, dn, fn in os.walk(ROOT + 'books'):
    for f in fn:
        if not f.endswith('.json'): continue
        p = os.path.join(dp, f)
        try: d = json.load(open(p, encoding='utf-8'))
        except Exception: st['unreadable'] += 1; continue
        if d.get('kind') != 'verse_detail': st['not_hadith_file'] += 1; continue
        v = (d.get('data') or {}).get('verse') or {}
        nc = v.get('narrator_chain'); txt = v.get('text')
        if not nc or not nc.get('parts'): st['no_chain'] += 1; continue
        if not txt: st['no_text'] += 1; continue
        matn = txt[0] if isinstance(txt, list) else str(txt)
        text = ''; spans = []; ids = []
        for part in nc['parts']:
            t = part.get('text') or ''
            if part.get('kind') == 'narrator':
                spans.append((len(text), len(text) + len(t))); ids.append((part.get('path') or '').rsplit('/', 1)[-1])
            text += t
        if not spans: st['chain_without_narrators'] += 1; continue
        ms = len(text) + 1; full = text + ' ' + matn.strip()
        book = os.path.relpath(p, ROOT + 'books').replace('\\', '/').split('/')[0]
        rec.write(json.dumps({'kid': 'T:' + (d.get('index') or p), 'book': book, 'order': 'chain_first', 'text': full[:ms + 80], 'spans': spans, 'matn_start': ms, 'matn_end': min(len(full), ms + 80), 'narrator_ids': ids,
                              'chain_text': text, 'matn': matn.strip()}, ensure_ascii=False) + '\n')
        st['hadith'] += 1; per_book[book] += 1; chain_len[min(len(spans), 15)] += 1
        if st['hadith'] % 20000 == 0: log('parsed', st['hadith'])
rec.close(); log('DONE', dict(st)); print('hadith per book:', per_book.most_common(30)); print('narrators per chain:', sorted(chain_len.items()))
