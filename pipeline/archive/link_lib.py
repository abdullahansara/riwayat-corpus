import re, json, ast, csv, collections
csv.field_size_limit(10**9)
D = r'<ROOT>/Rijal_Itqan/rijal/'
S = r'<ROOT>/Sanadset/'
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655]')
HON = re.compile(r'\b(?:رضي الله (?:تعالى )?عنهما|رضي الله (?:تعالى )?عنهم|رضي الله (?:تعالى )?عنها|رضي الله (?:تعالى )?عنه|رحمه الله(?: تعالى)?|رحمهما الله|عليه السلام|صلى الله عليه (?:واله )?وسلم|رضى الله عنه|رضى الله عنها|رضى الله تعالى عنه)\b')
TITLES = {'الشيخ','الامام','الحافظ','الفقيه','القاضي','الاستاذ','الامير','الاديب','المحدث','الزاهد','العالم','شيخ'}
def norm(s):
    s = re.sub(r'<[^>]*>', ' ', s)
    s = re.sub(r'[0-9\u0660-\u0669]', ' ', s)
    s = DIAC.sub('', s).translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    s = HON.sub(' ', s)
    s = re.sub(r'\s(?:يعني|هو|وهو|يريد|يعنى|يعني)\s+(?:ابن|بن)\s', ' بن ', ' ' + s + ' ')
    s = re.sub(r'\s(?:يعني|وهو|هو|يريد)\s', ' ', s)
    s = re.sub(r'[^\w\s]|_', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    t = s.split()
    while len(t) > 1 and t[0] in TITLES: t = t[1:]
    return ' '.join(t)
def load_profiles():
    P = {}
    for g in ['companion','reliable','mostly_reliable','weak','abandoned','fabricator','unknown']:
        d = json.load(open(D + f'profiles_{g}.json', encoding='utf-8'))
        for k, v in d.items(): P[int(v['id'])] = v
    return P

# ---------- improved normalisation (case endings of kunya, clitics) ----------
KUN = re.compile(r'\b(ابا|ابي)\s+(?=[^\s]+)')
def norm2(s):
    s = norm(s)
    s = KUN.sub('ابو ', s)                       # ابا هريرة / ابي هريرة -> ابو هريرة
    s = re.sub(r'\b(?:بنا|بني|ابنا|ابني)\b', lambda m: 'ابن' if m.group(0).startswith('ا') else 'بن', s)
    s = re.sub(r'\bبنت\b', 'بنت', s)
    return s
def build_index(P):
    idx = collections.defaultdict(set); first = collections.Counter()
    for i, p in P.items():
        names = set([p['full_name']] + list(p.get('namings') or []))
        if p.get('kunya') not in (None, '', '-'): names.add(p['kunya'])
        for nm in names:
            k = norm2(nm)
            if k: idx[k].add(i); first[k.split()[0]] += 1
    # generated variants: 'ابن X' / 'عبد الله بن X' for well-connected profiles named 'عبد الله بن X ...'
    for i, p in P.items():
        if len(p.get('teachers') or []) + len(p.get('students') or []) < 30: continue
        t = norm2(p['full_name']).split()
        if len(t) >= 3 and t[0] == 'عبد' and t[1] == 'الله' and t[2] == 'بن' and len(t) >= 4:
            for k in ('ابن ' + t[3], 'عبد الله بن ' + t[3]):
                idx[k].add(i); first[k.split()[0]] += 1
    return idx, first
CLITIC = 'وفبلك'
def candidates(key, idx, first):
    """-> (set of profile ids, level). level 0 exact; 1 clitic-stripped; 2+ progressive prefix/suffix backoff."""
    if key in idx: return idx[key], 0
    t = key.split()
    if not t: return set(), -1
    if len(t[0]) > 2 and t[0][0] in CLITIC and t[0] not in first and t[0][1:] in first:
        k2 = ' '.join([t[0][1:]] + t[1:])
        if k2 in idx: return idx[k2], 1
        t = k2.split()
    for drop in range(1, min(4, len(t) - 1)):           # drop trailing tokens (nisba / extra)
        k2 = ' '.join(t[:len(t) - drop])
        if len(t) - drop >= 2 and k2 in idx: return idx[k2], 1 + drop
    if len(t) >= 3 and t[0] in ('ابو', 'ابن', 'ام') :
        k2 = ' '.join(t[1:])
        if k2 in idx: return idx[k2], 5
    return set(), -1
