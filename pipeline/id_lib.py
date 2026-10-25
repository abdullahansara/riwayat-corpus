"""Shared helpers for the narrator-ID ranker (fix_25): candidate generation and features for (mention, candidate) pairs."""
import re, math, collections
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
STOP = {'ابن', 'بن', 'ابو', 'ابي', 'ابا', 'عبد', 'الله', 'بنت', 'ام', 'محمد', 'احمد', 'علي'}
WEAK_METHODS = ['candidates_only', 'linker_context', 'linker_unique', 'name_plus_graph_edges', 'name_lookup_unique_v2', 'edge_context', 'gap_filled_unique', 'gap_model_unique', 'manual_gold', 'other']
class Ctx:
    """loads the lookup tables once (read-only connection)"""
    def __init__(self, c):
        self.exact = collections.defaultdict(set)
        for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): self.exact[nn].add(nid)
        self.forms = collections.defaultdict(set)
        for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed' and length(norm)<80"): self.forms[nid].add(nn)
        self.pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
        self.info = {i: (norm(n), d, t) for i, n, d, t in c.execute('select id,std_name,death_year,tradition from narrator')}
        self.edge = {(s, t): n for s, t, n in c.execute('select student,teacher,n_hadith from narrator_edge')}
        self.out_edges = collections.defaultdict(dict)
        for (s, t), n in self.edge.items(): self.out_edges[s][t] = n
        self.has_src = {r[0] for r in c.execute('select distinct narrator_id from narrator_source_id')}
def _vars(w): return {w, w.lstrip('و'), w[2:] if w.startswith('ال') else w, (w.lstrip('و')[2:] if w.lstrip('و').startswith('ال') else w.lstrip('و'))}
def compatible(ctx, sn, cand):
    """the surface shares a content word with the candidate's standard name or one of its registered forms (always true if the surface is a registered form)"""
    if sn in ctx.forms.get(cand, ()): return True
    st = [w for w in sn.split() if w not in STOP]
    if not st: return True                       # only generic words: cannot judge
    words = set(ctx.info[cand][0].split())
    for f in ctx.forms.get(cand, ()): words |= set(f.split())
    words = words | {w[2:] for w in words if w.startswith('ال')}
    return any(_vars(w) & words for w in st)
def candidates(ctx, surface, cur_id, guess, prev_id, limit=10):
    sn = norm(surface); cand = []
    for x in [cur_id, guess] + sorted(ctx.exact.get(sn, ()), key=lambda x: -ctx.pop.get(x, 0))[:8]:
        if x and x not in cand: cand.append(x)
    if prev_id and sn:
        st = set(sn.split())
        for t, n in sorted(ctx.out_edges.get(prev_id, {}).items(), key=lambda x: -x[1])[:3]:
            if t not in cand and len(cand) < limit and t in ctx.info and st & set(ctx.info[t][0].split()): cand.append(t)
    return [x for x in cand if x in ctx.info and compatible(ctx, sn, x)][:limit]
def feats(ctx, surface, cand, all_cands, cur_id, guess, cur_method, prev_id, next_id, tradition, pos, n_ments):
    sn = norm(surface); st = [w for w in sn.split() if w not in STOP]; nm = ctx.info[cand][0]; ct = set(nm.split())
    ov = sum(1 for w in st if w in ct or w.lstrip('و') in ct)
    pops = [ctx.pop.get(x, 0) for x in all_cands]; pc = ctx.pop.get(cand, 0)
    f = {
        'exact': float(sn in ctx.forms.get(cand, ())), 'ov_s': ov / max(1, len(st)), 'ov_c': ov / max(1, len(ct)),
        'n_s': len(sn.split()), 'n_c': len(nm.split()), 'logpop': math.log1p(pc), 'pop_share': pc / max(1, sum(pops)),
        'pop_rank': sorted(pops, reverse=True).index(pc), 'n_cands': len(all_cands),
        'e_prev': math.log1p(ctx.edge.get((prev_id, cand), 0)) if prev_id else -1.0,
        'e_next': math.log1p(ctx.edge.get((cand, next_id), 0)) if next_id else -1.0,
        'e_prev_rev': math.log1p(ctx.edge.get((cand, prev_id), 0)) if prev_id else -1.0,
        'e_next_rev': math.log1p(ctx.edge.get((next_id, cand), 0)) if next_id else -1.0,
        'is_cur': float(cand == cur_id), 'is_guess': float(cand == guess), 'has_cur': float(bool(cur_id)), 'has_guess': float(bool(guess)),
        'died_known': float(ctx.info[cand][1] is not None), 'died': (ctx.info[cand][1] or 0) / 1000.0,
        'trad_match': float(ctx.info[cand][2] == tradition), 'has_src': float(cand in ctx.has_src), 'pos': min(pos, 30), 'rel_pos': pos / max(1, n_ments),
        'prev_died': (ctx.info[prev_id][1] or 0) / 1000.0 if prev_id and prev_id in ctx.info else 0.0,
    }
    m = cur_method if cur_method in WEAK_METHODS else 'other'
    for k in WEAK_METHODS: f['m_' + k] = float(m == k)
    if prev_id and cand in ctx.info and ctx.info[cand][1] and prev_id in ctx.info and ctx.info[prev_id][1]:
        f['gap_years'] = (ctx.info[cand][1] - ctx.info[prev_id][1]) / 100.0
    else: f['gap_years'] = 0.0
    return f
