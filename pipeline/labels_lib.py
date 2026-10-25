"""Shared helpers for the Claude-label / model pipeline (phase 1+).
load_labels(dirs) -> {hadith_id: label dict with offsets matn_start / matn_end (None if the phrase was not found)}."""
import re, json, glob, os
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
TRN = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def plain(text):
    """letters only (no diacritics/punctuation), single spaces; keep[i] = text offset of plain char i"""
    out = []; keep = []; sp = False
    for i, ch in enumerate(text):
        if DIAC.match(ch): continue
        ch2 = ch.translate(TRN)
        if 'ء' <= ch2 <= 'ي': out.append(ch2); keep.append(i); sp = False
        elif not sp and out: out.append(' '); keep.append(i); sp = True
    return ''.join(out), keep
def find(text, phrase, last=False, plain_text=None):
    """(start, end) text offsets of phrase (diacritic/punctuation-insensitive), first or last occurrence"""
    if not phrase: return None
    pt, keep = plain_text or plain(text); pp = plain(phrase)[0].strip()
    if not pp: return None
    i = pt.rfind(pp) if last else pt.find(pp)
    if i < 0: return None
    e = keep[i + len(pp) - 1] + 1
    while e < len(text) and DIAC.match(text[e]): e += 1          # include the vowel marks of the last letter
    return keep[i], e
def load_labels(dirs, texts):
    """dirs: label output directories (chunk_*.jsonl); texts: dict id -> text. Later dirs do not override earlier ones."""
    out = {}
    for d in dirs:
        for fn in sorted(glob.glob(os.path.join(d, 'chunk_*.jsonl'))):
            for l in open(fn, encoding='utf-8'):
                l = l.strip()
                if not l: continue
                try: o = json.loads(l)
                except Exception: continue
                h = o.get('id')
                if h in out or h not in texts: continue
                t = texts[h]; pl = plain(t)
                ls = find(t, o.get('matn_start_phrase', ''), plain_text=pl); le = find(t, o.get('matn_end_phrase', ''), last=True, plain_text=pl)
                if o.get('chain_status') == 'no_sanad_in_source' and not o.get('matn_start_phrase'): ls = (0, 0)
                o['matn_start'] = ls[0] if ls else None; o['matn_end'] = le[1] if le else None
                out[h] = o
    return out
