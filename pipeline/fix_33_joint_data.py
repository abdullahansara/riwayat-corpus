"""Joint tagger training data.  One example per Claude-labelled hadith: whitespace tokens of the text (first MAXTOK) with a tag per token
  0 = chain other (connectors, verbs, honorifics)   1 = B-narrator   2 = I-narrator   3 = matn   4 = after the matn (grading, commentary, next report)
Narrator spans = the parsed mentions the labeller accepted (kind narrator / relative / anonymous) + the names it listed as missed (located inside the chain);
matn = [matn_start_phrase .. matn_end_phrase] located with labels_lib.find.  Labels come from the chunk files (text + mention offsets) and the *_out answers.
  build(dirs) -> list of dict(id, tokens, offs, tags, ids)   where dirs = [(chunk_dir, out_dir), ...]"""
import json, glob, os, re
from labels_lib import find, plain
TOK = re.compile(r'\S+')
MAXTOK = 450
def build(pairs, keep_ids=None):
    ex = []
    for cd, od in pairs:
        items = {}
        for f in glob.glob(os.path.join(cd, 'chunk_*.json')):
            for it in json.load(open(f, encoding='utf-8')): items[it['id']] = it
        for f in sorted(glob.glob(os.path.join(od, 'chunk_*.jsonl'))):
            for l in open(f, encoding='utf-8'):
                if not l.strip(): continue
                try: o = json.loads(l)
                except Exception: continue
                it = items.get(o.get('id'))
                if not it or (keep_ids is not None and it['id'] not in keep_ids): continue
                text = it['text']; pl = plain(text)
                s = find(text, o.get('matn_start_phrase', ''), plain_text=pl); e = find(text, o.get('matn_end_phrase', ''), last=True, plain_text=pl)
                st = o.get('chain_status')
                if st == 'no_sanad_in_source' and not s: s = (0, 0)
                if not s or not e or e[1] <= s[0] + 3: continue
                toks = [(m.start(), m.end()) for m in TOK.finditer(text)][:MAXTOK]
                spans = []
                kinds = {m['i']: m for m in o.get('mentions', [])}
                for m in it['mentions']:
                    k = kinds.get(m['i'])
                    if k is None or k.get('kind') in ('not_a_narrator',): continue
                    a = m['start']; b = a + len(m['surface'])
                    if b <= s[0] + 3: spans.append((a, b, k.get('choice') if k.get('kind') == 'narrator' and str(k.get('choice', '')).startswith('N') else None))
                pos = 0
                for nm in o.get('missed', []):
                    r = find(text[:s[0] + 3][pos:], nm)
                    if r:
                        a, b = pos + r[0], pos + r[1]; pos = b
                        if not any(a < y and b > x for x, y, _ in spans): spans.append((a, b, None))
                spans.sort()
                tags = []; ids = []
                for ts, te in toks:
                    t = 0
                    if ts >= s[0] and ts < e[1]: t = 3
                    elif ts >= e[1]: t = 4
                    if t != 3:
                        for a, b, nid in spans:
                            if ts < b and te > a: t = 1 if ts <= a or ts - a < 1 else 2; break
                    tags.append(t)
                # B only on the first token overlapping a span
                prev = None
                for i, (ts, te) in enumerate(toks):
                    if tags[i] in (1, 2):
                        sp = next(j for j, (a, b, _) in enumerate(spans) if ts < b and te > a)
                        tags[i] = 1 if sp != prev else 2; prev = sp
                    else: prev = None
                ex.append(dict(id=it['id'], tokens=[text[a:b] for a, b in toks], offs=toks, tags=tags, spans=[(a, b) for a, b, _ in spans], ms=s[0], me=e[1], tier=it.get('tier'), tradition=it.get('tradition')))
    return ex
if __name__ == '__main__':
    import collections
    pairs = [('labels/' + a, 'labels/' + b) for a, b in (('pilot', 'pilot_out'), ('wave1', 'wave1_out'), ('defects', 'defects_out'), ('unparsed', 'unparsed_out'), ('wave2', 'wave2_out'))]
    ex = build(pairs); print(len(ex), 'examples;', collections.Counter(t for e in ex for t in e['tags']))
