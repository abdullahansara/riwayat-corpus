import csv, sys, re, ast, collections, json, hashlib
csv.field_size_limit(10**9)
src = sys.argv[1]; books_f = sys.argv[2]
C = collections.Counter(); ex = collections.defaultdict(list)
def note(k, row_i, info=None):
    C[k]+=1
    if len(ex[k])<4: ex[k].append((row_i, info))
books = set(l.strip() for l in open(books_f, encoding='utf-8-sig') if l.strip())
books.discard('Book')
bookcnt = collections.Counter(); seen_bn = collections.Counter(); hseen = {}; mseen = collections.Counter()
nar_all = collections.Counter(); lens = collections.Counter()
diac = re.compile('[\u064B-\u0652\u0670\u0640]')
def norm(s): return re.sub(r'\s+',' ',diac.sub('',s)).strip()
nar_re = re.compile(r'<NAR>(.*?)</NAR>', re.S)
with open(src, encoding='utf-8', newline='') as f:
    r = csv.reader(f); hdr = next(r); print('header', hdr)
    for i,row in enumerate(r, 2):
        C['rows']+=1
        if len(row)!=6: note('bad_colcount', i, len(row)); continue
        H,B,N,M,S,L = row
        for name,v in zip(hdr,row):
            if v.strip()=='' : note('empty_'+name, i)
            if v.strip().lower() in ('nan','none','null'): note('nullstr_'+name, i, v)
        bookcnt[B]+=1
        if B not in books: note('book_not_in_books_csv', i, B)
        if B!=B.strip(): note('book_whitespace', i, repr(B))
        try: n=int(N)
        except: note('num_nonint', i, N); n=None
        if n is not None:
            if n<=0: note('num_nonpositive', i, N)
            seen_bn[(B,n)]+=1
        # tags
        for t in ('SANAD','MATN'):
            a,b = H.count('<%s>'%t), H.count('</%s>'%t)
            if a!=b or a>1: note('tag_%s_unbalanced_or_multi'%t, i, (a,b))
        if H.count('<NAR>')!=H.count('</NAR>'): note('nar_tag_unbalanced', i)
        hm = re.search(r'<MATN>(.*?)</MATN>', H, re.S)
        hs = re.search(r'<SANAD>(.*?)</SANAD>', H, re.S)
        if not hm: note('hadith_no_matn_tag', i)
        elif hm.group(1).strip()!=M.strip(): note('matn_col_ne_tagged_matn', i)
        if hm is None and '<MATN>' not in H and M.strip(): note('matn_col_but_no_tag',i)
        if not hs and S.strip()!='No SANAD': note('sanad_col_but_no_tag', i)
        if hs and S.strip()=='No SANAD': note('tag_sanad_but_col_nosanad', i)
        # sanad list
        nars_h = nar_re.findall(hs.group(1)) if hs else []
        if S.strip()=='No SANAD': sl=[]
        else:
            try: sl = ast.literal_eval(S); assert isinstance(sl,list)
            except Exception: note('sanad_unparseable', i, S[:80]); sl=None
        try: Ln=int(L)
        except: note('len_nonint', i, L); Ln=None
        lens[Ln]+=1
        if sl is not None:
            if Ln is not None and Ln!=len(sl): note('len_ne_list', i, (Ln,len(sl)))
            if len(sl)!=len(nars_h): note('list_ne_tagged_nar_count', i, (len(sl),len(nars_h)))
            elif [x.strip() for x in sl]!=[x.strip() for x in nars_h]: note('list_ne_tagged_nar_text', i)
            if len(sl)!=len(set(sl)): note('repeated_narrator_in_chain', i, sl[:5])
            for x in sl:
                nar_all[x]+=1
                if x.strip()=='' : note('empty_narrator', i)
                if x!=x.strip() or '  ' in x: note('narrator_whitespace', i, repr(x))
                if re.search(r'[0-9A-Za-z]', x): note('narrator_latin_digit', i, x)
                if re.search(r'[\[\]\(\)<>"\'«»{}]', x): note('narrator_punct', i, x)
                if len(norm(x))<=3: note('narrator_very_short', i, x)
                if len(x.split())>12: note('narrator_very_long(>12w)', i, x[:100])
                if re.search(r'\b(قَالَ|قال|حَدَّثَنَا|حدثنا|أَخْبَرَنَا|أخبرنا|حَدَّثَنِي|عَنْ|عن)\b', x): note('narrator_contains_verb/عن', i, x[:100])
        # matn problems
        if re.search(r'</?(SANAD|NAR)>', M): note('matn_contains_sanad_tags', i)
        if re.search(r'</?MATN>', M): note('matn_col_contains_matn_tag', i)
        ml=len(M.strip())
        if 0<ml<15: note('matn_very_short(<15ch)', i, M)
        if ml>5000: note('matn_very_long(>5000ch)', i, ml)
        if '\ufffd' in H: note('replacement_char', i)
        if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\u202a-\u202e\ufeff]', H): note('control_or_bidi_chars', i)
        if 'ـ' in H: note('tatweel', i)
        if not re.search(r'[\u0600-\u06FF]', H): note('hadith_no_arabic', i)
        if re.search(r'\s{3,}', M): note('matn_multi_space', i)
        if Ln is not None and Ln>=15: note('sanad_len>=15', i, Ln)
        k = norm(M)
        mseen[hashlib.md5(k.encode()).digest()]+=1
        hk = hashlib.md5(H.encode()).digest()
        if hk in hseen: note('exact_dup_hadith_field', i, hseen[hk])
        else: hseen[hk]=i
print(json.dumps({k:v for k,v in sorted(C.items())}, ensure_ascii=False, indent=1))
print('\nEXAMPLES')
for k,v in ex.items(): print(k, v)
print('\nbooks_used', len(bookcnt), 'books.csv', len(books), 'unused', [b for b in books if b not in bookcnt][:20])
print('smallest books', bookcnt.most_common()[-8:])
print('largest books', bookcnt.most_common(6))
d = [(k,c) for k,c in seen_bn.items() if c>1]
print('dup (book,num) keys', len(d), 'rows involved', sum(c for _,c in d), d[:5])
print('dup matn groups', sum(1 for c in mseen.values() if c>1), 'rows in dup groups', sum(c for c in mseen.values() if c>1), 'unique matn', len(mseen))
print('Sanad_Length dist', sorted(((k,v) for k,v in lens.items() if k is not None))[:40])
print('unique narrator strings', len(nar_all), 'unique after diacritic strip', len({norm(x) for x in nar_all}))
print('top narrators', nar_all.most_common(8))
